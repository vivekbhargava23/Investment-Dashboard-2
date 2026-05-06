"""Port (Protocol) for the tax profile repository."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict, model_validator

from app.domain.money import Currency, Money
from app.domain.tax.models import FilingStatus

_EUR = Currency.EUR
_ZERO = Money(amount=Decimal("0"), currency=_EUR)


class YearlyTaxInputs(BaseModel):
    """User-supplied carryforward and extra-income inputs for one fiscal year."""

    model_config = ConfigDict(frozen=True)

    carryforward_aktien_eur: Money = _ZERO
    carryforward_general_eur: Money = _ZERO
    additional_dividend_income_eur: Money = _ZERO
    additional_interest_income_eur: Money = _ZERO

    @model_validator(mode="after")
    def validate_all_eur(self) -> YearlyTaxInputs:
        for field_name in (
            "carryforward_aktien_eur",
            "carryforward_general_eur",
            "additional_dividend_income_eur",
            "additional_interest_income_eur",
        ):
            val: Money = getattr(self, field_name)
            if val.currency != _EUR:
                raise ValueError(f"{field_name} must be EUR")
        return self


class TaxProfileDocument(BaseModel):
    """Persisted tax profile: filing status + per-year carryforward inputs."""

    model_config = ConfigDict(frozen=True)

    version: int = 1
    filing_status: FilingStatus = FilingStatus.SINGLE
    per_year: dict[int, YearlyTaxInputs] = {}

    def inputs_for_year(self, year: int) -> YearlyTaxInputs:
        """Return inputs for the given year, defaulting to zeroes."""
        return self.per_year.get(year, YearlyTaxInputs())


class TaxProfileRepository(Protocol):
    """Abstract interface for loading and saving the user's tax profile."""

    def load(self) -> TaxProfileDocument:
        """Load the tax profile. Returns a default document if the file does not exist."""
        ...

    def save(self, doc: TaxProfileDocument) -> None:
        """Persist the tax profile atomically."""
        ...
