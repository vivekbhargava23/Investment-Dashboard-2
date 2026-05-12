from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from app.adapters.company_cache.ttl import FINANCIALS_TTL, PROFILE_TTL, prices_ttl
from app.domain.company import (
    AnnualFundamentals,
    CompanyData,
    CompanyProfile,
    CurrentMultiples,
    DividendEvent,
    LatestQuote,
    NextCatalyst,
    OwnershipSnapshot,
    PriceHistoryPoint,
    QuarterlyFundamentals,
)
from app.ports.company_data import CompanyDataProvider

_log = logging.getLogger(__name__)

_SECTION_MODELS: dict[str, type] = {
    "profile": CompanyProfile,
    "prices": LatestQuote,   # placeholder — prices section has multiple sub-fields
    "financials": CurrentMultiples,  # placeholder — financials section has multiple sub-fields
}

_Section = Literal["profile", "prices", "financials"]


def _now_utc() -> datetime:
    return datetime.now(UTC)


class CacheCompanyAdapter:
    """Decorator adapter: wraps another CompanyDataProvider with per-section JSON caching."""

    def __init__(
        self,
        inner: CompanyDataProvider,
        cache_root: Path,
        *,
        now: Callable[[], datetime] = _now_utc,
    ) -> None:
        self._inner = inner
        self._cache_root = cache_root
        self._now = now

    def get_company(self, ticker: str) -> CompanyData:
        ticker_dir = self._cache_root / ticker
        ticker_dir.mkdir(parents=True, exist_ok=True)
        now = self._now()

        profile_data, profile_fetched_at = self._load_section(ticker, "profile", now)
        prices_data, prices_fetched_at = self._load_section(ticker, "prices", now)
        financials_data, financials_fetched_at = self._load_section(ticker, "financials", now)

        fetch_errors: dict[str, str] = {}

        # For any section that needs refreshing, fetch from inner
        if profile_data is None:
            fresh = self._inner.refresh_section(ticker, "profile")
            self._write_section(ticker, "profile", fresh, now)
            profile_data = fresh
            profile_fetched_at = now
            fetch_errors.update(fresh.fetch_errors)

        if prices_data is None:
            fresh = self._inner.refresh_section(ticker, "prices")
            self._write_section(ticker, "prices", fresh, now)
            prices_data = fresh
            prices_fetched_at = now
            fetch_errors.update(fresh.fetch_errors)

        if financials_data is None:
            fresh = self._inner.refresh_section(ticker, "financials")
            self._write_section(ticker, "financials", fresh, now)
            financials_data = fresh
            financials_fetched_at = now
            fetch_errors.update(fresh.fetch_errors)

        return _merge_sections(
            ticker=ticker,
            profile_data=profile_data,
            prices_data=prices_data,
            financials_data=financials_data,
            profile_fetched_at=profile_fetched_at,
            prices_fetched_at=prices_fetched_at,
            financials_fetched_at=financials_fetched_at,
            fetch_errors=fetch_errors,
        )

    def refresh_section(
        self,
        ticker: str,
        section: _Section,
    ) -> CompanyData:
        path = self._section_path(ticker, section)
        if path.exists():
            path.unlink()
        return self.get_company(ticker)

    def _section_path(self, ticker: str, section: _Section) -> Path:
        return self._cache_root / ticker / f"{section}.json"

    def _load_section(
        self, ticker: str, section: _Section, now: datetime
    ) -> tuple[CompanyData | None, datetime | None]:
        """Return (CompanyData, fetched_at) if cache is valid, else (None, None)."""
        path = self._section_path(ticker, section)
        if not path.exists():
            return None, None

        try:
            raw = path.read_text(encoding="utf-8")
            envelope = json.loads(raw)
            fetched_at = datetime.fromisoformat(envelope["fetched_at"])
            ttl = _ttl_for_section(section, now)
            age = now - fetched_at
            if age > ttl:
                return None, None  # stale
            data_dict = envelope.get("data", {})
            data = _dict_to_company_data(ticker, section, data_dict)
            return data, fetched_at
        except Exception as exc:
            _log.warning("Cache file %s is corrupt: %s. Re-fetching.", path, exc)
            return None, None

    def _write_section(
        self,
        ticker: str,
        section: _Section,
        company: CompanyData,
        fetched_at: datetime,
    ) -> None:
        ticker_dir = self._cache_root / ticker
        ticker_dir.mkdir(parents=True, exist_ok=True)
        path = self._section_path(ticker, section)
        tmp_path = path.with_suffix(".json.tmp")

        data_dict = _company_data_to_section_dict(section, company)
        envelope: dict[str, Any] = {
            "ticker": ticker,
            "fetched_at": fetched_at.isoformat(),
            "source": _source_for_section(section, company),
            "data": data_dict,
        }
        raw = json.dumps(envelope, default=str, indent=2)
        tmp_path.write_text(raw, encoding="utf-8")
        os.replace(tmp_path, path)


def _ttl_for_section(section: _Section, now: datetime) -> timedelta:
    if section == "profile":
        return PROFILE_TTL
    if section == "prices":
        return prices_ttl(now)
    return FINANCIALS_TTL


def _source_for_section(section: _Section, company: CompanyData) -> str:
    if section == "financials" and company.ownership is not None:
        return "finnhub"
    return "yfinance"


def _company_data_to_section_dict(section: _Section, company: CompanyData) -> dict[str, Any]:
    if section == "profile":
        return {
            "profile": company.profile.model_dump(mode="json") if company.profile else None,
        }
    if section == "prices":
        return {
            "latest_quote": (
                company.latest_quote.model_dump(mode="json") if company.latest_quote else None
            ),
            "price_history": [p.model_dump(mode="json") for p in company.price_history],
        }
    # financials
    return {
        "quarterly_fundamentals": [
            q.model_dump(mode="json") for q in company.quarterly_fundamentals
        ],
        "annual_fundamentals": [
            a.model_dump(mode="json") for a in company.annual_fundamentals
        ],
        "current_multiples": (
            company.current_multiples.model_dump(mode="json")
            if company.current_multiples
            else None
        ),
        "dividends": [d.model_dump(mode="json") for d in company.dividends],
        "ownership": (
            company.ownership.model_dump(mode="json") if company.ownership else None
        ),
        "next_catalyst": (
            company.next_catalyst.model_dump(mode="json") if company.next_catalyst else None
        ),
    }


def _dict_to_company_data(ticker: str, section: _Section, data: dict[str, Any]) -> CompanyData:
    """Deserialize a section dict back into a partial CompanyData."""
    if section == "profile":
        raw_profile = data.get("profile")
        profile = CompanyProfile.model_validate(raw_profile) if raw_profile else None
        return CompanyData(ticker=ticker, profile=profile)

    if section == "prices":
        raw_quote = data.get("latest_quote")
        latest_quote = LatestQuote.model_validate(raw_quote) if raw_quote else None
        raw_history = data.get("price_history") or []
        price_history = [PriceHistoryPoint.model_validate(p) for p in raw_history]
        return CompanyData(ticker=ticker, latest_quote=latest_quote, price_history=price_history)

    # financials
    raw_q = data.get("quarterly_fundamentals") or []
    raw_a = data.get("annual_fundamentals") or []
    raw_m = data.get("current_multiples")
    raw_d = data.get("dividends") or []
    raw_o = data.get("ownership")
    raw_nc = data.get("next_catalyst")
    return CompanyData(
        ticker=ticker,
        quarterly_fundamentals=[QuarterlyFundamentals.model_validate(q) for q in raw_q],
        annual_fundamentals=[AnnualFundamentals.model_validate(a) for a in raw_a],
        current_multiples=CurrentMultiples.model_validate(raw_m) if raw_m else None,
        dividends=[DividendEvent.model_validate(d) for d in raw_d],
        ownership=OwnershipSnapshot.model_validate(raw_o) if raw_o else None,
        next_catalyst=NextCatalyst.model_validate(raw_nc) if raw_nc else None,
    )


def _merge_sections(
    *,
    ticker: str,
    profile_data: CompanyData,
    prices_data: CompanyData,
    financials_data: CompanyData,
    profile_fetched_at: datetime | None,
    prices_fetched_at: datetime | None,
    financials_fetched_at: datetime | None,
    fetch_errors: dict[str, str],
) -> CompanyData:
    return CompanyData(
        ticker=ticker,
        profile=profile_data.profile,
        latest_quote=prices_data.latest_quote,
        price_history=prices_data.price_history,
        quarterly_fundamentals=financials_data.quarterly_fundamentals,
        annual_fundamentals=financials_data.annual_fundamentals,
        current_multiples=financials_data.current_multiples,
        dividends=financials_data.dividends,
        ownership=financials_data.ownership,
        next_catalyst=financials_data.next_catalyst,
        profile_fetched_at=profile_fetched_at,
        prices_fetched_at=prices_fetched_at,
        financials_fetched_at=financials_fetched_at,
        fetch_errors=fetch_errors,
    )
