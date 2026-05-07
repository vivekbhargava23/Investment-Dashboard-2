"""OHLC market data service with deliberate service-level caching.

This module deviates from the stateless-service convention (TICKET-006).
The cache here is justified because:
  - OHLC histories are large (days x bars per day) and slow to fetch.
  - Multiple pages share the same series; per-page Streamlit caching wastes memory.
  - The adapter cache for current prices does not fit OHLC's staleness profile.

The cache is invalidated by clear_market_data_caches(), wired into the same refresh
flow as other market-data cache invalidation.
"""

import time

from app.domain.market_data import ChartPeriod, OhlcSeries
from app.ports.market_data import OhlcDataProvider

_cache: dict[tuple[str, ChartPeriod], tuple[float, OhlcSeries]] = {}


def _ttl_for_period(period: ChartPeriod) -> float:
    if period.is_intraday:
        return 15 * 60
    return 24 * 60 * 60


def get_ohlc_history(
    ticker: str,
    period: ChartPeriod,
    *,
    provider: OhlcDataProvider,
) -> OhlcSeries:
    normalized_ticker = ticker.strip().upper()
    cache_key = (normalized_ticker, period)
    now = time.monotonic()

    if cache_key in _cache:
        cached_at, cached = _cache[cache_key]
        if now - cached_at < _ttl_for_period(period):
            return cached

    series = provider.get_ohlc_history(normalized_ticker, period)
    _cache[cache_key] = (now, series)
    return series


def clear_market_data_caches(provider: OhlcDataProvider) -> None:
    _cache.clear()
    provider.clear_cache()
