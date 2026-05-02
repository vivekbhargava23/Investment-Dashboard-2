"""
app/services/yfinance_client.py

yfinance wrapper for exchange-suffixed tickers.
Prices are returned in the local currency of the exchange:
  - Frankfurt (.F, .DE) → EUR
  - Tokyo (.T)          → JPY

yfinance is an unofficial API — it can break without notice. If fast_info
fails, the client falls back to a single-day history fetch.
"""

from __future__ import annotations

import math
import time

import yfinance as yf

from app.utils.logger import get_logger

logger = get_logger(__name__)

_CACHE_TTL = 60.0  # seconds
_cache: dict[str, tuple[float, float]] = {}  # ticker → (price, fetched_at)


def get_price(ticker: str) -> float | None:
    """
    Return the current price for a Frankfurt or Tokyo listed ticker.

    Tries fast_info.last_price first (cheapest call). Falls back to the
    most recent close from a 1-day history fetch if fast_info is unavailable.
    Returns None if both attempts fail or return an invalid value.

    Args:
        ticker: Exchange-suffixed ticker e.g. "HY9H.F", "RHM.DE", "5631.T".

    Returns:
        Current price in the exchange's local currency, or None on failure.
    """
    ticker = ticker.strip().upper()
    now = time.monotonic()

    cached = _cache.get(ticker)
    if cached is not None:
        price, fetched_at = cached
        if now - fetched_at < _CACHE_TTL:
            logger.debug("price_cache_hit", ticker=ticker, price=price, source="yfinance")
            return price

    price = _fetch(ticker)

    if price is not None:
        _cache[ticker] = (price, now)
        logger.info("price_fetched", ticker=ticker, price=price, source="yfinance")

    return price


def _fetch(ticker: str) -> float | None:
    """Attempt fast_info then fall back to history. Returns None on any failure."""
    try:
        obj = yf.Ticker(ticker)

        # Primary: fast_info (single lightweight request)
        try:
            price = obj.fast_info.last_price
            if _valid(price):
                return float(price)
        except Exception:
            pass

        # Fallback: most recent close from 1-day history
        hist = obj.history(period="1d")
        if not hist.empty:
            price = hist["Close"].iloc[-1]
            if _valid(price):
                return float(price)

        logger.warning("price_invalid", ticker=ticker, source="yfinance")
        return None

    except Exception as exc:
        logger.error(
            "price_fetch_failed",
            ticker=ticker,
            error=str(exc),
            source="yfinance",
        )
        return None


def _valid(price: object) -> bool:
    """True if price is a finite positive number."""
    try:
        f = float(price)  # type: ignore[arg-type]
        return f > 0 and not math.isnan(f) and not math.isinf(f)
    except (TypeError, ValueError):
        return False


def get_name(ticker: str) -> str | None:
    """
    Return the company long name for any yfinance-compatible ticker.

    Used for display purposes only — not rate-limited or cached here;
    caching is handled by the caller (Streamlit cache_data).

    Args:
        ticker: Any ticker supported by yfinance, e.g. "NVDA", "RHM.DE".

    Returns:
        Long name string, or None if yfinance cannot identify the ticker.
    """
    ticker = ticker.strip().upper()
    try:
        info = yf.Ticker(ticker).info
        name = info.get("longName") or info.get("shortName")
        if name:
            logger.info("name_fetched", ticker=ticker, name=name)
            return str(name)
        logger.warning("name_not_found", ticker=ticker)
        return None
    except Exception as exc:
        logger.error("name_fetch_failed", ticker=ticker, error=str(exc))
        return None


def clear_cache() -> None:
    """Evict all cached prices. Used in tests and on manual refresh."""
    _cache.clear()
