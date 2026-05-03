from datetime import date
from decimal import Decimal
from typing import Protocol

from app.domain.money import Currency


class FxRateUnavailableError(Exception):
    """Base exception for all FX feed failures."""

    def __init__(
        self, base: Currency, quote: Currency, on_date: date | None, reason: str
    ):
        date_part = f" on {on_date}" if on_date else ""
        super().__init__(f"FX rate unavailable for {base}/{quote}{date_part}: {reason}")
        self.base = base
        self.quote = quote
        self.on_date = on_date
        self.reason = reason


class UnsupportedCurrencyPairError(FxRateUnavailableError):
    """Raised when the requested currency pair is not supported by the provider."""

    pass


class FxProvider(Protocol):
    """Abstract contract for fetching current and historical FX rates."""

    def get_current_rate(self, base: Currency, quote: Currency) -> Decimal:
        """Returns rate as quote_per_base (e.g., USD per 1 EUR)."""
        ...

    def get_historical_rate(
        self, base: Currency, quote: Currency, on_date: date
    ) -> Decimal:
        """Returns rate as quote_per_base for a specific past date."""
        ...

    def clear_cache(self) -> None:
        """Invalidate all cached rates."""
        ...
