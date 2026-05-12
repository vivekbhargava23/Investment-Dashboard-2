from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import pytest

from app.adapters.company_cache.adapter import CacheCompanyAdapter
from app.domain.company import (
    CompanyData,
    CompanyProfile,
    CurrentMultiples,
    LatestQuote,
    PriceHistoryPoint,
)
from app.domain.money import Currency, Money


def _money(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency=Currency.USD)


_FROZEN_NOW = datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC)  # Tuesday 10:00 UTC (before NYSE)


def _make_now(dt: datetime) -> object:
    return lambda: dt


class FakeInner:
    def __init__(self, company: CompanyData | None = None) -> None:
        self._company = company or CompanyData(ticker="NVDA")
        self.refresh_calls: list[tuple[str, str]] = []

    def get_company(self, ticker: str) -> CompanyData:
        return self._company

    def refresh_section(
        self,
        ticker: str,
        section: Literal["profile", "prices", "financials"],
    ) -> CompanyData:
        self.refresh_calls.append((ticker, section))
        return self._company


def _make_rich_company(ticker: str = "NVDA") -> CompanyData:
    return CompanyData(
        ticker=ticker,
        profile=CompanyProfile(ticker=ticker, name="NVIDIA", currency="USD"),
        latest_quote=LatestQuote(
            ticker=ticker,
            price=_money("900"),
            previous_close=_money("890"),
            day_change_pct=Decimal("1.1"),
            as_of=_FROZEN_NOW,
        ),
        price_history=[PriceHistoryPoint(date=_FROZEN_NOW.date(), close=Decimal("900"))],
        current_multiples=CurrentMultiples(as_of=_FROZEN_NOW, pe_trailing=Decimal("35")),
    )


# ── Cold cache ──────────────────────────────────────────────────────────────

def test_cold_cache_fetches_all_three_sections(tmp_path: Path) -> None:
    inner = FakeInner(_make_rich_company())
    adapter = CacheCompanyAdapter(inner, tmp_path, now=lambda: _FROZEN_NOW)

    adapter.get_company("NVDA")

    sections = {s for _, s in inner.refresh_calls}
    assert sections == {"profile", "prices", "financials"}
    assert (tmp_path / "NVDA" / "profile.json").exists()
    assert (tmp_path / "NVDA" / "prices.json").exists()
    assert (tmp_path / "NVDA" / "financials.json").exists()


def test_cold_cache_files_have_correct_shape(tmp_path: Path) -> None:
    inner = FakeInner(_make_rich_company())
    adapter = CacheCompanyAdapter(inner, tmp_path, now=lambda: _FROZEN_NOW)
    adapter.get_company("NVDA")

    for section in ("profile", "prices", "financials"):
        raw = json.loads((tmp_path / "NVDA" / f"{section}.json").read_text())
        assert raw["ticker"] == "NVDA"
        assert "fetched_at" in raw
        assert "source" in raw
        assert "data" in raw


# ── Warm cache, all fresh ────────────────────────────────────────────────────

def test_warm_cache_all_fresh_no_inner_calls(tmp_path: Path) -> None:
    inner = FakeInner(_make_rich_company())
    adapter = CacheCompanyAdapter(inner, tmp_path, now=lambda: _FROZEN_NOW)
    # Populate cache
    adapter.get_company("NVDA")
    inner.refresh_calls.clear()

    # Second call — should be served fully from cache
    adapter.get_company("NVDA")
    assert inner.refresh_calls == []


# ── Warm cache, one stale section ────────────────────────────────────────────

def test_stale_prices_section_triggers_one_refresh(tmp_path: Path) -> None:
    # Use market-hours time so prices TTL is 15min (much shorter than financials 24h).
    # Mon 16:00 UTC is within NYSE hours (14:30–21:00).
    market_now = datetime(2026, 5, 11, 16, 0, 0, tzinfo=UTC)
    inner = FakeInner(_make_rich_company())
    # Populate at T=0
    adapter = CacheCompanyAdapter(inner, tmp_path, now=lambda: market_now)
    adapter.get_company("NVDA")
    inner.refresh_calls.clear()

    # Advance 20min: prices (15min TTL) stale; financials (24h) and profile (30d) not stale
    stale_now = market_now + timedelta(minutes=20)
    adapter2 = CacheCompanyAdapter(inner, tmp_path, now=lambda: stale_now)
    adapter2.get_company("NVDA")

    refreshed_sections = {s for _, s in inner.refresh_calls}
    assert "prices" in refreshed_sections
    assert "profile" not in refreshed_sections
    assert "financials" not in refreshed_sections


# ── Corrupt cache file ───────────────────────────────────────────────────────

def test_corrupt_cache_file_triggers_refetch(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    inner = FakeInner(_make_rich_company())
    # Populate cache first
    adapter = CacheCompanyAdapter(inner, tmp_path, now=lambda: _FROZEN_NOW)
    adapter.get_company("NVDA")
    inner.refresh_calls.clear()

    # Corrupt the profile cache file
    profile_path = tmp_path / "NVDA" / "profile.json"
    profile_path.write_text("not json", encoding="utf-8")

    import logging
    with caplog.at_level(logging.WARNING):
        adapter.get_company("NVDA")

    assert any("corrupt" in r.message.lower() for r in caplog.records)
    refreshed_sections = {s for _, s in inner.refresh_calls}
    assert "profile" in refreshed_sections
    # File should now be valid JSON again
    assert json.loads(profile_path.read_text())["ticker"] == "NVDA"


# ── Atomic write ─────────────────────────────────────────────────────────────

def test_atomic_write_failed_replace_leaves_no_final_file(tmp_path: Path) -> None:
    inner = FakeInner(_make_rich_company())
    adapter = CacheCompanyAdapter(inner, tmp_path, now=lambda: _FROZEN_NOW)

    profile_final = tmp_path / "NVDA" / "profile.json"

    def fail_replace(src: object, dst: object) -> None:
        if Path(str(dst)) == profile_final:
            raise OSError("simulated failure")
        os.replace(src, dst)  # type: ignore[arg-type]

    with patch("app.adapters.company_cache.adapter.os.replace", side_effect=fail_replace):
        with pytest.raises(OSError):
            adapter.get_company("NVDA")

    assert not profile_final.exists()


# ── refresh_section deletes and re-fetches ───────────────────────────────────

def test_refresh_section_prices_re_fetches_even_if_fresh(tmp_path: Path) -> None:
    inner = FakeInner(_make_rich_company())
    adapter = CacheCompanyAdapter(inner, tmp_path, now=lambda: _FROZEN_NOW)
    # Populate
    adapter.get_company("NVDA")
    inner.refresh_calls.clear()

    adapter.refresh_section("NVDA", "prices")

    refreshed = {s for _, s in inner.refresh_calls}
    assert "prices" in refreshed


# ── Per-section fetched_at on returned CompanyData ────────────────────────────

def test_fetched_at_populated_on_returned_company_data(tmp_path: Path) -> None:
    inner = FakeInner(_make_rich_company())
    adapter = CacheCompanyAdapter(inner, tmp_path, now=lambda: _FROZEN_NOW)
    result = adapter.get_company("NVDA")

    assert result.profile_fetched_at is not None
    assert result.prices_fetched_at is not None
    assert result.financials_fetched_at is not None


def test_fetched_at_matches_cache_file_timestamp(tmp_path: Path) -> None:
    inner = FakeInner(_make_rich_company())
    adapter = CacheCompanyAdapter(inner, tmp_path, now=lambda: _FROZEN_NOW)
    adapter.get_company("NVDA")  # populate

    result = adapter.get_company("NVDA")  # serve from cache

    profile_raw = json.loads((tmp_path / "NVDA" / "profile.json").read_text())
    expected_ts = datetime.fromisoformat(profile_raw["fetched_at"])
    assert result.profile_fetched_at == expected_ts


# ── Cache root directory created if missing ──────────────────────────────────

def test_cache_root_created_if_missing(tmp_path: Path) -> None:
    nonexistent = tmp_path / "new_cache" / "subdir"
    assert not nonexistent.exists()

    inner = FakeInner(_make_rich_company())
    adapter = CacheCompanyAdapter(inner, nonexistent, now=lambda: _FROZEN_NOW)
    adapter.get_company("NVDA")

    assert nonexistent.exists()
    assert (nonexistent / "NVDA" / "profile.json").exists()
