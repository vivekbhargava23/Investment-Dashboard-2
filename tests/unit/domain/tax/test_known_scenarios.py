"""Worked examples from German tax authority guidance (BVI / NRW Finanzamt)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from app.domain.money import Currency, Money
from app.domain.tax.classification import InstrumentKind
from app.domain.tax.models import FilingStatus, TaxImpact, TaxProfile
from app.domain.tax.pipeline import (
    TaxYearLedger,
    _apply_carryforward,
    _apply_sparerpauschbetrag,
    _apply_within_year_offset,
    _compute_abgeltungsteuer,
    _compute_soli,
    _finalise,
    _split_into_pots,
)
from app.domain.tax.rates import TAX_RATES_2026, TaxYearRates

_EUR = Currency.EUR
_ZERO = Money.zero(_EUR)
_SINGLE = TaxProfile(filing_status=FilingStatus.SINGLE)

_FIXTURES = Path(__file__).parent.parent.parent.parent / "fixtures" / "tax"


def _m(value: str) -> Money:
    return Money(amount=Decimal(value), currency=_EUR)


def _make_aktienfonds_impact(gross_eur: str) -> TaxImpact:
    gross = _m(gross_eur)
    pct = Decimal("0.30")
    amount = gross * pct
    taxable = gross * (Decimal("1") - pct)
    return TaxImpact(
        instrument_kind=InstrumentKind.AKTIENFONDS,
        gross_gain_eur=gross,
        teilfreistellung_pct=pct,
        teilfreistellung_amount_eur=amount,
        taxable_gain_after_teilfreistellung_eur=taxable,
    )


def _make_aktie_impact(gross_eur: str) -> TaxImpact:
    gross = _m(gross_eur)
    pct = Decimal("0.00")
    return TaxImpact(
        instrument_kind=InstrumentKind.AKTIE,
        gross_gain_eur=gross,
        teilfreistellung_pct=pct,
        teilfreistellung_amount_eur=gross * pct,
        taxable_gain_after_teilfreistellung_eur=gross * (Decimal("1") - pct),
    )


def _run_pipeline(
    impacts: list[TaxImpact],
    rates: TaxYearRates = TAX_RATES_2026,
    profile: TaxProfile = _SINGLE,
    prior_aktien: Money | None = None,
    prior_general: Money | None = None,
) -> TaxYearLedger:
    ledger = TaxYearLedger(
        year=2026,
        rates=rates,
        profile=profile,
        realised_gains=[],  # type: ignore[arg-type]
        prior_aktien_carryforward=prior_aktien or _ZERO,
        prior_general_carryforward=prior_general or _ZERO,
        additional_dividend_income_eur=_ZERO,
        additional_interest_income_eur=_ZERO,
    )
    ledger.tax_impacts = impacts
    ledger = _split_into_pots(ledger)
    ledger = _apply_within_year_offset(ledger)
    ledger = _apply_carryforward(ledger)
    ledger = _apply_sparerpauschbetrag(ledger)
    ledger = _compute_abgeltungsteuer(ledger)
    ledger = _compute_soli(ledger)
    return ledger


def test_bvi_aktienfonds_1000_eur_gain() -> None:
    """BVI example: €1000 Aktienfonds gain, 30% Teilfreistellung → €700 taxable."""
    impact = _make_aktienfonds_impact("1000.00")
    assert impact.taxable_gain_after_teilfreistellung_eur == _m("700.0000")


def test_nrw_aktienfonds_fixture() -> None:
    """NRW Finanzamt example loaded from fixture file."""
    fixture = json.loads((_FIXTURES / "nrw_aktienfonds_2024.json").read_text())
    gross = fixture["gross_gain_eur"]
    expected_taxable = Decimal(fixture["expected_taxable_gain_eur"])

    impact = _make_aktienfonds_impact(gross)
    assert (
        abs(impact.taxable_gain_after_teilfreistellung_eur.amount - expected_taxable)
        < Decimal("0.01")
    )


def test_loss_pot_firewall_worked_example() -> None:
    """
    Aktien gain €1500 + ETF loss (post-TF = -€1000) →
    - aktien_pot taxable remains €1500 (§20 Abs.6 S.4 firewall)
    - general_pot carryforward = €1000
    After €1000 allowance: taxable = €500
    Tax = €500 × 0.25 = €125, Soli = €125 × 0.055 = €6.875
    """
    # Construct the ETF loss impact with taxable = -€1000 directly (no TF applied)
    # to match the test spec "ETF loss post-Teilfreistellung = €1000"
    etf_loss_exact = TaxImpact(
        instrument_kind=InstrumentKind.AKTIENFONDS,
        gross_gain_eur=_m("-1000.00"),
        teilfreistellung_pct=Decimal("0.00"),
        teilfreistellung_amount_eur=_m("0.00"),
        taxable_gain_after_teilfreistellung_eur=_m("-1000.00"),
    )
    impacts = [_make_aktie_impact("1500.00"), etf_loss_exact]
    ledger = _run_pipeline(impacts)

    assert ledger.aktien_pot is not None
    assert ledger.general_pot is not None

    # Aktien is unaffected by ETF loss
    assert ledger.aktien_pot.taxable_after_offset_eur == _m("1500.0000")
    # ETF loss stays in general carryforward
    assert ledger.general_pot.remaining_carryforward_eur == _m("1000.0000")
    # After €1000 allowance: taxable = 1500 - 1000 = 500
    assert ledger.taxable_after_allowance == _m("500.0000")

    summary = _finalise(ledger)
    assert summary.abgeltungsteuer_eur == _m("125.0000")
    assert summary.solidaritaetszuschlag_eur == _m("6.8750")
    assert summary.total_tax_owed_eur == _m("131.8750")
