from datetime import date
from decimal import Decimal

from app.domain.money import Currency
from app.ports.fx_feed import FxRateUnavailableError


class FakeFxProvider:
    """Fake implementation of FxProvider for testing."""

    def __init__(
        self,
        current_rates: dict[tuple[Currency, Currency], Decimal] | None = None,
        historical_rates: dict[tuple[Currency, Currency, date], Decimal] | None = None,
    ):
        self.current_rates = current_rates or {}
        self.historical_rates = historical_rates or {}

    def get_current_rate(self, base: Currency, quote: Currency) -> Decimal:
        key = (base, quote)
        if key not in self.current_rates:
            raise FxRateUnavailableError(base, quote, None, "Rate not in fake")
        return self.current_rates[key]

    def get_historical_rate(self, base: Currency, quote: Currency, on_date: date) -> Decimal:
        key = (base, quote, on_date)
        if key not in self.historical_rates:
            raise FxRateUnavailableError(base, quote, on_date, "Rate not in fake")
        return self.historical_rates[key]

    def clear_cache(self) -> None:
        pass

    def set_rate(self, base: Currency, quote: Currency, rate: Decimal) -> None:
        self.current_rates[(base, quote)] = rate

    def set_historical_rate(
        self, base: Currency, quote: Currency, on_date: date, rate: Decimal
    ) -> None:
        self.historical_rates[(base, quote, on_date)] = rate
