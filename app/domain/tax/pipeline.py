"""Internal tax pipeline. Not exported — use engine.compute_tax_year_summary."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.isin_map import IsinMapDocument
from app.domain.money import Currency, Money
from app.domain.realised_gain import RealisedGain
from app.domain.tax.classification import InstrumentKind, classify_instrument
from app.domain.tax.models import (
    FilingStatus,
    LossPotState,
    TaxImpact,
    TaxProfile,
    TaxYearSummary,
)
from app.domain.tax.rates import TaxYearRates

_EUR = Currency.EUR
_AKTIEN_KINDS = frozenset({InstrumentKind.AKTIE})


@dataclass
class TaxYearLedger:
    """Mutable intermediate state passed between pipeline steps. Internal only."""

    year: int
    rates: TaxYearRates
    profile: TaxProfile
    realised_gains: list[RealisedGain]
    prior_aktien_carryforward: Money
    prior_general_carryforward: Money
    additional_dividend_income_eur: Money
    additional_interest_income_eur: Money
    isin_map: IsinMapDocument = field(default_factory=IsinMapDocument)

    # Populated by _classify_and_apply_teilfreistellung
    tax_impacts: list[TaxImpact] = field(default_factory=list)

    # Populated by _split_into_pots
    aktien_impacts: list[TaxImpact] = field(default_factory=list)
    general_impacts: list[TaxImpact] = field(default_factory=list)

    # Populated by _apply_within_year_offset
    aktien_current_year_gains: Money = field(
        default_factory=lambda: Money.zero(Currency.EUR)
    )
    aktien_current_year_losses: Money = field(
        default_factory=lambda: Money.zero(Currency.EUR)
    )
    general_current_year_gains: Money = field(
        default_factory=lambda: Money.zero(Currency.EUR)
    )
    general_current_year_losses: Money = field(
        default_factory=lambda: Money.zero(Currency.EUR)
    )

    # Populated by _apply_carryforward
    aktien_pot: LossPotState | None = None
    general_pot: LossPotState | None = None

    # Populated by _apply_sparerpauschbetrag
    total_taxable_after_loss_offset: Money = field(
        default_factory=lambda: Money.zero(Currency.EUR)
    )
    sparerpauschbetrag_total: Money = field(
        default_factory=lambda: Money.zero(Currency.EUR)
    )
    sparerpauschbetrag_consumed: Money = field(
        default_factory=lambda: Money.zero(Currency.EUR)
    )
    sparerpauschbetrag_remaining: Money = field(
        default_factory=lambda: Money.zero(Currency.EUR)
    )
    taxable_after_allowance: Money = field(
        default_factory=lambda: Money.zero(Currency.EUR)
    )

    # Populated by _compute_abgeltungsteuer
    abgeltungsteuer: Money = field(default_factory=lambda: Money.zero(Currency.EUR))

    # Populated by _compute_soli
    solidaritaetszuschlag: Money = field(
        default_factory=lambda: Money.zero(Currency.EUR)
    )


def _classify_and_apply_teilfreistellung(ledger: TaxYearLedger) -> TaxYearLedger:
    impacts: list[TaxImpact] = []
    for gain in ledger.realised_gains:
        kind = classify_instrument(gain.ticker, ledger.isin_map)
        pct = ledger.rates.teilfreistellung[kind]
        gross = gain.realised_gain_eur
        amount = gross * pct
        taxable = gross * (Decimal("1") - pct)
        impacts.append(
            TaxImpact(
                instrument_kind=kind,
                gross_gain_eur=gross,
                teilfreistellung_pct=pct,
                teilfreistellung_amount_eur=amount,
                taxable_gain_after_teilfreistellung_eur=taxable,
            )
        )
    ledger.tax_impacts = impacts
    return ledger


def _split_into_pots(ledger: TaxYearLedger) -> TaxYearLedger:
    aktien: list[TaxImpact] = []
    general: list[TaxImpact] = []
    for impact in ledger.tax_impacts:
        if impact.instrument_kind in _AKTIEN_KINDS:
            aktien.append(impact)
        else:
            general.append(impact)
    ledger.aktien_impacts = aktien
    ledger.general_impacts = general
    return ledger


def _apply_within_year_offset(ledger: TaxYearLedger) -> TaxYearLedger:
    # Aktien pot: only AKTIE impacts
    aktien_gains = Money.zero(_EUR)
    aktien_losses = Money.zero(_EUR)
    for impact in ledger.aktien_impacts:
        taxable = impact.taxable_gain_after_teilfreistellung_eur
        if taxable.amount >= Decimal("0"):
            aktien_gains = aktien_gains + taxable
        else:
            aktien_losses = aktien_losses + Money(
                amount=-taxable.amount, currency=_EUR
            )

    # General pot: non-AKTIE impacts + dividends + interest
    general_gains = Money.zero(_EUR)
    general_losses = Money.zero(_EUR)
    for impact in ledger.general_impacts:
        taxable = impact.taxable_gain_after_teilfreistellung_eur
        if taxable.amount >= Decimal("0"):
            general_gains = general_gains + taxable
        else:
            general_losses = general_losses + Money(
                amount=-taxable.amount, currency=_EUR
            )
    # Dividends and interest are always positive income in the general pot
    general_gains = (
        general_gains
        + ledger.additional_dividend_income_eur
        + ledger.additional_interest_income_eur
    )

    ledger.aktien_current_year_gains = aktien_gains
    ledger.aktien_current_year_losses = aktien_losses
    ledger.general_current_year_gains = general_gains
    ledger.general_current_year_losses = general_losses
    return ledger


def _apply_carryforward(ledger: TaxYearLedger) -> TaxYearLedger:
    ledger.aktien_pot = _build_pot_state(
        prior_carryforward=ledger.prior_aktien_carryforward,
        current_gains=ledger.aktien_current_year_gains,
        current_losses=ledger.aktien_current_year_losses,
    )
    ledger.general_pot = _build_pot_state(
        prior_carryforward=ledger.prior_general_carryforward,
        current_gains=ledger.general_current_year_gains,
        current_losses=ledger.general_current_year_losses,
    )
    return ledger


def _build_pot_state(
    prior_carryforward: Money,
    current_gains: Money,
    current_losses: Money,
) -> LossPotState:
    total_available = prior_carryforward + current_losses
    consumed = Money(
        amount=min(total_available.amount, current_gains.amount),
        currency=_EUR,
    )
    remaining = total_available - consumed
    taxable = current_gains - consumed
    return LossPotState(
        prior_year_carryforward_eur=prior_carryforward,
        current_year_losses_eur=current_losses,
        current_year_gains_eur=current_gains,
        consumed_against_gains_eur=consumed,
        remaining_carryforward_eur=remaining,
        taxable_after_offset_eur=taxable,
    )


def _apply_sparerpauschbetrag(ledger: TaxYearLedger) -> TaxYearLedger:
    assert ledger.aktien_pot is not None
    assert ledger.general_pot is not None

    total_taxable = (
        ledger.aktien_pot.taxable_after_offset_eur
        + ledger.general_pot.taxable_after_offset_eur
    )
    if ledger.profile.filing_status == FilingStatus.JOINT:
        allowance = ledger.rates.sparerpauschbetrag_joint
    else:
        allowance = ledger.rates.sparerpauschbetrag_single

    # Cap at the available taxable amount — cannot consume more than what's taxable.
    consumed = Money(
        amount=min(allowance.amount, total_taxable.amount),
        currency=_EUR,
    )
    remaining = allowance - consumed
    taxable_after = total_taxable - consumed

    ledger.total_taxable_after_loss_offset = total_taxable
    ledger.sparerpauschbetrag_total = allowance
    ledger.sparerpauschbetrag_consumed = consumed
    ledger.sparerpauschbetrag_remaining = remaining
    ledger.taxable_after_allowance = taxable_after
    return ledger


def _compute_abgeltungsteuer(ledger: TaxYearLedger) -> TaxYearLedger:
    ledger.abgeltungsteuer = ledger.taxable_after_allowance * ledger.rates.abgeltungsteuer_rate
    return ledger


def _compute_soli(ledger: TaxYearLedger) -> TaxYearLedger:
    ledger.solidaritaetszuschlag = (
        ledger.abgeltungsteuer * ledger.rates.solidaritaetszuschlag_rate
    )
    return ledger


def _finalise(ledger: TaxYearLedger) -> TaxYearSummary:
    assert ledger.aktien_pot is not None
    assert ledger.general_pot is not None

    church_tax = Money.zero(_EUR)
    total_tax = ledger.abgeltungsteuer + ledger.solidaritaetszuschlag + church_tax

    gross_realised = sum(
        (i.gross_gain_eur.amount for i in ledger.tax_impacts),
        Decimal("0"),
    )
    effective_rate: Decimal | None = None
    if gross_realised > Decimal("0"):
        effective_rate = (total_tax.amount / gross_realised * Decimal("100")).quantize(
            Decimal("0.0001")
        )

    return TaxYearSummary(
        year=ledger.year,
        profile=ledger.profile,
        aktien_pot=ledger.aktien_pot,
        general_pot=ledger.general_pot,
        realised_gain_impacts=tuple(ledger.tax_impacts),
        additional_dividend_income_eur=ledger.additional_dividend_income_eur,
        additional_interest_income_eur=ledger.additional_interest_income_eur,
        total_taxable_after_loss_offset_eur=ledger.total_taxable_after_loss_offset,
        sparerpauschbetrag_total_eur=ledger.sparerpauschbetrag_total,
        sparerpauschbetrag_consumed_eur=ledger.sparerpauschbetrag_consumed,
        sparerpauschbetrag_remaining_eur=ledger.sparerpauschbetrag_remaining,
        taxable_after_allowance_eur=ledger.taxable_after_allowance,
        abgeltungsteuer_eur=ledger.abgeltungsteuer,
        solidaritaetszuschlag_eur=ledger.solidaritaetszuschlag,
        church_tax_eur=church_tax,
        total_tax_owed_eur=total_tax,
        effective_tax_rate_pct=effective_rate,
    )


def run_pipeline(ledger: TaxYearLedger) -> TaxYearSummary:
    """Execute all pipeline steps in the legally-mandated order."""
    ledger = _classify_and_apply_teilfreistellung(ledger)
    ledger = _split_into_pots(ledger)
    ledger = _apply_within_year_offset(ledger)
    ledger = _apply_carryforward(ledger)
    ledger = _apply_sparerpauschbetrag(ledger)
    ledger = _compute_abgeltungsteuer(ledger)
    ledger = _compute_soli(ledger)
    return _finalise(ledger)
