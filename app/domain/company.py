from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.money import Money


class CompanyProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    name: str
    isin: str | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    currency: str
    employees: int | None = None
    market_cap: Money | None = None
    long_description: str | None = None


class LatestQuote(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    price: Money
    previous_close: Money
    day_change_pct: Decimal
    as_of: datetime


class PriceHistoryPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    close: Decimal
    volume: int | None = None


class QuarterlyFundamentals(BaseModel):
    model_config = ConfigDict(frozen=True)

    period_end: date
    revenue: Decimal | None = None
    gross_profit: Decimal | None = None
    operating_income: Decimal | None = None
    net_income: Decimal | None = None
    free_cash_flow: Decimal | None = None
    eps_diluted: Decimal | None = None
    shares_diluted: int | None = None
    total_debt: Decimal | None = None
    cash_and_equivalents: Decimal | None = None
    net_debt: Decimal | None = None
    ebitda: Decimal | None = None
    currency: str


class AnnualFundamentals(BaseModel):
    model_config = ConfigDict(frozen=True)

    fiscal_year: int
    period_end: date
    revenue: Decimal | None = None
    gross_profit: Decimal | None = None
    operating_income: Decimal | None = None
    net_income: Decimal | None = None
    free_cash_flow: Decimal | None = None
    eps_diluted: Decimal | None = None
    shares_diluted: int | None = None
    total_debt: Decimal | None = None
    cash_and_equivalents: Decimal | None = None
    net_debt: Decimal | None = None
    ebitda: Decimal | None = None
    capex: Decimal | None = None
    buybacks: Decimal | None = None
    dividends_paid: Decimal | None = None
    stock_based_compensation: Decimal | None = None
    currency: str


class CurrentMultiples(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: datetime
    pe_trailing: Decimal | None = None
    ps_trailing: Decimal | None = None
    ev_ebitda: Decimal | None = None
    p_fcf: Decimal | None = None
    p_book: Decimal | None = None
    dividend_yield_pct: Decimal | None = None


class DividendEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    ex_date: date
    amount_per_share: Decimal
    currency: str


class InstitutionalHolder(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    shares_held: int
    pct_of_shares_outstanding: Decimal
    shares_change_qoq: int | None = None
    as_of: date


class InsiderTransaction(BaseModel):
    model_config = ConfigDict(frozen=True)

    insider_name: str
    insider_title: str | None = None
    transaction_date: date
    transaction_type: Literal["BUY", "SELL", "OPTION_EXERCISE", "OTHER"]
    shares: int
    price_per_share: Decimal | None = None
    value: Decimal | None = None


class OwnershipSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: date
    insider_ownership_pct: Decimal | None = None
    institutional_ownership_pct: Decimal | None = None
    top_institutional_holders: list[InstitutionalHolder] = Field(default_factory=list)
    recent_insider_transactions: list[InsiderTransaction] = Field(default_factory=list)


class NextCatalyst(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["EARNINGS", "DIVIDEND", "EX_DIVIDEND", "SPLIT"]
    date: date
    detail: str | None = None


class CompanyData(BaseModel):
    """Root aggregate. Every sub-section is optional — adapters fill what they can."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    quote_type: str | None = None
    profile: CompanyProfile | None = None
    latest_quote: LatestQuote | None = None
    price_history: list[PriceHistoryPoint] = Field(default_factory=list)
    quarterly_fundamentals: list[QuarterlyFundamentals] = Field(default_factory=list)
    annual_fundamentals: list[AnnualFundamentals] = Field(default_factory=list)
    current_multiples: CurrentMultiples | None = None
    dividends: list[DividendEvent] = Field(default_factory=list)
    ownership: OwnershipSnapshot | None = None
    next_catalyst: NextCatalyst | None = None
    profile_fetched_at: datetime | None = None
    prices_fetched_at: datetime | None = None
    financials_fetched_at: datetime | None = None
    fetch_errors: dict[str, str] = Field(default_factory=dict)
