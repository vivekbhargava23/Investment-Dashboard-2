from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.domain.money import Currency, Money


class OpenLot(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_transaction_id: str
    ticker: str
    trade_date: date
    remaining_shares: Decimal
    cost_per_share_native: Money
    fx_rate_eur: Decimal

    @model_validator(mode="after")
    def validate_shares(self) -> OpenLot:
        if self.remaining_shares < 0:
            raise ValueError("Remaining shares cannot be negative")
        return self

    @property
    def cost_basis_eur(self) -> Money:
        amount_eur = (
            self.remaining_shares * self.cost_per_share_native.amount * self.fx_rate_eur
        )
        return Money(amount=amount_eur, currency=Currency.EUR)


class Position(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    open_shares: Decimal
    open_lots: tuple[OpenLot, ...]
    realised_gain_eur_ytd: Money
    cost_basis_eur: Money

    @model_validator(mode="after")
    def validate_position_consistency(self) -> Position:
        # Check ticker consistency
        for lot in self.open_lots:
            if lot.ticker != self.ticker:
                raise ValueError(
                    f"Lot ticker {lot.ticker} does not match position ticker {self.ticker}"
                )

        # Check shares sum
        sum_shares = sum((lot.remaining_shares for lot in self.open_lots), Decimal("0"))
        if (
            sum_shares.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            != self.open_shares.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        ):
            raise ValueError(
                f"Position shares ({self.open_shares}) mismatch sum of lots ({sum_shares})"
            )

        # Check cost basis sum
        sum_cost_basis_eur = sum(
            (lot.cost_basis_eur.amount for lot in self.open_lots), Decimal("0")
        )
        if (
            sum_cost_basis_eur.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            != self.cost_basis_eur.amount.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        ):
            raise ValueError(
                f"Position cost basis ({self.cost_basis_eur.amount}) "
                f"mismatch sum of lots ({sum_cost_basis_eur})"
            )

        return self


class LivePosition(BaseModel):
    """
    Combines a Position with its live valuation data.
    """

    model_config = ConfigDict(frozen=True)

    position: Position
    live_price_native: Money | None
    live_value_eur: Money | None
    unrealised_gain_eur: Money | None
    unrealised_gain_pct: Decimal | None
    current_fx_rate: Decimal | None
    staleness_reason: str | None

    @model_validator(mode="after")
    def validate_valuation_consistency(self) -> LivePosition:
        if self.live_price_native is None:
            if any(
                v is not None
                for v in [
                    self.live_value_eur,
                    self.unrealised_gain_eur,
                    self.unrealised_gain_pct,
                ]
            ):
                raise ValueError("Cannot have value without live price")

        if self.live_price_native is None or self.live_value_eur is None:
            if self.staleness_reason is None:
                raise ValueError("Stale positions must have a staleness_reason")
        else:
            if self.staleness_reason is not None:
                raise ValueError("Live positions should not have a staleness_reason")

        return self

    @property
    def is_stale(self) -> bool:
        return self.live_price_native is None or self.live_value_eur is None

    @property
    def ticker(self) -> str:
        return self.position.ticker


class PortfolioSummary(BaseModel):
    """
    Aggregated KPIs for the entire portfolio.
    """

    model_config = ConfigDict(frozen=True)

    total_value_eur: Money
    total_cost_basis_eur: Money
    total_unrealised_gain_eur: Money
    total_unrealised_gain_pct: Decimal
    total_realised_gain_eur_ytd: Money
    position_count: int
    live_position_count: int
    staleness: Literal["live", "partial", "stale"]
    as_of: datetime
