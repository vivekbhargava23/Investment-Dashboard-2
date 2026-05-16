from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.money import Currency, Money
from app.domain.tickers import UnsupportedTickerError, infer_currency_from_ticker


class TransactionType(StrEnum):
    BUY = "buy"
    SELL = "sell"


class Transaction(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: TransactionType
    ticker: str
    trade_date: date
    shares: Decimal
    price_native: Money
    fees_native: Money | None = None
    fx_rate_eur: Decimal
    notes: str | None = None
    isin: str | None = None
    csv_reference: str | None = None
    source: Literal["scalable_csv", "manual", "switch", "unknown"] = "manual"

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

    @field_validator("fx_rate_eur")
    @classmethod
    def fx_rate_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("fx_rate_eur must be positive")
        return v

    @model_validator(mode="after")
    def validate_ticker_currency(self) -> Transaction:
        # Broker-sourced rows carry their own settlement currency; only manual entry is
        # validated against ticker inference (see ADR-005 amendment, TICKET-CSV-7).
        if self.source != "manual":
            return self
        try:
            inferred = infer_currency_from_ticker(self.ticker)
        except UnsupportedTickerError as e:
            raise ValueError(str(e)) from e
        if inferred != self.price_native.currency:
            raise ValueError(
                f"Ticker {self.ticker} trades in {inferred} but transaction recorded as "
                f"{self.price_native.currency}. See ADR-005."
            )
        return self

    @model_validator(mode="after")
    def validate_eur_fx_rate(self) -> Transaction:
        if self.price_native.currency == Currency.EUR:
            if self.fx_rate_eur != Decimal("1"):
                raise ValueError("fx_rate_eur must be 1 for EUR transactions")
        return self

    @model_validator(mode="after")
    def validate_fees_currency(self) -> Transaction:
        if self.fees_native and self.fees_native.currency != self.price_native.currency:
            raise ValueError("Fees must be in the same currency as price")
        return self

    @property
    def cost_native(self) -> Money:
        total = self.price_native * self.shares
        if self.fees_native:
            total += self.fees_native
        return total

    @property
    def cost_eur(self) -> Money:
        amount_eur = self.cost_native.amount * self.fx_rate_eur
        return Money(amount=amount_eur, currency=Currency.EUR)
