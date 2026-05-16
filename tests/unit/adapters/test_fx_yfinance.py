"""Unit tests for FxYfinanceDiskAdapter — cache hit/miss, offline fallback."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.fx_yfinance.adapter import FxYfinanceDiskAdapter
from app.domain.money import Currency
from app.ports.fx_feed import FxRateUnavailableError  # noqa: F401 used in FakeFxProvider

# ─── fake inner provider ──────────────────────────────────────────────────────

class FakeFxProvider:
    def __init__(self, rates: dict[tuple[Currency, Currency, date], Decimal]) -> None:
        self._rates = rates
        self.call_count = 0

    def get_historical_rate(self, base: Currency, quote: Currency, on_date: date) -> Decimal:
        self.call_count += 1
        key = (base, quote, on_date)
        if key not in self._rates:
            raise FxRateUnavailableError(base, quote, on_date, "not in fake")
        return self._rates[key]

    def get_current_rate(self, base: Currency, quote: Currency) -> Decimal:
        raise NotImplementedError

    def clear_cache(self) -> None:
        pass


# ─── helpers ──────────────────────────────────────────────────────────────────

_DATE = date(2026, 3, 15)
_RATE = Decimal("0.922345")


def _make_adapter(cache_dir: Path, inner: FakeFxProvider) -> FxYfinanceDiskAdapter:
    return FxYfinanceDiskAdapter(cache_dir, inner=inner)


# ─── test 1: cache miss → fetches from inner → writes disk ───────────────────

def test_cache_miss_fetches_and_writes_disk(tmp_path: Path) -> None:
    inner = FakeFxProvider({(Currency.USD, Currency.EUR, _DATE): _RATE})
    adapter = _make_adapter(tmp_path, inner)

    rate = adapter.get_historical_rate(Currency.USD, Currency.EUR, _DATE)

    assert rate == _RATE
    assert inner.call_count == 1

    cache_file = tmp_path / "USD_EUR.json"
    assert cache_file.exists()
    data = json.loads(cache_file.read_text())
    assert data[_DATE.isoformat()] == str(_RATE)


# ─── test 2: cache hit on disk → does NOT call inner ─────────────────────────

def test_cache_hit_on_disk_skips_inner(tmp_path: Path) -> None:
    # Pre-populate disk cache
    cache_file = tmp_path / "USD_EUR.json"
    cache_file.write_text(json.dumps({_DATE.isoformat(): str(_RATE)}))

    inner = FakeFxProvider({})  # no rates — would raise if called
    adapter = _make_adapter(tmp_path, inner)

    rate = adapter.get_historical_rate(Currency.USD, Currency.EUR, _DATE)

    assert rate == _RATE
    assert inner.call_count == 0


# ─── test 3: memory cache hit → does NOT open file again ─────────────────────

def test_memory_cache_skips_disk_on_second_call(tmp_path: Path) -> None:
    inner = FakeFxProvider({(Currency.USD, Currency.EUR, _DATE): _RATE})
    adapter = _make_adapter(tmp_path, inner)

    r1 = adapter.get_historical_rate(Currency.USD, Currency.EUR, _DATE)
    r2 = adapter.get_historical_rate(Currency.USD, Currency.EUR, _DATE)

    assert r1 == r2 == _RATE
    assert inner.call_count == 1  # only fetched once


# ─── test 4: clear_cache clears memory but disk still used ───────────────────

def test_clear_cache_clears_memory_only(tmp_path: Path) -> None:
    inner = FakeFxProvider({(Currency.USD, Currency.EUR, _DATE): _RATE})
    adapter = _make_adapter(tmp_path, inner)

    adapter.get_historical_rate(Currency.USD, Currency.EUR, _DATE)
    assert inner.call_count == 1

    adapter.clear_cache()
    # After clearing memory, disk cache is still there → no new inner call
    adapter.get_historical_rate(Currency.USD, Currency.EUR, _DATE)
    assert inner.call_count == 1


# ─── test 5: inner raises → error propagates, no disk write ──────────────────

def test_inner_raises_propagates_error(tmp_path: Path) -> None:
    inner = FakeFxProvider({})  # always raises
    adapter = _make_adapter(tmp_path, inner)

    with pytest.raises(FxRateUnavailableError):
        adapter.get_historical_rate(Currency.USD, Currency.EUR, _DATE)

    cache_file = tmp_path / "USD_EUR.json"
    assert not cache_file.exists()


# ─── test 6: corrupted cache file → treated as miss, fetches from inner ──────

def test_corrupted_cache_treated_as_miss(tmp_path: Path) -> None:
    cache_file = tmp_path / "USD_EUR.json"
    cache_file.write_text("NOT VALID JSON {{{")

    inner = FakeFxProvider({(Currency.USD, Currency.EUR, _DATE): _RATE})
    adapter = _make_adapter(tmp_path, inner)

    rate = adapter.get_historical_rate(Currency.USD, Currency.EUR, _DATE)

    assert rate == _RATE
    assert inner.call_count == 1


# ─── test 7: JPY pair round-trips correctly ───────────────────────────────────

def test_jpy_pair_cached_and_returned(tmp_path: Path) -> None:
    jpy_rate = Decimal("0.006234")
    inner = FakeFxProvider({(Currency.JPY, Currency.EUR, _DATE): jpy_rate})
    adapter = _make_adapter(tmp_path, inner)

    rate = adapter.get_historical_rate(Currency.JPY, Currency.EUR, _DATE)
    assert rate == jpy_rate

    cache_file = tmp_path / "JPY_EUR.json"
    assert cache_file.exists()

    # Second call reads from disk
    adapter2 = _make_adapter(tmp_path, FakeFxProvider({}))
    rate2 = adapter2.get_historical_rate(Currency.JPY, Currency.EUR, _DATE)
    assert rate2 == jpy_rate


# ─── test 8: multiple dates accumulate in same cache file ────────────────────

def test_multiple_dates_in_same_cache_file(tmp_path: Path) -> None:
    date_a = date(2026, 3, 15)
    date_b = date(2026, 4, 10)
    rate_a = Decimal("0.920000")
    rate_b = Decimal("0.915000")

    inner = FakeFxProvider({
        (Currency.USD, Currency.EUR, date_a): rate_a,
        (Currency.USD, Currency.EUR, date_b): rate_b,
    })
    adapter = _make_adapter(tmp_path, inner)

    adapter.get_historical_rate(Currency.USD, Currency.EUR, date_a)
    adapter.get_historical_rate(Currency.USD, Currency.EUR, date_b)

    cache_file = tmp_path / "USD_EUR.json"
    data = json.loads(cache_file.read_text())
    assert data[date_a.isoformat()] == str(rate_a)
    assert data[date_b.isoformat()] == str(rate_b)
