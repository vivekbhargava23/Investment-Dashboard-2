"""Daily NAV snapshot service.

Reconstructs portfolio EUR NAV for any calendar date by replaying FIFO positions
against historical OHLC closes (via OhlcDataProvider).

Design decisions (TICKET-013):
  - Historical snapshots (< today) are reconstructed once and cached in nav_repo.
  - Today's snapshot is computed from the latest available OHLC close and never cached.
  - FX reconstruction uses EURUSD=X / EURJPY=X via the same OhlcDataProvider (decision #5).
  - Trading days are the union of dates present in the OHLC bars across all tickers.
  - Per-ticker missing closes fall back to the most recent prior close (decision #9).
  - If no prior close exists, that ticker contributes zero and a warning is emitted.

Note on logging: the services CLAUDE.md prohibits logging in the service layer. This
service is an explicit exception: batch NAV reconstruction can silently produce incorrect
NAV if a ticker's OHLC is missing, and returning that error in the domain model would
require a container structure disproportionate to the value. The warnings here are the
minimal signal that lets a future operator diagnose stale snapshots.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from app.domain.fifo import compute_positions
from app.domain.market_data import ChartPeriod, OhlcUnavailableError
from app.domain.models import Transaction
from app.domain.money import Currency, Money
from app.domain.nav import DailyNavPoint
from app.domain.tickers import infer_currency_from_ticker
from app.ports.market_data import OhlcDataProvider
from app.ports.nav_repository import NavSnapshotRepository
from app.ports.repository import TransactionRepository

_log = logging.getLogger(__name__)

# Maps each non-EUR currency to its yfinance FX ticker ("native per 1 EUR").
# EURUSD=X close = 1.10 means 1 EUR buys 1.10 USD.
_FX_TICKER: dict[Currency, str] = {
    Currency.USD: "EURUSD=X",
    Currency.JPY: "EURJPY=X",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_nav_series(
    start: date,
    end: date,
    *,
    nav_repo: NavSnapshotRepository,
    ohlc_provider: OhlcDataProvider,
    tx_repo: TransactionRepository,
    today: date | None = None,
) -> list[DailyNavPoint]:
    """Return daily NAV points for the closed interval [start, end].

    Historical points (snapshot_date < today) are reconstructed from OHLC history
    and persisted in nav_repo so subsequent calls are fast.
    Today's point is computed from the latest available OHLC close and never persisted.

    Returns an empty list if there are no open positions for any date in the range.
    """
    resolved_today = today or date.today()

    # Split range into historical (can be cached) and live (today only).
    hist_end = min(end, resolved_today - timedelta(days=1))
    include_today = end >= resolved_today

    # Load existing cached historical snapshots.
    cached: list[DailyNavPoint] = []
    if start <= hist_end:
        cached = nav_repo.load_range(start, hist_end)
    cached_dates = {p.snapshot_date for p in cached}

    # Short-circuit if everything is already cached and today is not requested.
    all_transactions = list(tx_repo.load_all())
    if not all_transactions:
        return []

    # Determine which non-EUR currencies appear in the portfolio (for FX fetching).
    currencies_needed: set[Currency] = set()
    for tx in all_transactions:
        currency = infer_currency_from_ticker(tx.ticker)
        if currency != Currency.EUR:
            currencies_needed.add(currency)

    # Determine the period needed to cover the full range.
    period = _period_covering(start, resolved_today)

    # Fetch OHLC for every portfolio ticker + required FX tickers.
    tickers: set[str] = {tx.ticker for tx in all_transactions}
    closes_by_ticker = _fetch_closes(ohlc_provider, tickers, period)
    fx_closes = _fetch_fx_closes(ohlc_provider, currencies_needed, period)

    # Trading days = union of all dates present in any OHLC series.
    all_ohlc_dates: set[date] = set()
    for date_map in closes_by_ticker.values():
        all_ohlc_dates.update(date_map)

    # Reconstruct missing historical trading days.
    missing_hist_dates = sorted(
        d
        for d in all_ohlc_dates
        if start <= d <= hist_end and d not in cached_dates
    )
    new_points: list[DailyNavPoint] = []
    for target_date in missing_hist_dates:
        point = _build_nav_point(
            target_date,
            all_transactions,
            closes_by_ticker,
            fx_closes,
            is_reconstructed=True,
        )
        new_points.append(point)

    if new_points:
        nav_repo.save_points(new_points)

    # Compute today's NAV live (not persisted).
    today_points: list[DailyNavPoint] = []
    if include_today:
        point = _build_nav_point(
            resolved_today,
            all_transactions,
            closes_by_ticker,
            fx_closes,
            is_reconstructed=False,
        )
        today_points = [point]

    all_points = sorted(
        cached + new_points + today_points,
        key=lambda p: p.snapshot_date,
    )
    return all_points


def clear_nav_cache(nav_repo: NavSnapshotRepository) -> None:
    """Drop all persisted NAV snapshots.

    Called via JsonTransactionRepository.save_all after any transaction write
    so the next analytics render triggers a full reconstruction (ADR-003).
    """
    nav_repo.clear()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _period_covering(start: date, as_of: date) -> ChartPeriod:
    """Return the smallest ChartPeriod whose history window covers start→as_of."""
    days = (as_of - start).days
    if days <= 30:
        return ChartPeriod.ONE_MONTH
    if days <= 90:
        return ChartPeriod.THREE_MONTH
    if days <= 180:
        return ChartPeriod.SIX_MONTH
    if days <= 365:
        return ChartPeriod.ONE_YEAR
    if days <= 730:
        return ChartPeriod.TWO_YEAR
    return ChartPeriod.FIVE_YEAR


def _fetch_closes(
    provider: OhlcDataProvider,
    tickers: set[str],
    period: ChartPeriod,
) -> dict[str, dict[date, Decimal]]:
    """Fetch OHLC and return ticker → {date → close_price}."""
    result: dict[str, dict[date, Decimal]] = {}
    for ticker in tickers:
        try:
            series = provider.get_ohlc_history(ticker, period)
            result[ticker] = {bar.timestamp.date(): bar.close for bar in series.bars}
        except OhlcUnavailableError:
            _log.warning(
                "No OHLC data for %s (period=%s); ticker will contribute zero",
                ticker,
                period,
            )
            result[ticker] = {}
    return result


def _fetch_fx_closes(
    provider: OhlcDataProvider,
    currencies: set[Currency],
    period: ChartPeriod,
) -> dict[Currency, dict[date, Decimal]]:
    """Fetch FX tickers and return currency → {date → rate (native per 1 EUR)}."""
    result: dict[Currency, dict[date, Decimal]] = {}
    for currency in currencies:
        fx_ticker = _FX_TICKER.get(currency)
        if fx_ticker is None:
            _log.warning("No FX ticker configured for %s; positions will contribute zero", currency)
            result[currency] = {}
            continue
        try:
            series = provider.get_ohlc_history(fx_ticker, period)
            result[currency] = {bar.timestamp.date(): bar.close for bar in series.bars}
        except OhlcUnavailableError:
            _log.warning(
                "No FX data for %s; %s positions will contribute zero",
                fx_ticker,
                currency,
            )
            result[currency] = {}
    return result


def _closest_close(date_map: dict[date, Decimal], target: date) -> Decimal | None:
    """Return the close on target or the most recent prior close (decision #9)."""
    candidates = [d for d in date_map if d <= target]
    if not candidates:
        return None
    return date_map[max(candidates)]


def _build_nav_point(
    target_date: date,
    transactions: list[Transaction],
    closes_by_ticker: dict[str, dict[date, Decimal]],
    fx_closes: dict[Currency, dict[date, Decimal]],
    *,
    is_reconstructed: bool,
) -> DailyNavPoint:
    """Compute a single DailyNavPoint for target_date."""
    filtered_txs = [tx for tx in transactions if tx.trade_date <= target_date]
    positions = compute_positions(filtered_txs)

    nav_amount = Decimal("0")
    cost_basis_amount = Decimal("0")

    for ticker, position in positions.items():
        cost_basis_amount += position.cost_basis_eur.amount

        close_price = _closest_close(closes_by_ticker.get(ticker, {}), target_date)
        if close_price is None:
            _log.warning(
                "No close price for %s on or before %s; contributing zero to NAV",
                ticker,
                target_date,
            )
            continue

        currency = infer_currency_from_ticker(ticker)

        if currency == Currency.EUR:
            nav_amount += position.open_shares * close_price
        else:
            fx_rate = _closest_close(fx_closes.get(currency, {}), target_date)
            if not fx_rate:
                _log.warning(
                    "No FX rate for %s on or before %s; %s contributes zero to NAV",
                    currency,
                    target_date,
                    ticker,
                )
                continue
            # fx_rate = native-currency per 1 EUR (e.g. EURUSD=X = 1.10 → 1 EUR = 1.10 USD)
            # value_eur = shares * close_native / fx_rate
            nav_amount += position.open_shares * close_price / fx_rate

    return DailyNavPoint(
        snapshot_date=target_date,
        nav_eur=Money(amount=nav_amount, currency=Currency.EUR),
        cost_basis_eur=Money(amount=cost_basis_amount, currency=Currency.EUR),
        n_positions=len(positions),
        is_reconstructed=is_reconstructed,
    )
