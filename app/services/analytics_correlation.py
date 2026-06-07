from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict

from app.domain import analytics
from app.domain.market_data import ChartPeriod, OhlcSeries
from app.ports.fx_feed import LiveFxProvider
from app.ports.market_data import OhlcDataProvider
from app.ports.price_feed import PriceProvider
from app.ports.repository import TransactionRepository
from app.services.valuation import compute_live_positions

CLUSTER_THRESHOLD: Final[Decimal] = Decimal("0.6")
MIN_CLUSTER_SIZE: Final[int] = 3
DIVERSIFICATION_BUCKETS: Final[tuple[tuple[Decimal, str, str], ...]] = (
    (Decimal("0.2"), "high", "green"),
    (Decimal("0.4"), "moderate", "amber"),
    (Decimal("0.6"), "low", "amber"),
)


class SkippedTicker(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    available_days: int
    required_days: int


class CorrelationView(BaseModel):
    model_config = ConfigDict(frozen=True)

    matrix: dict[str, dict[str, Decimal]]
    included_tickers: list[str]
    skipped: list[SkippedTicker]
    avg_correlation: dict[str, Decimal]
    clusters: list[list[str]]


def diversification_bucket(avg_corr: Decimal) -> tuple[str, str]:
    for upper_bound, label, colour_token in DIVERSIFICATION_BUCKETS:
        if avg_corr < upper_bound:
            return label, colour_token
    return "very low", "red"


def build_correlation_view(
    *,
    repo: TransactionRepository,
    price_feed: PriceProvider,
    fx_feed: LiveFxProvider,
    ohlc: OhlcDataProvider,
    as_of: date,
    window_days: int,
) -> CorrelationView:
    live_positions = compute_live_positions(repo.load_all(), price_feed, fx_feed, as_of)
    live_tickers = sorted(
        ticker
        for ticker, live_position in live_positions.items()
        if live_position.position.open_shares > 0
    )
    if not live_tickers:
        return CorrelationView(
            matrix={},
            included_tickers=[],
            skipped=[],
            avg_correlation={},
            clusters=[],
        )

    # One batched OHLC fetch for every included ticker (was N serial round-trips).
    series_map = ohlc.get_ohlc_histories(live_tickers, _period_for_window(window_days))

    closes_by_ticker: dict[str, dict[date, Decimal]] = {}
    skipped: list[SkippedTicker] = []
    minimum_days = max(2, window_days - 1)
    for ticker in live_tickers:
        series = series_map.get(ticker)
        daily_closes = _daily_closes_from_series(series, as_of) if series else {}
        available_days = len(daily_closes)
        if available_days < minimum_days:
            skipped.append(
                SkippedTicker(
                    ticker=ticker,
                    available_days=available_days,
                    required_days=window_days,
                )
            )
            continue
        closes_by_ticker[ticker] = dict(sorted(daily_closes.items())[-window_days:])

    included_tickers = sorted(closes_by_ticker)
    if not included_tickers:
        return CorrelationView(
            matrix={},
            included_tickers=[],
            skipped=sorted(skipped, key=lambda item: item.ticker),
            avg_correlation={},
            clusters=[],
        )

    aligned_closes = _aligned_closes(closes_by_ticker)
    returns_by_ticker = {
        ticker: analytics.daily_returns(aligned_closes[ticker])
        for ticker in included_tickers
    }
    matrix = analytics.correlation_matrix(returns_by_ticker)
    avg_correlation = _average_correlation(matrix)
    clusters = analytics.correlation_clusters(
        matrix,
        threshold=CLUSTER_THRESHOLD,
        min_size=MIN_CLUSTER_SIZE,
    )

    return CorrelationView(
        matrix=matrix,
        included_tickers=included_tickers,
        skipped=sorted(skipped, key=lambda item: item.ticker),
        avg_correlation=avg_correlation,
        clusters=clusters,
    )


def _period_for_window(window_days: int) -> ChartPeriod:
    if window_days <= 30:
        return ChartPeriod.THREE_MONTH
    if window_days <= 90:
        return ChartPeriod.SIX_MONTH
    return ChartPeriod.ONE_YEAR


def _daily_closes_from_series(
    series: OhlcSeries,
    as_of: date,
) -> dict[date, Decimal]:
    closes: dict[date, Decimal] = {}
    for bar in series.bars:
        day = bar.timestamp.date()
        if day <= as_of:
            closes[day] = bar.close
    return closes


def _aligned_closes(
    closes_by_ticker: dict[str, dict[date, Decimal]],
) -> dict[str, list[Decimal]]:
    common_dates: set[date] | None = None
    for daily_closes in closes_by_ticker.values():
        dates = set(daily_closes)
        common_dates = dates if common_dates is None else common_dates & dates

    sorted_common_dates = sorted(common_dates or set())
    return {
        ticker: [daily_closes[day] for day in sorted_common_dates]
        for ticker, daily_closes in closes_by_ticker.items()
    }


def _average_correlation(
    matrix: dict[str, dict[str, Decimal]],
) -> dict[str, Decimal]:
    if len(matrix) < 2:
        return {}

    averages: dict[str, Decimal] = {}
    for ticker, row in matrix.items():
        peers = [value for peer, value in row.items() if peer != ticker]
        if peers:
            averages[ticker] = sum(peers, Decimal("0")) / Decimal(len(peers))
    return averages
