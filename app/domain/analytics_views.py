from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.domain.money import Currency, Money


class ConcentrationRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    name: str
    weight_pct: Decimal
    value_eur: Money
    currency: Currency
    thesis_status: str | None = None
    staleness_reason: str | None = None

    @field_validator("weight_pct")
    @classmethod
    def validate_weight_pct(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("weight_pct must be non-negative")
        return value

    @field_validator("value_eur")
    @classmethod
    def validate_value_eur(cls, value: Money) -> Money:
        if value.currency != Currency.EUR:
            raise ValueError("value_eur must be EUR-denominated")
        if value.amount < 0:
            raise ValueError("value_eur must be non-negative")
        return value


class ConcentrationView(BaseModel):
    model_config = ConfigDict(frozen=True)

    top_1_pct: Decimal
    top_3_pct: Decimal
    herfindahl: Decimal
    weights_by_ticker: list[tuple[str, Decimal]]
    currency_split: list[tuple[Currency, Decimal]]
    rows: list[ConcentrationRow]

    @field_validator("top_1_pct", "top_3_pct", "herfindahl")
    @classmethod
    def validate_non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("concentration values must be non-negative")
        return value

    @model_validator(mode="after")
    def validate_top_3_includes_top_1(self) -> ConcentrationView:
        if self.top_3_pct < self.top_1_pct:
            raise ValueError("top_3_pct must be greater than or equal to top_1_pct")
        return self
