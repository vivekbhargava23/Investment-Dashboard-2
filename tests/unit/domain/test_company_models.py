from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.company import (
    AnnualFundamentals,
    CompanyData,
    CompanyProfile,
    CurrentMultiples,
    DividendEvent,
    InsiderTransaction,
    InstitutionalHolder,
    LatestQuote,
    NextCatalyst,
    OwnershipSnapshot,
    PriceHistoryPoint,
    QuarterlyFundamentals,
)
from app.domain.money import Currency, Money


def _money(amount: str, currency: Currency = Currency.USD) -> Money:
    return Money(amount=Decimal(amount), currency=currency)


def _now() -> datetime:
    return datetime(2026, 5, 12, 12, 0, 0, tzinfo=UTC)


# --- Frozen contract ---

def test_company_profile_frozen() -> None:
    profile = CompanyProfile(ticker="NVDA", name="NVIDIA", currency="USD")
    with pytest.raises(ValidationError):
        profile.name = "changed"  # type: ignore[misc]


def test_latest_quote_frozen() -> None:
    q = LatestQuote(
        ticker="NVDA",
        price=_money("900"),
        previous_close=_money("890"),
        day_change_pct=Decimal("1.12"),
        as_of=_now(),
    )
    with pytest.raises(ValidationError):
        q.ticker = "AAPL"  # type: ignore[misc]


def test_price_history_point_frozen() -> None:
    p = PriceHistoryPoint(date=date(2026, 1, 1), close=Decimal("100"))
    with pytest.raises(ValidationError):
        p.close = Decimal("200")  # type: ignore[misc]


def test_quarterly_fundamentals_frozen() -> None:
    q = QuarterlyFundamentals(period_end=date(2026, 3, 31), currency="USD")
    with pytest.raises(ValidationError):
        q.revenue = Decimal("1")  # type: ignore[misc]


def test_annual_fundamentals_frozen() -> None:
    a = AnnualFundamentals(fiscal_year=2025, period_end=date(2025, 12, 31), currency="USD")
    with pytest.raises(ValidationError):
        a.fiscal_year = 2026  # type: ignore[misc]


def test_current_multiples_frozen() -> None:
    m = CurrentMultiples(as_of=_now())
    with pytest.raises(ValidationError):
        m.pe_trailing = Decimal("20")  # type: ignore[misc]


def test_dividend_event_frozen() -> None:
    d = DividendEvent(ex_date=date(2026, 1, 1), amount_per_share=Decimal("0.5"), currency="USD")
    with pytest.raises(ValidationError):
        d.amount_per_share = Decimal("1")  # type: ignore[misc]


def test_institutional_holder_frozen() -> None:
    h = InstitutionalHolder(
        name="Vanguard",
        shares_held=1_000_000,
        pct_of_shares_outstanding=Decimal("5"),
        as_of=date(2026, 1, 1),
    )
    with pytest.raises(ValidationError):
        h.name = "BlackRock"  # type: ignore[misc]


def test_insider_transaction_frozen() -> None:
    t = InsiderTransaction(
        insider_name="Jensen Huang",
        transaction_date=date(2026, 1, 1),
        transaction_type="SELL",
        shares=1000,
    )
    with pytest.raises(ValidationError):
        t.shares = 2000  # type: ignore[misc]


def test_ownership_snapshot_frozen() -> None:
    o = OwnershipSnapshot(as_of=date(2026, 1, 1))
    with pytest.raises(ValidationError):
        o.as_of = date(2026, 6, 1)  # type: ignore[misc]


def test_next_catalyst_frozen() -> None:
    nc = NextCatalyst(kind="EARNINGS", date=date(2026, 7, 1))
    with pytest.raises(ValidationError):
        nc.kind = "DIVIDEND"  # type: ignore[misc]


def test_company_data_frozen() -> None:
    cd = CompanyData(ticker="NVDA")
    with pytest.raises(ValidationError):
        cd.ticker = "AAPL"  # type: ignore[misc]


# --- CompanyData with everything None ---

def test_company_data_all_none_construction() -> None:
    cd = CompanyData(ticker="NVDA")
    assert cd.profile is None
    assert cd.latest_quote is None
    assert cd.price_history == []
    assert cd.quarterly_fundamentals == []
    assert cd.annual_fundamentals == []
    assert cd.current_multiples is None
    assert cd.dividends == []
    assert cd.ownership is None
    assert cd.next_catalyst is None
    assert cd.fetch_errors == {}


def test_company_data_all_none_json_roundtrip() -> None:
    cd = CompanyData(ticker="NVDA")
    json_str = cd.model_dump_json()
    restored = CompanyData.model_validate_json(json_str)
    assert restored.ticker == "NVDA"
    assert restored.profile is None
    assert restored.fetch_errors == {}


# --- CompanyData fully populated ---

def _build_full_company_data() -> CompanyData:
    return CompanyData(
        ticker="NVDA",
        profile=CompanyProfile(
            ticker="NVDA",
            name="NVIDIA Corporation",
            isin="US67066G1040",
            sector="Technology",
            industry="Semiconductors",
            country="US",
            currency="USD",
            employees=29600,
            market_cap=_money("2000000000000"),
            long_description="NVIDIA designs GPUs.",
        ),
        latest_quote=LatestQuote(
            ticker="NVDA",
            price=_money("900"),
            previous_close=_money("890"),
            day_change_pct=Decimal("1.12"),
            as_of=_now(),
        ),
        price_history=[
            PriceHistoryPoint(date=date(2026, 1, 1), close=Decimal("850"), volume=10_000_000),
            PriceHistoryPoint(date=date(2026, 1, 2), close=Decimal("860")),
        ],
        quarterly_fundamentals=[
            QuarterlyFundamentals(
                period_end=date(2026, 1, 31),
                revenue=Decimal("39000000000"),
                net_income=Decimal("22000000000"),
                currency="USD",
            )
        ],
        annual_fundamentals=[
            AnnualFundamentals(
                fiscal_year=2025,
                period_end=date(2025, 12, 31),
                revenue=Decimal("130000000000"),
                currency="USD",
            )
        ],
        current_multiples=CurrentMultiples(as_of=_now(), pe_trailing=Decimal("35")),
        dividends=[
            DividendEvent(
                ex_date=date(2026, 3, 1), amount_per_share=Decimal("0.01"), currency="USD"
            )
        ],
        ownership=OwnershipSnapshot(
            as_of=date(2026, 1, 1),
            top_institutional_holders=[
                InstitutionalHolder(
                    name="Vanguard",
                    shares_held=500_000_000,
                    pct_of_shares_outstanding=Decimal("2"),
                    as_of=date(2026, 1, 1),
                )
            ],
            recent_insider_transactions=[
                InsiderTransaction(
                    insider_name="Jensen Huang",
                    transaction_date=date(2026, 1, 15),
                    transaction_type="SELL",
                    shares=100_000,
                )
            ],
        ),
        next_catalyst=NextCatalyst(
            kind="EARNINGS", date=date(2026, 8, 28), detail="Q2 FY26 earnings"
        ),
        profile_fetched_at=_now(),
        prices_fetched_at=_now(),
        financials_fetched_at=_now(),
        fetch_errors={},
    )


def test_company_data_fully_populated_construction() -> None:
    cd = _build_full_company_data()
    assert cd.profile is not None
    assert cd.profile.name == "NVIDIA Corporation"
    assert len(cd.price_history) == 2
    assert cd.next_catalyst is not None
    assert cd.next_catalyst.kind == "EARNINGS"


def test_company_data_fully_populated_json_roundtrip() -> None:
    cd = _build_full_company_data()
    json_str = cd.model_dump_json()
    restored = CompanyData.model_validate_json(json_str)
    assert restored.ticker == "NVDA"
    assert restored.profile is not None
    assert restored.profile.name == "NVIDIA Corporation"
    assert len(restored.price_history) == 2
    assert restored.ownership is not None
    assert len(restored.ownership.top_institutional_holders) == 1
    assert restored.next_catalyst is not None


# --- fetch_errors default ---

def test_fetch_errors_default_is_empty_dict() -> None:
    cd = CompanyData(ticker="AAPL")
    assert cd.fetch_errors == {}


def test_fetch_errors_with_values() -> None:
    cd = CompanyData(ticker="AAPL", fetch_errors={"prices": "timeout"})
    assert cd.fetch_errors["prices"] == "timeout"
