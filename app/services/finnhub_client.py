"""
app/services/finnhub_client.py

Finnhub REST client for US-listed tickers.
Prices are returned in USD — the exchange currency for US equities.

Free tier: 60 requests/minute. The module-level cache ensures at most one
fetch per ticker per 60 seconds, so a 12-position portfolio with 9 US tickers
uses at most 9 req/min on refresh — well within the limit.
"""

from __future__ import annotations

import math
import time
from functools import lru_cache

import finnhub

from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_CACHE_TTL = 60.0  # seconds — matches default price_refresh_interval_seconds
_cache: dict[str, tuple[float, float]] = {}  # ticker → (price, fetched_at)


@lru_cache(maxsize=1)
def _client() -> finnhub.Client:
    return finnhub.Client(api_key=get_settings().finnhub_api_key)


def get_price(ticker: str) -> float | None:
    """
    Return the current USD price for a US-listed ticker.

    Checks the in-process cache first. On a cache miss, fetches from Finnhub
    and stores the result. Returns None if the fetch fails or Finnhub returns
    an invalid quote (price of 0 means the market is closed or the ticker is
    unrecognised).

    Args:
        ticker: US ticker symbol e.g. "NVDA", "MRVL".

    Returns:
        Current price in USD, or None on failure.
    """
    ticker = ticker.strip().upper()
    now = time.monotonic()

    cached = _cache.get(ticker)
    if cached is not None:
        price, fetched_at = cached
        if now - fetched_at < _CACHE_TTL:
            logger.debug("price_cache_hit", ticker=ticker, price=price, source="finnhub")
            return price

    try:
        quote = _client().quote(ticker)
        price = quote.get("c")  # current price field

        if not price or math.isnan(price):
            logger.warning(
                "price_invalid",
                ticker=ticker,
                quote=quote,
                source="finnhub",
            )
            return None

        _cache[ticker] = (price, now)
        logger.info("price_fetched", ticker=ticker, price=price, source="finnhub")
        return float(price)

    except Exception as exc:
        logger.error(
            "price_fetch_failed",
            ticker=ticker,
            error=str(exc),
            source="finnhub",
        )
        return None


def clear_cache() -> None:
    """Evict all cached prices. Used in tests and on manual refresh."""
    _cache.clear()
