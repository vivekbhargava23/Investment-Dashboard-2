from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from app.domain.company import CompanyData


class CompanyDataError(Exception):
    """Raised only for unrecoverable cases: invalid ticker format, all sources down."""

    pass


@runtime_checkable
class CompanyDataProvider(Protocol):
    """Single read interface for everything Company Deep Dive needs."""

    def get_company(self, ticker: str) -> CompanyData:
        """Fetch full company data. Never raises for partial data — populates fetch_errors instead.

        Raises CompanyDataError only for completely unrecoverable cases (invalid ticker
        format, all sources down).
        """
        ...

    def refresh_section(
        self,
        ticker: str,
        section: Literal["profile", "prices", "financials"],
    ) -> CompanyData:
        """Force-refresh a specific cache section. Returns the new full CompanyData.

        For cache adapters: invalidate that section's cache file and re-fetch.
        For non-cache adapters: equivalent to get_company (no cache to bypass).
        """
        ...
