"""Unit tests for individual pipeline steps in app/domain/tax/pipeline.py."""

from __future__ import annotations

from decimal import Decimal

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
_JOINT = TaxProfile(filing_status=FilingStatus.JOINT)


def _m(value: str) -> Money:
    return Money(amount=Decimal(value), currency=_EUR)


def _make_ledger(
    profile: TaxProfile | None = None,
    rates: TaxYearRates = TAX_RATES_2026,
    prior_aktien: Money | None = None,
    prior_general: Money | None = None,
    dividend_income: Money | None = None,
    interest_income: Money | None = None,
) -> TaxYearLedger:
    return TaxYearLedger(
        year=2026,
        rates=rates,
        profile=profile or _SINGLE,
        realised_gains=[],  # type: ignore[arg-type]
        prior_aktien_carryforward=prior_aktien or _ZERO,
        prior_general_carryforward=prior_general or _ZERO,
        additional_dividend_income_eur=dividend_income or _ZERO,
        additional_interest_income_eur=interest_income or _ZERO,
    )


def _make_aktie_impact(gross_eur: str) -> TaxImpact:
    gross = _m(gross_eur)
    pct = Decimal("0.00")
    amount = gross * pct
    taxable = gross * (Decimal("1") - pct)
    return TaxImpact(
        instrument_kind=InstrumentKind.AKTIE,
        gross_gain_eur=gross,
        teilfreistellung_pct=pct,
        teilfreistellung_amount_eur=amount,
        taxable_gain_after_teilfreistellung_eur=taxable,
    )


def _make_etf_impact(gross_eur: str) -> TaxImpact:
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


def _make_dividende_impact(gross_eur: str) -> TaxImpact:
    gross = _m(gross_eur)
    pct = Decimal("0.00")
    return TaxImpact(
        instrument_kind=InstrumentKind.DIVIDENDE,
        gross_gain_eur=gross,
        teilfreistellung_pct=pct,
        teilfreistellung_amount_eur=gross * pct,
        taxable_gain_after_teilfreistellung_eur=gross * (Decimal("1") - pct),
    )


# --- Teilfreistellung ---

def test_teilfreistellung_30_percent_gain() -> None:
    # €1000 ETF gain → €300 exempt, €700 taxable
    impact = _make_etf_impact("1000.00")
    assert impact.teilfreistellung_amount_eur == _m("300.0000")
    assert impact.taxable_gain_after_teilfreistellung_eur == _m("700.0000")


def test_teilfreistellung_applies_symmetrically_to_losses() -> None:
    # €100 ETF loss → €30 of loss is "exempt" (not deductible), €70 is deductible
    impact = _make_etf_impact("-100.00")
    assert impact.taxable_gain_after_teilfreistellung_eur == _m("-70.0000")
    assert impact.teilfreistellung_amount_eur == _m("-30.0000")


# --- Pot splitting and §20 Abs.6 S.4 firewall ---

def test_aktien_pot_does_not_absorb_general_pot_losses() -> None:
    # Aktien gain €100, ETF loss (after TF: -€70). They CANNOT cross-offset.
    ledger = _make_ledger()
    ledger.tax_impacts = [
        _make_aktie_impact("100.00"),
        _make_etf_impact("-100.00"),   # -€70 after TF
    ]
    ledger = _split_into_pots(ledger)
    ledger = _apply_within_year_offset(ledger)
    ledger = _apply_carryforward(ledger)

    assert ledger.aktien_pot is not None
    assert ledger.general_pot is not None

    # Aktien pot is untouched by the ETF loss
    assert ledger.aktien_pot.taxable_after_offset_eur == _m("100.0000")
    # General pot has a loss of €70 that carries forward
    assert ledger.general_pot.taxable_after_offset_eur == _ZERO
    assert ledger.general_pot.remaining_carryforward_eur == _m("70.0000")


def test_general_pot_absorbs_across_kinds() -> None:
    # ETF gain €100 + dividend €50 - bond-like loss (RENTENFONDS) €30
    # After TF: ETF gain = €70, div = €50. RENTENFONDS loss (no TF): -€30.
    etf_gain = _make_etf_impact("100.00")   # taxable = €70
    div_impact = _make_dividende_impact("50.00")  # taxable = €50
    bond_loss = TaxImpact(
        instrument_kind=InstrumentKind.RENTENFONDS,
        gross_gain_eur=_m("-30.00"),
        teilfreistellung_pct=Decimal("0.00"),
        teilfreistellung_amount_eur=_m("0.00"),
        taxable_gain_after_teilfreistellung_eur=_m("-30.00"),
    )
    ledger = _make_ledger()
    ledger.tax_impacts = [etf_gain, div_impact, bond_loss]
    ledger = _split_into_pots(ledger)
    ledger = _apply_within_year_offset(ledger)
    ledger = _apply_carryforward(ledger)

    assert ledger.general_pot is not None
    # €70 + €50 - €30 = €90 taxable in general pot
    assert ledger.general_pot.taxable_after_offset_eur == _m("90.0000")


# --- Carryforward ---

def test_prior_year_carryforward_consumed_first() -> None:
    # Aktien gain €500 this year, prior carryforward €700 → aktien taxable = 0
    # Remaining carryforward = €700 - €500 = €200
    ledger = _make_ledger(prior_aktien=_m("700.00"))
    ledger.tax_impacts = [_make_aktie_impact("500.00")]
    ledger = _split_into_pots(ledger)
    ledger = _apply_within_year_offset(ledger)
    ledger = _apply_carryforward(ledger)

    assert ledger.aktien_pot is not None
    assert ledger.aktien_pot.taxable_after_offset_eur == _ZERO
    assert ledger.aktien_pot.remaining_carryforward_eur == _m("200.0000")


# --- Sparerpauschbetrag ---

def test_sparerpauschbetrag_capped_at_taxable_amount() -> None:
    # €600 taxable, €1000 allowance → consumed = €600, remaining = €400
    ledger = _make_ledger()
    ledger.tax_impacts = [_make_aktie_impact("600.00")]
    ledger = _split_into_pots(ledger)
    ledger = _apply_within_year_offset(ledger)
    ledger = _apply_carryforward(ledger)
    ledger = _apply_sparerpauschbetrag(ledger)

    assert ledger.sparerpauschbetrag_consumed == _m("600.0000")
    assert ledger.sparerpauschbetrag_remaining == _m("400.0000")
    assert ledger.taxable_after_allowance == _ZERO


def test_sparerpauschbetrag_consumes_from_combined_pots() -> None:
    # €400 aktien + ETF gain €1000 → after TF €700 general = €1100 total
    # allowance €1000 → taxable_after_allowance = €100
    ledger = _make_ledger()
    ledger.tax_impacts = [
        _make_aktie_impact("400.00"),
        _make_etf_impact("1000.00"),  # €700 after TF
    ]
    ledger = _split_into_pots(ledger)
    ledger = _apply_within_year_offset(ledger)
    ledger = _apply_carryforward(ledger)

    assert ledger.aktien_pot is not None
    assert ledger.general_pot is not None
    total = (
        ledger.aktien_pot.taxable_after_offset_eur.amount
        + ledger.general_pot.taxable_after_offset_eur.amount
    )
    assert total == Decimal("1100.0000")

    ledger = _apply_sparerpauschbetrag(ledger)
    assert ledger.sparerpauschbetrag_consumed == _m("1000.0000")
    assert ledger.taxable_after_allowance == _m("100.0000")


def test_joint_filing_doubles_allowance() -> None:
    # €600 taxable, joint → allowance = €2000, consumed = €600, remaining = €1400
    ledger = _make_ledger(profile=_JOINT)
    ledger.tax_impacts = [_make_aktie_impact("600.00")]
    ledger = _split_into_pots(ledger)
    ledger = _apply_within_year_offset(ledger)
    ledger = _apply_carryforward(ledger)
    ledger = _apply_sparerpauschbetrag(ledger)

    assert ledger.sparerpauschbetrag_total == _m("2000.0000")
    assert ledger.sparerpauschbetrag_consumed == _m("600.0000")
    assert ledger.sparerpauschbetrag_remaining == _m("1400.0000")


# --- Abgeltungsteuer + Soli ---

def test_abgeltungsteuer_is_25_percent() -> None:
    ledger = _make_ledger()
    ledger.taxable_after_allowance = _m("1000.00")
    ledger = _compute_abgeltungsteuer(ledger)
    assert ledger.abgeltungsteuer == _m("250.0000")


def test_soli_is_5_5_percent_of_tax_not_of_taxable() -> None:
    ledger = _make_ledger()
    ledger.abgeltungsteuer = _m("250.00")
    ledger = _compute_soli(ledger)
    assert ledger.solidaritaetszuschlag == _m("13.7500")


def test_effective_rate_calculation() -> None:
    # €1000 gross (AKTIE, 0% TF) → zero allowance → abgeltungsteuer €250 + soli €13.75
    # effective rate = 263.75 / 1000 × 100 = 26.375%
    # Use zero-allowance rates so full taxable passes through
    zero_allowance_rates = TaxYearRates(
        sparerpauschbetrag_single=_m("0"),
        sparerpauschbetrag_joint=_m("0"),
        abgeltungsteuer_rate=Decimal("0.25"),
        solidaritaetszuschlag_rate=Decimal("0.055"),
        teilfreistellung=TAX_RATES_2026.teilfreistellung,
    )
    ledger = _make_ledger(rates=zero_allowance_rates)
    ledger.tax_impacts = [_make_aktie_impact("1000.00")]
    ledger = _split_into_pots(ledger)
    ledger = _apply_within_year_offset(ledger)
    ledger = _apply_carryforward(ledger)
    ledger = _apply_sparerpauschbetrag(ledger)
    ledger = _compute_abgeltungsteuer(ledger)
    ledger = _compute_soli(ledger)
    summary = _finalise(ledger)

    assert summary.abgeltungsteuer_eur == _m("250.0000")
    assert summary.solidaritaetszuschlag_eur == _m("13.7500")
    assert summary.total_tax_owed_eur == _m("263.7500")
    assert summary.effective_tax_rate_pct is not None
    assert abs(summary.effective_tax_rate_pct - Decimal("26.375")) < Decimal("0.001")
