from datetime import date
from typing import Protocol

from app.domain.money import Money


class PriceUnavailableError(Exception):
    """Base exception for all price feed failures."""

    def __init__(self, ticker: str, reason: str):
        super().__init__(f"Price unavailable for {ticker}: {reason}")
        self.ticker = ticker
        self.reason = reason


class TickerNotFoundError(PriceUnavailableError):
    """Raised when the price provider returns empty or 404 for a ticker."""

    pass


class PriceProvider(Protocol):
    """Abstract contract for fetching current and historical ticker prices."""

    def get_current_price(self, ticker: str) -> Money:
        """Fetch the most recent traded price for a ticker."""
        ...

    def get_historical_close(self, ticker: str, on_date: date) -> Money:
        """Fetch the close price for a specific past date."""
        ...

    def clear_cache(self) -> None:
        """Invalidate all cached prices."""
        ...
