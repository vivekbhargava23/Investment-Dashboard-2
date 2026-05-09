from __future__ import annotations

from decimal import Decimal
from typing import Literal

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


class CurrentPositionCard(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    name: str
    weight_pct: Decimal
    market_value_eur: Money
    last_price_native: Money
    last_price_eur: Money
    open_lot_count: int
    staleness: str | None = None

    @field_validator("weight_pct")
    @classmethod
    def validate_weight_pct(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("weight_pct must be non-negative")
        return value

    @field_validator("market_value_eur", "last_price_eur")
    @classmethod
    def validate_eur_money(cls, value: Money) -> Money:
        if value.currency != Currency.EUR:
            raise ValueError("EUR money fields must be EUR-denominated")
        return value

    @field_validator("market_value_eur", "last_price_native", "last_price_eur")
    @classmethod
    def validate_non_negative_money(cls, value: Money) -> Money:
        if value.amount < 0:
            raise ValueError("money amounts must be non-negative")
        return value

    @field_validator("open_lot_count")
    @classmethod
    def validate_open_lot_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("open_lot_count must be non-negative")
        return value


class RiskBasedResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    shares: Decimal
    trade_value_eur: Money
    risk_eur: Money
    risk_pct_input: Decimal
    stop_price_native: Money

    @field_validator("trade_value_eur", "risk_eur")
    @classmethod
    def validate_eur_money(cls, value: Money) -> Money:
        if value.currency != Currency.EUR:
            raise ValueError("EUR money fields must be EUR-denominated")
        return value

    @field_validator("trade_value_eur", "risk_eur", "stop_price_native")
    @classmethod
    def validate_non_negative_money(cls, value: Money) -> Money:
        if value.amount < 0:
            raise ValueError("money amounts must be non-negative")
        return value


class WeightBasedResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    shares: Decimal
    delta_eur: Money
    current_weight_pct: Decimal
    target_weight_pct: Decimal

    @field_validator("delta_eur")
    @classmethod
    def validate_delta_eur(cls, value: Money) -> Money:
        if value.currency != Currency.EUR:
            raise ValueError("delta_eur must be EUR-denominated")
        return value

    @field_validator("current_weight_pct", "target_weight_pct")
    @classmethod
    def validate_weight_pct(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("weight values must be non-negative")
        return value


class PostTradeWeightPreview(BaseModel):
    model_config = ConfigDict(frozen=True)

    current_weight_pct: Decimal
    new_weight_pct: Decimal
    bucket: Literal["green", "amber", "red"]

    @field_validator("current_weight_pct", "new_weight_pct")
    @classmethod
    def validate_weight_pct(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("weight values must be non-negative")
        return value


class SizerView(BaseModel):
    model_config = ConfigDict(frozen=True)

    current: CurrentPositionCard
    risk_based: RiskBasedResult | None
    weight_based: WeightBasedResult | None
    post_trade: PostTradeWeightPreview | None
    degraded_reason: str | None = None
