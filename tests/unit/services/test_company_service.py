from __future__ import annotations

from typing import Literal

from app.domain.company import CompanyData, CompanyProfile
from app.services.company import get_company, refresh_company_section


class FakeProvider:
    def __init__(self, company: CompanyData) -> None:
        self._company = company
        self.get_calls: list[str] = []
        self.refresh_calls: list[tuple[str, str]] = []

    def get_company(self, ticker: str) -> CompanyData:
        self.get_calls.append(ticker)
        return self._company

    def refresh_section(
        self,
        ticker: str,
        section: Literal["profile", "prices", "financials"],
    ) -> CompanyData:
        self.refresh_calls.append((ticker, section))
        return self._company


def _make_company(ticker: str) -> CompanyData:
    return CompanyData(
        ticker=ticker,
        profile=CompanyProfile(ticker=ticker, name="Test Corp", currency="USD"),
    )


def test_get_company_happy_path() -> None:
    expected = _make_company("NVDA")
    provider = FakeProvider(expected)

    result = get_company("nvda", provider=provider)

    assert result is expected
    assert provider.get_calls == ["NVDA"]  # uppercased


def test_get_company_uppercases_ticker() -> None:
    expected = _make_company("AAPL")
    provider = FakeProvider(expected)

    get_company("aapl", provider=provider)

    assert provider.get_calls == ["AAPL"]


def test_refresh_company_section_calls_provider_with_correct_args() -> None:
    expected = _make_company("NVDA")
    provider = FakeProvider(expected)

    result = refresh_company_section("nvda", "prices", provider=provider)

    assert result is expected
    assert provider.refresh_calls == [("NVDA", "prices")]


def test_refresh_company_section_uppercases_ticker() -> None:
    provider = FakeProvider(_make_company("MSFT"))

    refresh_company_section("msft", "financials", provider=provider)

    assert provider.refresh_calls == [("MSFT", "financials")]
