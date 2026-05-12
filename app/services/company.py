from __future__ import annotations

from typing import Literal

from app.domain.company import CompanyData
from app.ports.company_data import CompanyDataProvider


def get_company(ticker: str, *, provider: CompanyDataProvider) -> CompanyData:
    """Fetch (cached or fresh) full company data for a ticker."""
    return provider.get_company(ticker.upper())


def refresh_company_section(
    ticker: str,
    section: Literal["profile", "prices", "financials"],
    *,
    provider: CompanyDataProvider,
) -> CompanyData:
    """Force-refresh one section. UI calls this from the per-tab refresh button."""
    return provider.refresh_section(ticker.upper(), section)
