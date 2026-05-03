from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.domain.money import Currency, Money


class RealisedGain(BaseModel):
    model_config = ConfigDict(frozen=True)

    sell_transaction_id: str
    buy_transaction_id: str
    ticker: str
    shares: Decimal
    sell_date: date
    buy_date: date
    proceeds_eur: Money
    cost_basis_eur: Money
    realised_gain_eur: Money
    holding_period_days: int

    @field_validator("ticker")
    @classmethod
    def ticker_must_be_uppercase(cls, v: str) -> str:
        if v.upper() != v:
            raise ValueError("Ticker must be uppercase")
        return v

    @field_validator("shares")
    @classmethod
    def shares_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Shares must be positive")
        return v

    @model_validator(mode="after")
    def validate_currencies(self) -> RealisedGain:
        if self.proceeds_eur.currency != Currency.EUR:
            raise ValueError("proceeds_eur must be in EUR")
        if self.cost_basis_eur.currency != Currency.EUR:
            raise ValueError("cost_basis_eur must be in EUR")
        if self.realised_gain_eur.currency != Currency.EUR:
            raise ValueError("realised_gain_eur must be in EUR")
        return self

    @model_validator(mode="after")
    def validate_math(self) -> RealisedGain:
        expected_gain = self.proceeds_eur.amount - self.cost_basis_eur.amount
        if abs(self.realised_gain_eur.amount - expected_gain) > Decimal("0.01"):
            raise ValueError(
                f"realised_gain_eur ({self.realised_gain_eur.amount}) does not match "
                f"proceeds ({self.proceeds_eur.amount}) - cost ({self.cost_basis_eur.amount})"
            )
        return self

    @model_validator(mode="after")
    def validate_dates(self) -> RealisedGain:
        if self.holding_period_days < 0:
            raise ValueError("holding_period_days cannot be negative")
        if (self.sell_date - self.buy_date).days != self.holding_period_days:
            raise ValueError("holding_period_days must match date difference")
        return self

    @property
    def is_loss(self) -> bool:
        return self.realised_gain_eur.amount < 0
