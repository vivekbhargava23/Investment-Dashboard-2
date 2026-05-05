from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator


class CurrencyMismatchError(Exception):
    """Raised when arithmetic or comparison is attempted between different currencies."""

    pass


class Currency(StrEnum):
    EUR = "EUR"
    USD = "USD"
    JPY = "JPY"



class Money(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: Decimal
    currency: Currency

    @field_validator("amount", mode="after")
    @classmethod
    def normalize_amount(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    @classmethod
    def zero(cls, currency: Currency) -> Self:
        return cls(amount=Decimal("0"), currency=currency)

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot add {self.currency} and {other.currency}"
            )
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot subtract {other.currency} from {self.currency}"
            )
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, other: Decimal | int) -> Money:
        if isinstance(other, (Decimal, int)):
            return Money(amount=self.amount * Decimal(other), currency=self.currency)
        return NotImplemented

    def __rmul__(self, other: Decimal | int) -> Money:
        return self.__mul__(other)

    def __truediv__(self, other: Money | Decimal | int) -> Decimal | Money:
        if isinstance(other, Money):
            if self.currency != other.currency:
                raise CurrencyMismatchError(
                    f"Cannot divide {self.currency} by {other.currency}"
                )
            if other.amount == 0:
                raise ZeroDivisionError()
            return self.amount / other.amount
        if isinstance(other, (Decimal, int)):
            if other == 0:
                raise ZeroDivisionError()
            return Money(amount=self.amount / Decimal(other), currency=self.currency)
        return NotImplemented

    def __neg__(self) -> Money:
        return Money(amount=-self.amount, currency=self.currency)

    def __lt__(self, other: Self) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot compare {self.currency} and {other.currency}"
            )
        return self.amount < other.amount

    def __le__(self, other: Self) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot compare {self.currency} and {other.currency}"
            )
        return self.amount <= other.amount

    def __gt__(self, other: Self) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot compare {self.currency} and {other.currency}"
            )
        return self.amount > other.amount

    def __ge__(self, other: Self) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot compare {self.currency} and {other.currency}"
            )
        return self.amount >= other.amount

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return False
        return self.currency == other.currency and self.amount == other.amount

    def __str__(self) -> str:
        if self.currency == Currency.EUR:
            return f"€{self.amount:,.2f}"
        if self.currency == Currency.JPY:
            return f"¥{self.amount:,.0f}"
        return f"${self.amount:,.2f}"
