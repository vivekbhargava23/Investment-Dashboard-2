"""
app/core/transaction.py

The append-only event log: every BUY and SELL the user has ever recorded.
Open lots and tax state are derived from this log — never stored directly.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


TransactionType = Literal["buy", "sell"]


class Transaction(BaseModel):
    """
    One trade event. Immutable record of intent.

    Fields:
        id: stable identifier for editing/deleting in the UI.
        ticker: equity symbol; normalised uppercase.
        trade_date: date of execution.
        trade_type: "buy" or "sell".
        shares: positive number of shares moved.
        price: per-share price in the position's native currency.
        fees: total fees in native currency, defaults 0.
        note: free-text annotation, optional.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ticker: str
    trade_date: date
    trade_type: TransactionType
    shares: float = Field(gt=0)
    price: float = Field(gt=0)
    fees: float = Field(default=0.0, ge=0)
    note: str = ""

    @field_validator("ticker", mode="before")
    @classmethod
    def normalise_ticker(cls, v: str) -> str:
        return v.strip().upper()

    @property
    def gross_value(self) -> float:
        """shares × price, native currency, no fees."""
        return self.shares * self.price
