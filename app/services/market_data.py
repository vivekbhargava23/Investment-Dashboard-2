"""OHLC market data service with deliberate service-level caching.

This module deviates from the stateless-service convention (TICKET-006).
The cache here is justified because:
  - OHLC histories are large (days × bars per day) and slow to fetch (~600ms).
  - Multiple pages share the same series; per-page Streamlit caching wastes memory.
  - The adapter cache (60s on prices) doesn't fit OHLC's staleness profile.

The cache is invalidated by clear_market_data_caches() — wired into the
Refresh button alongside the price/FX cache invalidation.
"""

import time

from app.domain.market_data import ChartPeriod, OhlcSeries
from app.ports.market_data import OhlcDataProvider

_cache: dict[tuple[str, ChartPeriod], tuple[float, OhlcSeries]] = {}

_INTRADAY_TTL = 15 * 60.0
_DAILY_TTL = 24 * 60 * 60.0


def _ttl_for_period(period: ChartPeriod) -> float:
    return _INTRADAY_TTL if period.is_intraday else _DAILY_TTL


def get_ohlc_history(
    ticker: str,
    period: ChartPeriod,
    *,
    provider: OhlcDataProvider,
) -> OhlcSeries:
    """Return OHLC history, using the service-level cache to avoid redundant fetches.

    Raises OhlcUnavailableError if the provider has no data — propagated to the caller.
    """
    ticker = ticker.strip().upper()
    key = (ticker, period)
    now = time.monotonic()

    if key in _cache:
        ts, series = _cache[key]
        if now - ts < _ttl_for_period(period):
            return series

    series = provider.get_ohlc_history(ticker, period)
    _cache[key] = (now, series)
    return series


def clear_market_data_caches(provider: OhlcDataProvider) -> None:
    """Clear the service-level OHLC cache and the provider's adapter cache."""
    _cache.clear()
    provider.clear_cache()
