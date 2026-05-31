import logging
import time
from decimal import Decimal
from typing import Any

from app.adapters._yfinance_client import yf
from app.domain.money import Currency, Money
from app.domain.tickers import UnsupportedTickerError, infer_currency_from_ticker
from app.ports.ticker_resolver import TickerMatch

_log = logging.getLogger(__name__)

_RESOLVER_TTL = 3600  # 1 hour — ticker metadata changes rarely


class YfinanceResolverAdapter:
    """TickerResolver backed by yfinance with in-memory TTL cache."""

    def __init__(self) -> None:
        self._resolver_cache: dict[str, tuple[float, Any]] = {}

    def _build_match(
        self,
        symbol: str,
        name: str,
        exchange: str,
        *,
        fetch_price: bool = True,
    ) -> TickerMatch | None:
        """Return a TickerMatch, or None if the ticker's currency is unsupported."""
        try:
            inferred: Currency = infer_currency_from_ticker(symbol)
        except UnsupportedTickerError:
            return None

        recent_price: Money | None = None
        if fetch_price:
            try:
                fi = yf.Ticker(symbol).fast_info
                raw = fi.get("lastPrice")
                if raw is not None and not (isinstance(raw, float) and raw != raw):
                    recent_price = Money(
                        amount=Decimal(str(raw)).quantize(Decimal("0.0001")),
                        currency=inferred,
                    )
            except Exception:
                pass  # recent_price stays None — non-critical

        return TickerMatch(
            symbol=symbol,
            name=name,
            exchange=exchange,
            currency=inferred,
            recent_price=recent_price,
        )

    def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]:
        """Fuzzy/prefix search for tickers matching *query*."""
        query = query.strip()
        if not query:
            return []

        cache_key = f"resolve:{query.upper()}:{limit}"
        now = time.monotonic()
        if cache_key in self._resolver_cache:
            ts, cached = self._resolver_cache[cache_key]
            if now - ts < _RESOLVER_TTL:
                return list(cached)

        results: list[TickerMatch] = []
        try:
            quotes = yf.Search(query, max_results=limit).quotes
            for q in quotes:
                symbol = q.get("symbol", "")
                if not symbol:
                    continue
                name = q.get("longname") or q.get("shortname") or symbol
                exchange = q.get("exchDisp") or q.get("exchange") or ""
                match = self._build_match(symbol, name, exchange, fetch_price=False)
                if match is not None:
                    results.append(match)
                if len(results) >= limit:
                    break
        except Exception as exc:
            _log.warning("yfinance Search failed for %r: %s", query, exc)

        self._resolver_cache[cache_key] = (now, results)
        return results

    def lookup(self, symbol: str) -> TickerMatch | None:
        """Exact-symbol metadata lookup."""
        symbol = symbol.strip().upper()
        if not symbol:
            return None

        cache_key = f"lookup:{symbol}"
        now = time.monotonic()
        if cache_key in self._resolver_cache:
            ts, cached = self._resolver_cache[cache_key]
            if now - ts < _RESOLVER_TTL:
                return cached if isinstance(cached, TickerMatch) else None

        result: TickerMatch | None = None
        try:
            info = yf.Ticker(symbol).info
            if info and info.get("symbol"):
                name = info.get("longName") or info.get("shortName") or symbol
                exchange = info.get("exchange") or ""
                result = self._build_match(symbol, name, exchange)
        except Exception as exc:
            _log.warning("yfinance Ticker.info failed for %r: %s", symbol, exc)

        self._resolver_cache[cache_key] = (now, result)
        return result

    def clear_cache(self) -> None:
        self._resolver_cache.clear()
