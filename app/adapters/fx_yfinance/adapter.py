"""Disk-cached FX rate adapter backed by yfinance.

Historical rates are cached indefinitely once written (history is immutable).
Cache files live at {cache_dir}/{FROM}_{TO}.json, one file per currency pair.
"""
from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.domain.money import Currency
from app.ports.fx_feed import FxProvider


class FxYfinanceDiskAdapter:
    """FxProvider wrapping an inner provider (defaults to YfinanceAdapter) with disk cache."""

    def __init__(self, cache_dir: Path, *, inner: FxProvider | None = None) -> None:
        self._cache_dir = cache_dir
        self._inner = inner
        self._memory: dict[str, Decimal] = {}

    # ------------------------------------------------------------------
    # FxProvider protocol
    # ------------------------------------------------------------------

    def get_historical_rate(self, base: Currency, quote: Currency, on_date: date) -> Decimal:
        key = f"{base}/{quote}/{on_date.isoformat()}"
        if key in self._memory:
            return self._memory[key]

        cached = self._read_from_disk(base, quote, on_date)
        if cached is not None:
            self._memory[key] = cached
            return cached

        rate = self._get_inner().get_historical_rate(base, quote, on_date)
        self._write_to_disk(base, quote, on_date, rate)
        self._memory[key] = rate
        return rate

    def get_current_rate(self, base: Currency, quote: Currency) -> Decimal:
        return self._get_inner().get_current_rate(base, quote)

    def clear_cache(self) -> None:
        self._memory.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_inner(self) -> FxProvider:
        if self._inner is None:
            from app.adapters.yfinance_feed import YfinanceAdapter
            self._inner = YfinanceAdapter()
        return self._inner

    def _cache_path(self, base: Currency, quote: Currency) -> Path:
        return self._cache_dir / f"{base}_{quote}.json"

    def _read_from_disk(self, base: Currency, quote: Currency, on_date: date) -> Decimal | None:
        path = self._cache_path(base, quote)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data: dict[str, str] = json.load(f)
            val = data.get(on_date.isoformat())
            return Decimal(val) if val is not None else None
        except Exception:
            return None

    def _write_to_disk(self, base: Currency, quote: Currency, on_date: date, rate: Decimal) -> None:
        path = self._cache_path(base, quote)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    data: dict[str, str] = json.load(f)
            else:
                data = {}
            data[on_date.isoformat()] = str(rate)
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            os.replace(tmp, path)
        except Exception:
            pass  # cache write failure is non-fatal
