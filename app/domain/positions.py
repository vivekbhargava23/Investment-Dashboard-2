from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

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
        sum_shares = sum(
            (lot.remaining_shares for lot in self.open_lots), Decimal("0")
        )
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
