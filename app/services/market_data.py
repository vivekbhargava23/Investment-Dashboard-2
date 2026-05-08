"""OHLC market data service with deliberate service-level caching.

This module deviates from the stateless-service convention (TICKET-006).
The cache here is justified because:
  - OHLC histories are large (days × bars per day) and slow to fetch (~600ms).
  - Multiple pages share the same series; per-page Streamlit caching wastes memory.
  - The adapter cache (60s on prices) doesn't fit OHLC's staleness profile.

The cache is invalidated by clear_market_data_caches() — wired into the
Refresh button alongside the price/FX cache invalidation.

Aggregation is applied after fetch so the cache always holds display-ready data:
  - 5D  → daily bars   (avoids intraday-gap artefacts from 15m bars)
  - 1Y/2Y → weekly bars (252 daily bars → 52 weekly; readable candle widths)
  - 5Y  → monthly bars (~60 monthly bars for a 5-year view)
  - YTD → weekly bars  (variable length, weekly gives stable bar count)
"""

import time

from app.domain.market_data import (
    AggregationFreq,
    ChartPeriod,
    OhlcSeries,
    aggregate_ohlc_series,
)
from app.ports.market_data import OhlcDataProvider

_cache: dict[tuple[str, ChartPeriod], tuple[float, OhlcSeries]] = {}

_INTRADAY_TTL = 15 * 60.0
_DAILY_TTL = 24 * 60 * 60.0

# Periods that need coarser bars to look good on a candlestick chart.
# None = keep the yfinance-native interval (daily for 1M–6M, intraday for 1D).
_AGGREGATION: dict[ChartPeriod, AggregationFreq | None] = {
    ChartPeriod.ONE_DAY: None,         # 5m intraday — already readable
    ChartPeriod.FIVE_DAY: "day",       # 15m → 5 daily bars (no gap mess)
    ChartPeriod.ONE_MONTH: None,       # ~22 daily bars — fine
    ChartPeriod.THREE_MONTH: None,     # ~65 daily bars — fine
    ChartPeriod.SIX_MONTH: None,       # ~130 daily bars — acceptable
    ChartPeriod.ONE_YEAR: "week",      # ~252 daily → ~52 weekly
    ChartPeriod.TWO_YEAR: "week",      # ~504 daily → ~104 weekly
    ChartPeriod.FIVE_YEAR: "month",    # ~1260 daily → ~60 monthly
    ChartPeriod.YEAR_TO_DATE: "week",  # variable daily → weekly
}


def _ttl_for_period(period: ChartPeriod) -> float:
    return _INTRADAY_TTL if period.is_intraday else _DAILY_TTL


def get_ohlc_history(
    ticker: str,
    period: ChartPeriod,
    *,
    provider: OhlcDataProvider,
) -> OhlcSeries:
    """Return OHLC history, applying period-appropriate aggregation.

    Aggregated series are cached so the aggregation cost is paid once per TTL.
    Raises OhlcUnavailableError if the provider has no data.
    """
    ticker = ticker.strip().upper()
    key = (ticker, period)
    now = time.monotonic()

    if key in _cache:
        ts, series = _cache[key]
        if now - ts < _ttl_for_period(period):
            return series

    series = provider.get_ohlc_history(ticker, period)

    freq = _AGGREGATION.get(period)
    if freq is not None:
        series = aggregate_ohlc_series(series, freq)

    _cache[key] = (now, series)
    return series


def clear_market_data_caches(provider: OhlcDataProvider) -> None:
    """Clear the service-level OHLC cache and the provider's adapter cache."""
    _cache.clear()
    provider.clear_cache()
