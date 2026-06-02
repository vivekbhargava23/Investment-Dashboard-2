from __future__ import annotations

import logging

from app.ports.ticker_resolver import TickerMatch, TickerResolver

_log = logging.getLogger(__name__)


class CompositeTickerResolver:
    """Fan-out resolver: primary first, then fallbacks fill the gap.

    resolve: calls primary; if results < limit, calls each fallback in order and
    merges by symbol (dedup; primary wins on conflict). Returns up to limit.

    lookup: calls primary; if None, tries fallbacks in order; returns first non-None.

    Each adapter's exceptions are caught individually so one source down cannot
    break the composite.
    """

    def __init__(
        self,
        primary: TickerResolver,
        fallbacks: list[TickerResolver],
    ) -> None:
        self._primary = primary
        self._fallbacks = fallbacks

    def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]:
        primary_results: list[TickerMatch] = []
        try:
            primary_results = self._primary.resolve(query, limit)
        except Exception as exc:
            _log.warning("CompositeTickerResolver primary.resolve failed: %s", exc)

        if len(primary_results) >= limit:
            return primary_results[:limit]

        seen: dict[str, TickerMatch] = {m.symbol.upper(): m for m in primary_results}

        for fallback in self._fallbacks:
            if len(seen) >= limit:
                break
            needed = limit - len(seen)
            try:
                fb_results = fallback.resolve(query, needed)
            except Exception as exc:
                _log.warning("CompositeTickerResolver fallback.resolve failed: %s", exc)
                continue
            for m in fb_results:
                key = m.symbol.upper()
                if key not in seen:
                    seen[key] = m
                if len(seen) >= limit:
                    break

        primary_keys = [m.symbol.upper() for m in primary_results]
        ordered = list(primary_results)
        for key, match in seen.items():
            if key not in primary_keys:
                ordered.append(match)

        return ordered[:limit]

    def lookup(self, symbol: str) -> TickerMatch | None:
        try:
            result = self._primary.lookup(symbol)
            if result is not None:
                return result
        except Exception as exc:
            _log.warning("CompositeTickerResolver primary.lookup failed: %s", exc)

        for fallback in self._fallbacks:
            try:
                result = fallback.lookup(symbol)
                if result is not None:
                    return result
            except Exception as exc:
                _log.warning("CompositeTickerResolver fallback.lookup failed: %s", exc)

        return None

    def clear_cache(self) -> None:
        try:
            self._primary.clear_cache()
        except Exception as exc:
            _log.warning("CompositeTickerResolver primary.clear_cache failed: %s", exc)
        for fallback in self._fallbacks:
            try:
                fallback.clear_cache()
            except Exception as exc:
                _log.warning("CompositeTickerResolver fallback.clear_cache failed: %s", exc)
