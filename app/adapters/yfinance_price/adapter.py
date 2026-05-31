import time
from datetime import date, timedelta
from decimal import Decimal

from app.adapters._yfinance_client import yf
from app.domain.money import Money
from app.domain.tickers import infer_currency_from_ticker
from app.ports.price_feed import PriceUnavailableError, TickerNotFoundError


class YfinancePriceAdapter:
    """PriceProvider backed by yfinance with in-memory TTL cache."""

    def __init__(self, current_ttl_seconds: int = 60) -> None:
        self.current_ttl_seconds = current_ttl_seconds
        self._current_cache: dict[str, tuple[float, Money]] = {}
        self._historical_cache: dict[str, Money] = {}

    def get_current_price(self, ticker: str) -> Money:
        cache_key = f"price:{ticker}"
        now = time.monotonic()

        if cache_key in self._current_cache:
            ts, value = self._current_cache[cache_key]
            if now - ts < self.current_ttl_seconds:
                return value

        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            price = info.get("lastPrice")

            if price is None or (isinstance(price, float) and price != price):
                hist = t.history(period="1d")
                if not hist.empty:
                    price = hist["Close"].iloc[-1]

            if price is None or (isinstance(price, float) and price != price):
                raise TickerNotFoundError(ticker, "yfinance returned no current price")

            currency = infer_currency_from_ticker(ticker)
            amount = Decimal(str(price)).quantize(Decimal("0.0001"))
            money = Money(amount=amount, currency=currency)

            self._current_cache[cache_key] = (now, money)
            return money

        except TickerNotFoundError:
            raise
        except Exception as e:
            raise PriceUnavailableError(ticker, str(e)) from e

    def get_historical_close(self, ticker: str, on_date: date) -> Money:
        cache_key = f"price:{ticker}:{on_date.isoformat()}"
        if cache_key in self._historical_cache:
            return self._historical_cache[cache_key]

        try:
            t = yf.Ticker(ticker)
            hist = t.history(start=on_date, end=on_date + timedelta(days=1))

            if hist.empty:
                hist = t.history(start=on_date - timedelta(days=7), end=on_date + timedelta(days=1))

            if hist.empty:
                raise PriceUnavailableError(ticker, f"No historical close near {on_date}")

            price = hist["Close"].iloc[-1]
            if price != price:  # NaN
                raise PriceUnavailableError(ticker, f"NaN historical close near {on_date}")

            currency = infer_currency_from_ticker(ticker)
            amount = Decimal(str(price)).quantize(Decimal("0.0001"))
            money = Money(amount=amount, currency=currency)

            self._historical_cache[cache_key] = money
            return money

        except PriceUnavailableError:
            raise
        except Exception as e:
            raise PriceUnavailableError(ticker, str(e)) from e

    def clear_cache(self) -> None:
        self._current_cache.clear()
        self._historical_cache.clear()
