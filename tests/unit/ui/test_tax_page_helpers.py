# ruff: noqa: E501
"""Unit tests for helper functions in app/ui/pages/tax.py."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.money import Currency, Money
from app.domain.tax.classification import InstrumentKind
from app.domain.tax.engine import compute_tax_year_summary
from app.domain.tax.models import FilingStatus, HarvestImpact, TaxProfile
from app.ui.pages.tax import compute_headroom, compute_sequential_harvest_impacts

_EUR = Currency.EUR
_SINGLE = TaxProfile(filing_status=FilingStatus.SINGLE)

_RHM_MAP = IsinMapDocument(entries={
    "DE0007030009": IsinMapping(ticker="RHM.DE", name="Rheinmetall", status="mapped", instrument_kind=InstrumentKind.AKTIE),
})


def _m(v: str) -> Money:
    return Money(amount=Decimal(v), currency=_EUR)


def _impact(ticker: str, gain: str, taxable: str, kind: InstrumentKind = InstrumentKind.AKTIE) -> HarvestImpact:
    return HarvestImpact(
        ticker=ticker,
        instrument_kind=kind,
        unrealised_gain_eur=_m(gain),
        taxable_gain_after_teilfreistellung_eur=_m(taxable),
        incremental_tax_eur=_m("0"),
        incremental_soli_eur=_m("0"),
        total_incremental_eur=_m("0"),
        is_fully_sheltered=True,
    )


# ---------------------------------------------------------------------------
# compute_headroom
# ---------------------------------------------------------------------------

def test_headroom_allowance_only() -> None:
    """With no carryforward, headroom equals allowance remaining."""
    summary = compute_tax_year_summary(year=2026, transactions=[], profile=_SINGLE)
    headroom = compute_headroom(summary)
    # No transactions → full €1,000 allowance remaining, pots empty
    assert headroom.amount == Decimal("1000")


def test_headroom_mixed_components() -> None:
    """Headroom = allowance remaining + aktien pot remaining + general pot remaining.

    Scenario:
    - RHM.DE gain €300 (AKTIE, 0% Teilfreistellung).
    - Prior aktien carryforward = €0, prior general carryforward = €200 (untouched — no general gains).
    - Aktien pot: gains = €300, losses = 0, carryforward = 0 → taxable = €300. Remaining = 0.
    - General pot: gains = 0 → taxable = 0. Remaining carryforward = €200.
    - Allowance consumes €300 → remaining = €700.
    - Headroom = €700 + €0 + €200 = €900.

    The critical assertion: headroom does NOT count the gross €300 aktien gain again.
    """
    from datetime import date

    from app.domain.models import Transaction, TransactionType

    txs = [
        Transaction(
            ticker="RHM.DE",
            type=TransactionType.BUY,
            trade_date=date(2025, 1, 1),
            shares=Decimal("10"),
            price_native=Money(amount=Decimal("100"), currency=_EUR),
            fx_rate_eur=Decimal("1"),
        ),
        Transaction(
            ticker="RHM.DE",
            type=TransactionType.SELL,
            trade_date=date(2026, 1, 15),
            shares=Decimal("10"),
            price_native=Money(amount=Decimal("130"), currency=_EUR),
            fx_rate_eur=Decimal("1"),
        ),
    ]
    summary = compute_tax_year_summary(
        year=2026,
        transactions=txs,
        profile=_SINGLE,
        isin_map=_RHM_MAP,
        prior_year_aktien_carryforward_eur=_m("0"),
        prior_year_general_carryforward_eur=_m("200"),
    )
    # Gain = €300. No prior aktien carryforward → aktien pot taxable = €300.
    # General pot: no gains → taxable = 0. Remaining = €200.
    # Allowance consumes €300 → remaining = €700.
    assert summary.sparerpauschbetrag_consumed_eur.amount == Decimal("300")
    assert summary.sparerpauschbetrag_remaining_eur.amount == Decimal("700")
    assert summary.aktien_pot.remaining_carryforward_eur.amount == Decimal("0")
    assert summary.general_pot.remaining_carryforward_eur.amount == Decimal("200")

    headroom = compute_headroom(summary)
    # Headroom = €700 + €0 + €200 = €900
    assert headroom.amount == pytest.approx(Decimal("900"), abs=Decimal("1"))


def test_headroom_does_not_double_count_losses() -> None:
    """Losses already consumed against gains do not inflate headroom.

    Scenario: €400 aktien gain, €300 aktien loss → net €100 taxable AKTIE gain.
    Prior aktien carryforward €0. No current losses remaining (they absorbed gains).
    Allowance consumes the €100 net. Headroom = €900 (allowance) + €0 (aktien pot) + €0 (general).
    """
    from datetime import date

    from app.domain.models import Transaction, TransactionType

    txs = [
        Transaction(
            ticker="RHM.DE",
            type=TransactionType.BUY,
            trade_date=date(2024, 1, 1),
            shares=Decimal("10"),
            price_native=_m("100"),
            fx_rate_eur=Decimal("1"),
        ),
        Transaction(
            ticker="RHM.DE",
            type=TransactionType.BUY,
            trade_date=date(2024, 1, 1),
            shares=Decimal("10"),
            price_native=_m("200"),
            fx_rate_eur=Decimal("1"),
        ),
        Transaction(
            ticker="RHM.DE",
            type=TransactionType.SELL,
            trade_date=date(2026, 3, 1),
            shares=Decimal("10"),
            price_native=_m("140"),
            fx_rate_eur=Decimal("1"),
        ),
        Transaction(
            ticker="RHM.DE",
            type=TransactionType.SELL,
            trade_date=date(2026, 4, 1),
            shares=Decimal("10"),
            price_native=_m("170"),
            fx_rate_eur=Decimal("1"),
        ),
    ]
    summary = compute_tax_year_summary(year=2026, transactions=txs, profile=_SINGLE, isin_map=_RHM_MAP)
    # NVDA gain: €400. RHM.DE loss: -€300. Net AKTIE: €100. Allowance covers €100.
    # Pots: aktien remaining = 0 (losses absorbed gains, nothing left to carryforward).
    # General: nothing.
    headroom = compute_headroom(summary)
    # Headroom = €900 remaining allowance + €0 aktien pot + €0 general pot = €900
    assert headroom.amount == pytest.approx(Decimal("900"), abs=Decimal("1"))


# ---------------------------------------------------------------------------
# compute_sequential_harvest_impacts
# ---------------------------------------------------------------------------

def test_sequential_harvest_three_positions() -> None:
    """Sequential harvest: €600, €500, €400 gains (AKTIE), €1,000 allowance.

    Row 1: €600 fully sheltered → headroom after = €400
    Row 2: €500, €400 sheltered, €100 net taxable → tax = €100 × 0.26375 = €26.375
    Row 3: €400 fully taxable → tax = €400 × 0.26375 = €105.50
    """
    impacts = [
        _impact("P1", gain="600", taxable="600"),
        _impact("P2", gain="500", taxable="500"),
        _impact("P3", gain="400", taxable="400"),
    ]
    headroom = _m("1000")
    results = compute_sequential_harvest_impacts(impacts, headroom)
    assert len(results) == 3

    p1_imp, p1_tax, p1_hdroom = results[0]
    assert p1_imp.ticker == "P1"
    assert p1_tax.amount == Decimal("0")
    assert p1_hdroom.amount == Decimal("400")

    p2_imp, p2_tax, p2_hdroom = results[1]
    assert p2_imp.ticker == "P2"
    # €100 taxable × 0.26375 = €26.375 → rounds to €26.38
    assert p2_tax.amount == pytest.approx(Decimal("26.38"), abs=Decimal("0.01"))
    assert p2_hdroom.amount == Decimal("0")

    p3_imp, p3_tax, p3_hdroom = results[2]
    assert p3_imp.ticker == "P3"
    # €400 × 0.26375 = €105.50
    assert p3_tax.amount == pytest.approx(Decimal("105.50"), abs=Decimal("0.01"))
    assert p3_hdroom.amount == Decimal("0")


def test_sequential_harvest_skips_negative_gains() -> None:
    """Positions with unrealised loss are not included in harvest output."""
    impacts = [
        _impact("GOOD", gain="500", taxable="500"),
        _impact("BAD", gain="-200", taxable="-200"),
    ]
    results = compute_sequential_harvest_impacts(impacts, _m("1000"))
    tickers = [r[0].ticker for r in results]
    assert "GOOD" in tickers
    assert "BAD" not in tickers
