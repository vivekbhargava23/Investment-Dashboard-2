"""Unit tests for CachedTickerResolver. Zero network access — uses FakeTickerResolver."""
import json
import logging
import os
import stat
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.ticker_resolver_cached import CACHE_VERSION, CachedTickerResolver
from app.domain.money import Currency, Money
from app.ports.ticker_resolver import TickerMatch
from tests.fakes.ticker_resolver import FakeTickerResolver


def _make_match(symbol: str = "APD", currency: Currency = Currency.USD) -> TickerMatch:
    return TickerMatch(
        symbol=symbol,
        name=f"{symbol} Corp",
        exchange="NYSE",
        currency=currency,
        recent_price=None,
    )


def _make_cached(
    inner: FakeTickerResolver, tmp_path: Path, filename: str = "cache.json"
) -> CachedTickerResolver:
    return CachedTickerResolver(inner=inner, cache_path=tmp_path / filename)


def _read_entries(path: Path) -> dict:
    return json.loads(path.read_text())["entries"]


def _stale_timestamp() -> str:
    return (datetime.now(UTC) - timedelta(days=31)).isoformat()


# ---------------------------------------------------------------------------
# Cache miss / hit
# ---------------------------------------------------------------------------

def test_cache_miss_calls_inner_and_persists(tmp_path: Path) -> None:
    fake = FakeTickerResolver([_make_match("APD")])
    cached = _make_cached(fake, tmp_path)

    result = cached.resolve("APD")

    assert fake.resolve_call_count == 1
    assert len(result) == 1
    assert result[0].symbol == "APD"
    cache_file = tmp_path / "cache.json"
    assert cache_file.exists()
    entries = _read_entries(cache_file)
    assert "resolve:apd" in entries


def test_cache_hit_skips_inner(tmp_path: Path) -> None:
    fake = FakeTickerResolver([_make_match("APD")])
    cached = _make_cached(fake, tmp_path)

    cached.resolve("APD")
    assert fake.resolve_call_count == 1

    result = cached.resolve("APD")
    assert fake.resolve_call_count == 1  # no second call
    assert result[0].symbol == "APD"


def test_stale_entry_treated_as_miss(tmp_path: Path) -> None:
    fake = FakeTickerResolver([_make_match("APD")])
    cached = _make_cached(fake, tmp_path)

    cached.resolve("APD")
    assert fake.resolve_call_count == 1

    # Manually backdate the cached entry
    cache_file = tmp_path / "cache.json"
    data = json.loads(cache_file.read_text())
    data["entries"]["resolve:apd"]["fetched_at"] = _stale_timestamp()
    cache_file.write_text(json.dumps(data))

    # New instance so _cache is reloaded from disk
    cached2 = CachedTickerResolver(inner=fake, cache_path=cache_file)
    cached2.resolve("APD")
    assert fake.resolve_call_count == 2


# ---------------------------------------------------------------------------
# Negative caching for lookup
# ---------------------------------------------------------------------------

def test_negative_caching_for_lookup(tmp_path: Path) -> None:
    fake = FakeTickerResolver([])  # no matches → lookup returns None
    cached = _make_cached(fake, tmp_path)

    result1 = cached.lookup("XQYZ")
    assert result1 is None
    assert fake.lookup_call_count == 1

    result2 = cached.lookup("XQYZ")
    assert result2 is None
    assert fake.lookup_call_count == 1  # served from cache


def test_lookup_hit_positive(tmp_path: Path) -> None:
    fake = FakeTickerResolver([_make_match("APD")])
    cached = _make_cached(fake, tmp_path)

    cached.lookup("APD")
    assert fake.lookup_call_count == 1

    result = cached.lookup("APD")
    assert result is not None and result.symbol == "APD"
    assert fake.lookup_call_count == 1


# ---------------------------------------------------------------------------
# clear_cache
# ---------------------------------------------------------------------------

def test_clear_cache_resets_both_layers(tmp_path: Path) -> None:
    fake = FakeTickerResolver([_make_match("APD")])
    cached = _make_cached(fake, tmp_path)

    cached.resolve("APD")
    cached.clear_cache()

    assert fake._cache_cleared_count == 1
    cache_file = tmp_path / "cache.json"
    data = json.loads(cache_file.read_text())
    assert data == {"_version": CACHE_VERSION, "entries": {}}

    cached.resolve("APD")
    assert fake.resolve_call_count == 2  # fetched anew after clear


# ---------------------------------------------------------------------------
# Best-effort write (unwritable path)
# ---------------------------------------------------------------------------

def test_unwritable_path_does_not_raise(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    ro_dir = tmp_path / "ro_dir"
    ro_dir.mkdir()
    os.chmod(ro_dir, stat.S_IREAD | stat.S_IEXEC)

    fake = FakeTickerResolver([_make_match("APD")])
    cache_path = ro_dir / "cache.json"
    cached = CachedTickerResolver(inner=fake, cache_path=cache_path)

    with caplog.at_level(logging.WARNING):
        result = cached.resolve("APD")

    assert result[0].symbol == "APD"
    assert any("Ticker cache write failed" in r.message for r in caplog.records)

    # Restore permissions so tmp_path cleanup succeeds
    os.chmod(ro_dir, stat.S_IRWXU)


# ---------------------------------------------------------------------------
# Malformed / wrong-version cache file
# ---------------------------------------------------------------------------

def test_malformed_cache_file_ignored(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    cache_file = tmp_path / "cache.json"
    cache_file.write_text("{garbage")

    fake = FakeTickerResolver([_make_match("APD")])
    cached = CachedTickerResolver(inner=fake, cache_path=cache_file)

    with caplog.at_level(logging.WARNING):
        result = cached.resolve("APD")

    assert result[0].symbol == "APD"
    assert fake.resolve_call_count == 1
    # File is now valid JSON with the new entry
    data = json.loads(cache_file.read_text())
    assert "resolve:apd" in data["entries"]


def test_wrong_cache_version_ignored(tmp_path: Path) -> None:
    cache_file = tmp_path / "cache.json"
    cache_file.write_text(json.dumps({
        "_version": 999,
        "entries": {"resolve:apd": {"results": [], "fetched_at": datetime.now(UTC).isoformat()}},
    }))

    fake = FakeTickerResolver([_make_match("APD")])
    cached = CachedTickerResolver(inner=fake, cache_path=cache_file)
    cached.resolve("APD")

    assert fake.resolve_call_count == 1  # cache discarded due to version mismatch


# ---------------------------------------------------------------------------
# Round-trip integrity across all Currency enum values
# ---------------------------------------------------------------------------

def test_round_trip_all_currencies(tmp_path: Path) -> None:
    matches = [
        TickerMatch(
            symbol=f"T.{c.value}",
            name=f"Test {c.value}",
            exchange="X",
            currency=c,
            recent_price=Money(amount=Decimal("10"), currency=c),
        )
        for c in Currency
    ]
    fake = FakeTickerResolver(matches)
    cache_file = tmp_path / "cache.json"
    cached = CachedTickerResolver(inner=fake, cache_path=cache_file)

    # Prime cache for each currency's symbol
    for m in matches:
        cached.lookup(m.symbol)

    # Reload from disk and verify round-trip
    cached2 = CachedTickerResolver(inner=FakeTickerResolver([]), cache_path=cache_file)
    for m in matches:
        result = cached2.lookup(m.symbol)
        assert result == m


# ---------------------------------------------------------------------------
# Empty query short-circuit
# ---------------------------------------------------------------------------

def test_empty_query_returns_empty_without_touching_cache(tmp_path: Path) -> None:
    fake = FakeTickerResolver([_make_match("APD")])
    cached = _make_cached(fake, tmp_path)

    result = cached.resolve("")
    assert result == []
    assert fake.resolve_call_count == 0
    assert not (tmp_path / "cache.json").exists()


def test_empty_symbol_returns_none_without_touching_cache(tmp_path: Path) -> None:
    fake = FakeTickerResolver([_make_match("APD")])
    cached = _make_cached(fake, tmp_path)

    result = cached.lookup("")
    assert result is None
    assert fake.lookup_call_count == 0
    assert not (tmp_path / "cache.json").exists()


# ---------------------------------------------------------------------------
# Concurrent-write safety (single-process atomic replace)
# ---------------------------------------------------------------------------

def test_double_write_produces_valid_json(tmp_path: Path) -> None:
    fake = FakeTickerResolver([_make_match("APD"), _make_match("NVDA", Currency.USD)])
    cached = _make_cached(fake, tmp_path)

    cached.resolve("APD")
    cached.resolve("NVDA")

    cache_file = tmp_path / "cache.json"
    data = json.loads(cache_file.read_text())
    assert "resolve:apd" in data["entries"]
    assert "resolve:nvda" in data["entries"]
