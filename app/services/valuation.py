import time
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from app.domain.fifo import compute_positions
from app.domain.models import Transaction
from app.domain.money import Currency, Money
from app.domain.positions import LivePosition, PortfolioSummary
from app.ports.fx_feed import FxRateUnavailableError, LiveFxProvider
from app.ports.price_feed import PriceProvider
from app.ports.repository import TransactionRepository

# Module-level TTL cache for live positions. Process-global; not safe for multi-tenant use
# (this is a single-user Streamlit app). Keyed by transactions signature so a portfolio
# change automatically causes a cache miss.
_live_positions_cache: dict[str, tuple[float, dict[str, LivePosition]]] = {}
_TTL_SECONDS = 60.0


def _tx_sig(transactions: list[Transaction]) -> str:
    """Stable key over a transaction list; changes when any tx is added or removed."""
    if not transactions:
        return "empty"
    sorted_ids = sorted(str(tx.id) for tx in transactions)
    return f"{len(transactions)}:{sorted_ids[-1]}"


def _live_fx_rates(
    currencies: set[Currency], fx_provider: LiveFxProvider
) -> dict[Currency, Decimal]:
    """Fetch one EUR->ccy rate per distinct non-EUR currency.

    Returns ccy -> rate where rate is "native per 1 EUR" (as the provider reports).
    Currencies whose rate is unavailable are omitted (callers treat absence as stale).
    """
    rates: dict[Currency, Decimal] = {}
    for ccy in currencies:
        try:
            rates[ccy] = fx_provider.get_current_rate(Currency.EUR, ccy)
        except FxRateUnavailableError:
            continue
    return rates


def compute_live_positions(
    transactions: Sequence[Transaction],
    price_provider: PriceProvider,
    fx_provider: LiveFxProvider,
    as_of: date,
) -> dict[str, LivePosition]:
    """
    Orchestrates FIFO position computation and live valuation.

    Prices are fetched in a single batch; FX rates are fetched once per distinct
    non-EUR currency. A position is stale if its price is missing or its currency's
    FX rate is unavailable. ``as_of`` is the valuation date (typically today); it is
    threaded into FIFO so YTD realised gains reflect the correct calendar year.
    """
    positions = compute_positions(transactions, as_of)
    live_positions: dict[str, LivePosition] = {}

    # One batched price fetch for the whole portfolio. Missing tickers are absent.
    prices = price_provider.get_current_prices(list(positions.keys()))

    # One FX fetch per distinct foreign currency actually present in the live prices.
    foreign_currencies: set[Currency] = {
        price.currency for price in prices.values() if price.currency != Currency.EUR
    }
    fx_rates = _live_fx_rates(foreign_currencies, fx_provider)

    for ticker, position in positions.items():
        live_price_native: Money | None = None
        live_value_eur: Money | None = None
        unrealised_gain_eur: Money | None = None
        unrealised_gain_pct: Decimal | None = None
        current_fx_rate: Decimal | None = None
        staleness_reason: str | None = None

        try:
            live_price_native = prices.get(ticker)

            if live_price_native is None:
                staleness_reason = "Live price unavailable"
            elif live_price_native.currency == Currency.EUR:
                live_value_eur = Money(
                    amount=position.open_shares * live_price_native.amount,
                    currency=Currency.EUR,
                )
            else:
                ccy = live_price_native.currency
                native_per_eur = fx_rates.get(ccy)
                if native_per_eur is not None:
                    # Provider rate is "native per 1 EUR"; invert to EUR per 1 native.
                    rate_eur_per_native = Decimal("1") / native_per_eur
                    current_fx_rate = rate_eur_per_native
                    live_value_eur = Money(
                        amount=position.open_shares
                        * live_price_native.amount
                        * rate_eur_per_native,
                        currency=Currency.EUR,
                    )
                else:
                    staleness_reason = f"FX rate {ccy}/EUR unavailable"

            if live_value_eur is not None:
                unrealised_gain_eur = Money(
                    amount=live_value_eur.amount - position.cost_basis_eur.amount,
                    currency=Currency.EUR,
                )
                if position.cost_basis_eur.amount > 0:
                    unrealised_gain_pct = (
                        unrealised_gain_eur.amount / position.cost_basis_eur.amount
                    ) * Decimal("100")
                else:
                    unrealised_gain_pct = None

        except Exception as e:
            staleness_reason = str(e)
            live_price_native = None
            live_value_eur = None
            unrealised_gain_eur = None
            unrealised_gain_pct = None
            current_fx_rate = None

        live_positions[ticker] = LivePosition(
            position=position,
            live_price_native=live_price_native,
            live_value_eur=live_value_eur,
            unrealised_gain_eur=unrealised_gain_eur,
            unrealised_gain_pct=unrealised_gain_pct,
            current_fx_rate=current_fx_rate,
            staleness_reason=staleness_reason,
        )

    return live_positions


def get_live_positions_cached(
    *,
    repo: TransactionRepository,
    price_provider: PriceProvider,
    fx_provider: LiveFxProvider,
    as_of: date,
    ttl_seconds: float = _TTL_SECONDS,
) -> dict[str, LivePosition]:
    """Module-level TTL cache keyed by transactions signature and valuation date.

    Single source of truth across all UI pages. Process-global — not safe for
    multi-tenant use; this app is single-user. ``as_of`` is part of the cache key so
    a day (and year) rollover does not serve a stale YTD figure.
    """
    transactions = repo.load_all()
    key = f"{_tx_sig(transactions)}@{as_of.isoformat()}"
    now = time.monotonic()

    if key in _live_positions_cache:
        ts, cached = _live_positions_cache[key]
        if now - ts < ttl_seconds:
            return cached

    result = compute_live_positions(transactions, price_provider, fx_provider, as_of)
    _live_positions_cache[key] = (now, result)
    return result


def clear_live_positions_cache() -> None:
    """Invalidate the module-level live-positions cache."""
    _live_positions_cache.clear()


def compute_portfolio_summary(
    live_positions: dict[str, LivePosition],
    as_of: datetime,
) -> PortfolioSummary:
    """
    Aggregates live positions into a portfolio-wide summary.
    """
    total_value_amount = Decimal("0")
    total_cost_basis_live_subset_amount = Decimal("0")
    total_cost_basis_all_amount = Decimal("0")
    total_realised_gain_ytd_amount = Decimal("0")
    live_position_count = 0
    position_count = len(live_positions)

    for lp in live_positions.values():
        total_cost_basis_all_amount += lp.position.cost_basis_eur.amount
        total_realised_gain_ytd_amount += lp.position.realised_gain_eur_ytd.amount

        if not lp.is_stale and lp.live_value_eur is not None:
            total_value_amount += lp.live_value_eur.amount
            total_cost_basis_live_subset_amount += lp.position.cost_basis_eur.amount
            live_position_count += 1

    total_unrealised_gain_amount = total_value_amount - total_cost_basis_live_subset_amount
    if total_cost_basis_live_subset_amount > 0:
        total_unrealised_gain_pct = (
            total_unrealised_gain_amount / total_cost_basis_live_subset_amount
        ) * Decimal("100")
    else:
        total_unrealised_gain_pct = Decimal("0")

    staleness: Literal["live", "partial", "stale"]
    if position_count == 0:
        staleness = "live"
    elif live_position_count == position_count:
        staleness = "live"
    elif live_position_count == 0:
        staleness = "stale"
    else:
        staleness = "partial"

    return PortfolioSummary(
        total_value_eur=Money(amount=total_value_amount, currency=Currency.EUR),
        total_cost_basis_eur=Money(amount=total_cost_basis_all_amount, currency=Currency.EUR),
        total_unrealised_gain_eur=Money(
            amount=total_unrealised_gain_amount, currency=Currency.EUR
        ),
        total_unrealised_gain_pct=total_unrealised_gain_pct,
        total_realised_gain_eur_ytd=Money(
            amount=total_realised_gain_ytd_amount, currency=Currency.EUR
        ),
        position_count=position_count,
        live_position_count=live_position_count,
        staleness=staleness,
        as_of=as_of,
    )


def clear_caches(
    price_provider: PriceProvider,
    fx_provider: LiveFxProvider,
) -> None:
    """
    Invalidates caches in the underlying providers.
    """
    price_provider.clear_cache()
    fx_provider.clear_cache()
