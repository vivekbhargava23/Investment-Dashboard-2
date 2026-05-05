import time
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import yfinance as yf

from app.domain.money import Currency, Money
from app.domain.tickers import infer_currency_from_ticker
from app.ports.fx_feed import (
    FxRateUnavailableError,
    UnsupportedCurrencyPairError,
)
from app.ports.price_feed import (
    PriceUnavailableError,
    TickerNotFoundError,
)


class YfinanceAdapter:
    """
    Adapter for yfinance providing both stock prices and FX rates.
    Includes in-memory caching with TTL for current values.
    """

    def __init__(self, current_ttl_seconds: int = 60):
        self.current_ttl_seconds = current_ttl_seconds
        # Key: "price:{ticker}" or "fx:{base}/{quote}"
        # Value: (timestamp, value)
        self._current_cache: dict[str, tuple[float, Any]] = {}
        # Key: "price:{ticker}:{date}" or "fx:{base}/{quote}:{date}"
        # Value: value
        self._historical_cache: dict[str, Any] = {}

    def _infer_currency(self, ticker: str) -> Currency:
        return infer_currency_from_ticker(ticker)

    def get_current_price(self, ticker: str) -> Money:
        cache_key = f"price:{ticker}"
        now = time.monotonic()

        if cache_key in self._current_cache:
            ts, value = self._current_cache[cache_key]
            if now - ts < self.current_ttl_seconds:
                return value  # type: ignore

        try:
            t = yf.Ticker(ticker)
            # Try fast_info first as it's faster
            info = t.fast_info
            price = info.get("lastPrice")

            # Fallback to history if fast_info is missing price
            if price is None or (isinstance(price, float) and price != price):  # NaN check
                hist = t.history(period="1d")
                if not hist.empty:
                    price = hist["Close"].iloc[-1]

            if price is None or (isinstance(price, float) and price != price):
                raise TickerNotFoundError(ticker, "yfinance returned no current price")

            currency = self._infer_currency(ticker)
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
            return self._historical_cache[cache_key]  # type: ignore

        try:
            t = yf.Ticker(ticker)
            # yfinance history is half-open [start, end)
            hist = t.history(start=on_date, end=on_date + timedelta(days=1))

            if hist.empty:
                # Expand search window to 7 days prior to handle weekends/holidays
                hist = t.history(start=on_date - timedelta(days=7), end=on_date + timedelta(days=1))

            if hist.empty:
                raise PriceUnavailableError(ticker, f"No historical close near {on_date}")

            price = hist["Close"].iloc[-1]
            if price != price:  # NaN
                raise PriceUnavailableError(ticker, f"NaN historical close near {on_date}")

            currency = self._infer_currency(ticker)
            amount = Decimal(str(price)).quantize(Decimal("0.0001"))
            money = Money(amount=amount, currency=currency)

            self._historical_cache[cache_key] = money
            return money

        except PriceUnavailableError:
            raise
        except Exception as e:
            raise PriceUnavailableError(ticker, str(e)) from e

    # Canonical yfinance tickers for currency pairs (base=first named, quote=second).
    # For reversed pairs, we fetch the canonical ticker and invert.
    _FX_CANONICAL: dict[tuple[Currency, Currency], str] = {
        (Currency.EUR, Currency.USD): "EURUSD=X",
        (Currency.EUR, Currency.JPY): "EURJPY=X",
        (Currency.USD, Currency.JPY): "USDJPY=X",
    }

    _SUPPORTED_PAIRS: frozenset[tuple[Currency, Currency]] = frozenset({
        (Currency.EUR, Currency.USD),
        (Currency.USD, Currency.EUR),
        (Currency.EUR, Currency.JPY),
        (Currency.JPY, Currency.EUR),
        (Currency.USD, Currency.JPY),
        (Currency.JPY, Currency.USD),
    })

    def _fx_yfinance_ticker(self, base: Currency, quote: Currency) -> tuple[str, bool]:
        """Return (yfinance_ticker, invert) for the given pair."""
        if (base, quote) in self._FX_CANONICAL:
            return self._FX_CANONICAL[(base, quote)], False
        return self._FX_CANONICAL[(quote, base)], True

    def get_current_rate(self, base: Currency, quote: Currency) -> Decimal:
        if (base, quote) not in self._SUPPORTED_PAIRS:
            raise UnsupportedCurrencyPairError(
                base, quote, None,
                "Supported pairs: EUR/USD, USD/EUR, EUR/JPY, JPY/EUR, USD/JPY, JPY/USD"
            )

        cache_key = f"fx:{base}/{quote}"
        now = time.monotonic()

        if cache_key in self._current_cache:
            ts, value = self._current_cache[cache_key]
            if now - ts < self.current_ttl_seconds:
                return value  # type: ignore

        try:
            yf_ticker, invert = self._fx_yfinance_ticker(base, quote)
            t = yf.Ticker(yf_ticker)
            rate_raw = t.fast_info.get("lastPrice")

            if rate_raw is None or (isinstance(rate_raw, float) and rate_raw != rate_raw):
                hist = t.history(period="1d")
                if not hist.empty:
                    rate_raw = hist["Close"].iloc[-1]

            if rate_raw is None or (isinstance(rate_raw, float) and rate_raw != rate_raw):
                raise FxRateUnavailableError(
                    base, quote, None, "yfinance returned no current rate"
                )

            rate = Decimal(str(rate_raw))
            if invert:
                rate = Decimal("1") / rate

            rate = rate.quantize(Decimal("0.000001"))
            self._current_cache[cache_key] = (now, rate)
            return rate

        except FxRateUnavailableError:
            raise
        except Exception as e:
            raise FxRateUnavailableError(base, quote, None, str(e)) from e

    def get_historical_rate(self, base: Currency, quote: Currency, on_date: date) -> Decimal:
        if (base, quote) not in self._SUPPORTED_PAIRS:
            raise UnsupportedCurrencyPairError(
                base, quote, on_date,
                "Supported pairs: EUR/USD, USD/EUR, EUR/JPY, JPY/EUR, USD/JPY, JPY/USD"
            )

        cache_key = f"fx:{base}/{quote}:{on_date.isoformat()}"
        if cache_key in self._historical_cache:
            return self._historical_cache[cache_key]  # type: ignore

        try:
            yf_ticker, invert = self._fx_yfinance_ticker(base, quote)
            t = yf.Ticker(yf_ticker)
            hist = t.history(start=on_date, end=on_date + timedelta(days=1))

            if hist.empty:
                hist = t.history(start=on_date - timedelta(days=7), end=on_date + timedelta(days=1))

            if hist.empty:
                raise FxRateUnavailableError(base, quote, on_date, f"No rate near {on_date}")

            rate_raw = hist["Close"].iloc[-1]
            if rate_raw != rate_raw:  # NaN
                raise FxRateUnavailableError(base, quote, on_date, f"NaN rate near {on_date}")

            rate = Decimal(str(rate_raw))
            if invert:
                rate = Decimal("1") / rate

            rate = rate.quantize(Decimal("0.000001"))
            self._historical_cache[cache_key] = rate
            return rate

        except FxRateUnavailableError:
            raise
        except Exception as e:
            raise FxRateUnavailableError(base, quote, on_date, str(e)) from e

    def clear_cache(self) -> None:
        self._current_cache.clear()
        self._historical_cache.clear()
