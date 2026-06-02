from __future__ import annotations

import logging

import requests

from app.domain.money import Currency
from app.domain.tickers import UnsupportedTickerError, infer_currency_from_ticker
from app.ports.ticker_resolver import TickerMatch

_log = logging.getLogger(__name__)

_BASE = "https://finnhub.io/api/v1"
_TIMEOUT = 10


class FinnhubTickerResolverAdapter:
    """TickerResolver backed by the Finnhub search and profile endpoints.

    Skips silently if the API key is unset — the CompositeTickerResolver will
    simply operate with yfinance results only.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]:
        query = query.strip()
        if not query or not self._api_key:
            return []

        try:
            resp = requests.get(
                f"{_BASE}/search",
                params={"q": query, "token": self._api_key},
                timeout=_TIMEOUT,
            )
            if resp.status_code == 401:
                _log.warning("Finnhub API key invalid")
                return []
            if resp.status_code == 429:
                _log.warning("Finnhub rate limit hit during resolve")
                return []
            if resp.status_code != 200:
                return []

            data = resp.json()
            results: list[TickerMatch] = []
            for item in data.get("result", []):
                symbol = item.get("displaySymbol") or item.get("symbol", "")
                if not symbol:
                    continue
                match = self._build_match(
                    symbol=symbol,
                    name=item.get("description") or symbol,
                    exchange=item.get("type") or "",
                )
                if match is not None:
                    results.append(match)
                if len(results) >= limit:
                    break
            return results

        except Exception as exc:
            _log.warning("Finnhub resolve failed for %r: %s", query, exc)
            return []

    def lookup(self, symbol: str) -> TickerMatch | None:
        symbol = symbol.strip().upper()
        if not symbol or not self._api_key:
            return None

        try:
            resp = requests.get(
                f"{_BASE}/stock/profile2",
                params={"symbol": symbol, "token": self._api_key},
                timeout=_TIMEOUT,
            )
            if resp.status_code == 401:
                _log.warning("Finnhub API key invalid")
                return None
            if resp.status_code == 429:
                _log.warning("Finnhub rate limit hit during lookup")
                return None
            if resp.status_code != 200:
                return None

            data = resp.json()
            if not data or not data.get("ticker"):
                return None

            return self._build_match(
                symbol=data.get("ticker", symbol),
                name=data.get("name") or symbol,
                exchange=data.get("exchange") or "",
            )

        except Exception as exc:
            _log.warning("Finnhub lookup failed for %r: %s", symbol, exc)
            return None

    def clear_cache(self) -> None:
        pass  # stateless; nothing to clear

    def _build_match(self, symbol: str, name: str, exchange: str) -> TickerMatch | None:
        try:
            currency: Currency = infer_currency_from_ticker(symbol)
        except UnsupportedTickerError:
            return None
        return TickerMatch(
            symbol=symbol,
            name=name,
            exchange=exchange,
            currency=currency,
            recent_price=None,
        )
