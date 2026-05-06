"""Domain models for the German capital-gains tax engine."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from app.domain.money import Currency, Money
from app.domain.tax.classification import InstrumentKind


class FilingStatus(StrEnum):
    """German Veranlagungsform for Sparerpauschbetrag purposes."""

    SINGLE = "single"
    JOINT = "joint"


class TaxProfile(BaseModel):
    """User's tax profile for a given year."""

    model_config = ConfigDict(frozen=True)

    filing_status: FilingStatus
    # Placeholder: church tax is out of scope for v1. Field exists so the public
    # API does not change when TICKET-010c adds church-tax support.
    church_tax_rate: Decimal = Decimal("0")


class TaxImpact(BaseModel):
    """Per-RealisedGain tax breakdown (Teilfreistellung applied)."""

    model_config = ConfigDict(frozen=True)

    instrument_kind: InstrumentKind
    gross_gain_eur: Money
    teilfreistellung_pct: Decimal
    # For gains: positive (amount exempt). For losses: negative (portion not deductible).
    teilfreistellung_amount_eur: Money
    taxable_gain_after_teilfreistellung_eur: Money

    @model_validator(mode="after")
    def validate_currencies(self) -> TaxImpact:
        if self.gross_gain_eur.currency != Currency.EUR:
            raise ValueError("gross_gain_eur must be EUR")
        if self.teilfreistellung_amount_eur.currency != Currency.EUR:
            raise ValueError("teilfreistellung_amount_eur must be EUR")
        if self.taxable_gain_after_teilfreistellung_eur.currency != Currency.EUR:
            raise ValueError("taxable_gain_after_teilfreistellung_eur must be EUR")
        return self

    @model_validator(mode="after")
    def validate_math(self) -> TaxImpact:
        expected = self.gross_gain_eur - self.teilfreistellung_amount_eur
        diff = abs(
            self.taxable_gain_after_teilfreistellung_eur.amount - expected.amount
        )
        if diff > Decimal("0.01"):
            raise ValueError(
                f"taxable_gain_after_teilfreistellung_eur "
                f"({self.taxable_gain_after_teilfreistellung_eur.amount}) does not match "
                f"gross ({self.gross_gain_eur.amount}) - amount "
                f"({self.teilfreistellung_amount_eur.amount})"
            )
        return self


class LossPotState(BaseModel):
    """State of one Verlustverrechnungstopf (aktien or general) after the pipeline."""

    model_config = ConfigDict(frozen=True)

    prior_year_carryforward_eur: Money
    current_year_losses_eur: Money
    current_year_gains_eur: Money
    consumed_against_gains_eur: Money
    remaining_carryforward_eur: Money
    taxable_after_offset_eur: Money

    @model_validator(mode="after")
    def validate_all_eur(self) -> LossPotState:
        for field_name in (
            "prior_year_carryforward_eur",
            "current_year_losses_eur",
            "current_year_gains_eur",
            "consumed_against_gains_eur",
            "remaining_carryforward_eur",
            "taxable_after_offset_eur",
        ):
            val: Money = getattr(self, field_name)
            if val.currency != Currency.EUR:
                raise ValueError(f"{field_name} must be EUR")
        return self

    @model_validator(mode="after")
    def validate_taxable_non_negative(self) -> LossPotState:
        if self.taxable_after_offset_eur.amount < Decimal("0"):
            raise ValueError("taxable_after_offset_eur cannot be negative")
        return self


class TaxYearSummary(BaseModel):
    """Full output of the tax engine for a single fiscal year."""

    model_config = ConfigDict(frozen=True)

    year: int
    profile: TaxProfile
    aktien_pot: LossPotState
    general_pot: LossPotState
    realised_gain_impacts: tuple[TaxImpact, ...]
    additional_dividend_income_eur: Money
    additional_interest_income_eur: Money
    total_taxable_after_loss_offset_eur: Money
    sparerpauschbetrag_total_eur: Money
    sparerpauschbetrag_consumed_eur: Money
    sparerpauschbetrag_remaining_eur: Money
    taxable_after_allowance_eur: Money
    abgeltungsteuer_eur: Money
    solidaritaetszuschlag_eur: Money
    church_tax_eur: Money
    total_tax_owed_eur: Money
    effective_tax_rate_pct: Decimal | None

    @model_validator(mode="after")
    def validate_taxable_after_allowance_non_negative(self) -> TaxYearSummary:
        if self.taxable_after_allowance_eur.amount < Decimal("0"):
            raise ValueError("taxable_after_allowance_eur cannot be negative")
        return self
