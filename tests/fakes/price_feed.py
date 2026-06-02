from collections.abc import Sequence
from datetime import date

from app.domain.money import Money
from app.ports.price_feed import TickerNotFoundError


class FakePriceProvider:
    """Fake implementation of PriceProvider for testing."""

    def __init__(
        self,
        current_prices: dict[str, Money] | None = None,
        historical_prices: dict[tuple[str, date], Money] | None = None,
    ):
        self.current_prices = current_prices or {}
        self.historical_prices = historical_prices or {}
        self.batch_call_count = 0

    def get_current_price(self, ticker: str) -> Money:
        if ticker not in self.current_prices:
            raise TickerNotFoundError(ticker, "Price not in fake")
        return self.current_prices[ticker]

    def get_current_prices(self, tickers: Sequence[str]) -> dict[str, Money]:
        self.batch_call_count += 1
        return {t: self.current_prices[t] for t in tickers if t in self.current_prices}

    def get_historical_close(self, ticker: str, on_date: date) -> Money:
        key = (ticker, on_date)
        if key not in self.historical_prices:
            raise TickerNotFoundError(ticker, f"Historical price for {on_date} not in fake")
        return self.historical_prices[key]

    def clear_cache(self) -> None:
        pass

    def set_price(self, ticker: str, money: Money) -> None:
        self.current_prices[ticker] = money

    def set_historical_price(self, ticker: str, on_date: date, money: Money) -> None:
        self.historical_prices[(ticker, on_date)] = money
