"""
app/core/position.py

Position model: one ticker's transactions, metadata, and live-price-derived calculations.
live_price is injected by the price service — the Position never fetches it.
UI receives a fully calculated Position and only renders.

Open lots and realised disposals are derived by replaying the transaction log.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from app.core.lot import OpenLot, RealisedDisposal, replay_transactions
from app.core.transaction import Transaction


class ThesisStatus(str, Enum):
    INTACT = "intact"
    WATCH = "watch"
    BROKEN = "broken"


class Horizon(str, Enum):
    H1 = "H1"  # 0–6 months
    H2 = "H2"  # 6–18 months
    H3 = "H3"  # 18–36 months


class Position(BaseModel):
    """
    One equity position: transactions grouped under a ticker with metadata.

    Calculated properties (current_value, unrealised_gain, unrealised_gain_pct)
    return None until live_price is injected.
    average_cost is display-only — tax calculations always use FIFO, not average cost.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ticker: str
    name: str = Field(description="Display name e.g. 'SK Hynix GDR'")
    transactions: list[Transaction] = Field(default_factory=list)
    live_price: float | None = None
    tags: list[str] = Field(default_factory=list)
    horizon: Horizon | None = None
    thesis_status: ThesisStatus = ThesisStatus.INTACT
    thesis_notes: str = ""

    @field_validator("ticker", mode="before")
    @classmethod
    def normalise_ticker(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("live_price", mode="before")
    @classmethod
    def validate_live_price(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError(f"live_price must be positive, got {v}")
        return v

    # ------------------------------------------------------------------ replay

    @property
    def _replayed(self) -> tuple[list[OpenLot], list[RealisedDisposal]]:
        return replay_transactions(self.transactions)

    @property
    def open_lots(self) -> list[OpenLot]:
        return self._replayed[0]

    @property
    def realised_disposals(self) -> list[RealisedDisposal]:
        return self._replayed[1]

    # ------------------------------------------------------------------ derived

    @property
    def total_shares(self) -> float:
        return sum(lot.shares for lot in self.open_lots)

    @property
    def total_cost_basis(self) -> float:
        return sum(lot.purchase_price * lot.shares for lot in self.open_lots)

    @property
    def average_cost(self) -> float | None:
        """Weighted average cost per share. Display only — never use for tax."""
        if self.total_shares == 0:
            return None
        return self.total_cost_basis / self.total_shares

    @property
    def lot_count(self) -> int:
        return len(self.open_lots)

    # ---------------------------------------------------------- price-dependent

    @property
    def current_value(self) -> float | None:
        if self.live_price is None:
            return None
        return self.live_price * self.total_shares

    @property
    def unrealised_gain(self) -> float | None:
        cv = self.current_value
        if cv is None:
            return None
        return cv - self.total_cost_basis

    @property
    def unrealised_gain_pct(self) -> float | None:
        """Unrealised gain as a decimal ratio (0.15 = 15%). None if no live price."""
        ug = self.unrealised_gain
        if ug is None or self.total_cost_basis == 0:
            return None
        return ug / self.total_cost_basis

    @property
    def has_live_price(self) -> bool:
        return self.live_price is not None

    # ------------------------------------------------------------------ helpers

    def with_price(self, price: float) -> Position:
        """Return a new Position with live_price set. Used by the price service."""
        return self.model_copy(update={"live_price": price})

