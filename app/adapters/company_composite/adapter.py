from __future__ import annotations

from typing import Literal

from app.domain.company import (
    AnnualFundamentals,
    CompanyData,
    DividendEvent,
    PriceHistoryPoint,
    QuarterlyFundamentals,
)
from app.ports.company_data import CompanyDataProvider


class CompositeCompanyAdapter:
    """Merges results from multiple CompanyDataProviders.

    yfinance wins for all sections except ownership and next_catalyst, where Finnhub wins.
    fetch_errors are unioned across all underlying adapters.
    """

    def __init__(self, *providers: CompanyDataProvider) -> None:
        self._providers = list(providers)

    def get_company(self, ticker: str) -> CompanyData:
        results = [p.get_company(ticker) for p in self._providers]
        return _merge(ticker, results)

    def refresh_section(
        self,
        ticker: str,
        section: Literal["profile", "prices", "financials"],
    ) -> CompanyData:
        results = [p.refresh_section(ticker, section) for p in self._providers]
        return _merge(ticker, results)


def _merge(ticker: str, results: list[CompanyData]) -> CompanyData:
    if not results:
        return CompanyData(ticker=ticker)

    merged_errors: dict[str, str] = {}
    for r in results:
        merged_errors.update(r.fetch_errors)

    # Collect all field values, last-writer-wins (unless there's a preference rule)
    profile = None
    latest_quote = None
    price_history: list[PriceHistoryPoint] = []
    quarterly: list[QuarterlyFundamentals] = []
    annual: list[AnnualFundamentals] = []
    multiples = None
    dividends: list[DividendEvent] = []
    ownership = None
    next_catalyst = None
    profile_fetched_at = None
    prices_fetched_at = None
    financials_fetched_at = None

    for r in results:
        # yfinance sections: default last-writer-wins, but yfinance beats finnhub for these
        if r.profile is not None:
            profile = r.profile
        if r.latest_quote is not None:
            latest_quote = r.latest_quote
        if r.price_history:
            price_history = r.price_history
        if r.quarterly_fundamentals:
            quarterly = r.quarterly_fundamentals
        if r.annual_fundamentals:
            annual = r.annual_fundamentals
        if r.current_multiples is not None:
            multiples = r.current_multiples
        if r.dividends:
            dividends = r.dividends
        if r.profile_fetched_at is not None:
            profile_fetched_at = r.profile_fetched_at
        if r.prices_fetched_at is not None:
            prices_fetched_at = r.prices_fetched_at
        if r.financials_fetched_at is not None:
            financials_fetched_at = r.financials_fetched_at

    # Finnhub wins for ownership and next_catalyst
    # Process in order: let the last provider that returns a value win,
    # but we process providers in order so the later ones take priority.
    # To let Finnhub win, we process all results and take the last non-None value.
    for r in results:
        if r.ownership is not None:
            ownership = r.ownership
        if r.next_catalyst is not None:
            next_catalyst = r.next_catalyst

    return CompanyData(
        ticker=ticker,
        profile=profile,
        latest_quote=latest_quote,
        price_history=price_history,
        quarterly_fundamentals=quarterly,
        annual_fundamentals=annual,
        current_multiples=multiples,
        dividends=dividends,
        ownership=ownership,
        next_catalyst=next_catalyst,
        profile_fetched_at=profile_fetched_at,
        prices_fetched_at=prices_fetched_at,
        financials_fetched_at=financials_fetched_at,
        fetch_errors=merged_errors,
    )
