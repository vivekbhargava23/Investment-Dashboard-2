import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.ports.ticker_resolver import TickerMatch, TickerResolver

CACHE_VERSION = 1
CACHE_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


class CachedTickerResolver:
    """Decorator that persists TickerResolver results to disk.

    Implements the TickerResolver Protocol by delegating to an inner provider
    and caching results to a JSON file. Cache hits avoid the network entirely.
    Cache misses fetch from the inner provider, persist, then return.
    """

    def __init__(self, inner: TickerResolver, cache_path: Path) -> None:
        self._inner = inner
        self._cache_path = cache_path
        self._cache: dict[str, Any] | None = None

    def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]:
        query = query.strip().upper()
        if not query:
            return []
        key = f"resolve:{query.lower()}"
        self._load_cache()
        assert self._cache is not None
        entry = self._cache.get(key)
        if entry is not None and self._is_fresh(entry):
            return [TickerMatch.model_validate(m) for m in entry["results"]][:limit]
        matches = self._inner.resolve(query, limit)
        self._cache[key] = {
            "results": [m.model_dump(mode="json") for m in matches],
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        self._write_cache()
        return matches

    def lookup(self, symbol: str) -> TickerMatch | None:
        symbol = symbol.strip().upper()
        if not symbol:
            return None
        key = f"lookup:{symbol}"
        self._load_cache()
        assert self._cache is not None
        entry = self._cache.get(key)
        if entry is not None and self._is_fresh(entry):
            raw = entry.get("result")
            return TickerMatch.model_validate(raw) if raw is not None else None
        result = self._inner.lookup(symbol)
        self._cache[key] = {
            "result": result.model_dump(mode="json") if result is not None else None,
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        self._write_cache()
        return result

    def clear_cache(self) -> None:
        self._inner.clear_cache()
        self._cache = {}
        self._write_cache()

    def _is_fresh(self, entry: dict[str, Any]) -> bool:
        try:
            fetched_at = datetime.fromisoformat(entry["fetched_at"])
            age = (datetime.now(UTC) - fetched_at).total_seconds()
            return age < CACHE_TTL_SECONDS
        except (KeyError, ValueError):
            return False

    def _load_cache(self) -> None:
        if self._cache is not None:
            return
        if not self._cache_path.exists():
            self._cache = {}
            return
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if data.get("_version") != CACHE_VERSION:
                logging.info("Ticker cache version mismatch, ignoring")
                self._cache = {}
                return
            self._cache = data.get("entries", {})
        except (json.JSONDecodeError, OSError) as exc:
            logging.warning("Ticker cache load failed: %s", exc)
            self._cache = {}

    def _write_cache(self) -> None:
        assert self._cache is not None
        # TODO(TICKET-021b): periodic compaction — drop entries older than TTL
        try:
            parent = self._cache_path.parent
            parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path_str = tempfile.mkstemp(dir=parent, suffix=".tmp")
            tmp_path = Path(tmp_path_str)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(
                        {"_version": CACHE_VERSION, "entries": self._cache},
                        f,
                        ensure_ascii=False,
                    )
                os.replace(tmp_path, self._cache_path)
            except Exception:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
                raise
        except Exception as exc:
            logging.warning("Ticker cache write failed: %s", exc)
