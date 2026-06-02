import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal

from app.adapters._yfinance_client import yf
from app.domain.money import Money
from app.domain.tickers import infer_currency_from_ticker
from app.ports.price_feed import PriceUnavailableError, TickerNotFoundError

# Cap concurrency so a large portfolio doesn't hammer yfinance with one thread per ticker.
_MAX_WORKERS = 8


class YfinancePriceAdapter:
    """PriceProvider backed by yfinance with in-memory TTL cache."""

    def __init__(self, current_ttl_seconds: int = 60) -> None:
        self.current_ttl_seconds = current_ttl_seconds
        self._current_cache: dict[str, tuple[float, Money]] = {}
        self._historical_cache: dict[str, Money] = {}

    def _cached_price(self, ticker: str, now: float) -> Money | None:
        """Return a still-fresh cached price for ticker, or None on miss/expiry."""
        cache_key = f"price:{ticker}"
        if cache_key in self._current_cache:
            ts, value = self._current_cache[cache_key]
            if now - ts < self.current_ttl_seconds:
                return value
        return None

    def _fetch_current_price(self, ticker: str) -> Money:
        """Network fetch + parse for a single ticker. Raises on failure; no caching.

        Shared by the single-ticker and batch paths so currency inference, NaN
        handling, and error wrapping can never drift between them.
        """
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
            return Money(amount=amount, currency=currency)

        except TickerNotFoundError:
            raise
        except Exception as e:
            raise PriceUnavailableError(ticker, str(e)) from e

    def get_current_price(self, ticker: str) -> Money:
        now = time.monotonic()
        cached = self._cached_price(ticker, now)
        if cached is not None:
            return cached

        money = self._fetch_current_price(ticker)
        self._current_cache[f"price:{ticker}"] = (now, money)
        return money

    def get_current_prices(self, tickers: Sequence[str]) -> dict[str, Money]:
        now = time.monotonic()
        result: dict[str, Money] = {}
        misses: list[str] = []

        for ticker in dict.fromkeys(tickers):  # dedupe, preserve order
            cached = self._cached_price(ticker, now)
            if cached is not None:
                result[ticker] = cached
            else:
                misses.append(ticker)

        if not misses:
            return result

        # yfinance is blocking I/O; threads parallelise the network round-trips.
        with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(misses))) as pool:
            fetched = pool.map(self._fetch_current_price_safe, misses)

        for ticker, money in zip(misses, fetched):
            if money is not None:
                self._current_cache[f"price:{ticker}"] = (now, money)
                result[ticker] = money

        return result

    def _fetch_current_price_safe(self, ticker: str) -> Money | None:
        """Batch helper: isolate per-ticker failures so one bad ticker never fails the batch."""
        try:
            return self._fetch_current_price(ticker)
        except PriceUnavailableError:
            return None

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
