from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.money import Currency, Money


class DailyNavPoint(BaseModel):
    """Daily portfolio NAV snapshot.

    Represents the portfolio's EUR value at the end of a trading day.
    Historical points are reconstructed from OHLC + transaction history;
    today's point is computed live and never persisted.
    """

    model_config = ConfigDict(frozen=True)

    snapshot_date: date
    nav_eur: Money
    cost_basis_eur: Money
    n_positions: int
    is_reconstructed: bool

    @field_validator("nav_eur", "cost_basis_eur")
    @classmethod
    def _must_be_eur_and_non_negative(cls, v: Money) -> Money:
        if v.currency != Currency.EUR:
            raise ValueError(f"must be EUR, got {v.currency}")
        if v.amount < Decimal("0"):
            raise ValueError(f"must be non-negative, got {v.amount}")
        return v

    @field_validator("n_positions")
    @classmethod
    def _n_positions_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"n_positions must be non-negative, got {v}")
        return v
