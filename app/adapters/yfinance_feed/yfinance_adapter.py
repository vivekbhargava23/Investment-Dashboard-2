import logging
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import yfinance as yf

from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries, OhlcUnavailableError
from app.domain.money import Currency, Money
from app.domain.tickers import UnsupportedTickerError, infer_currency_from_ticker
from app.ports.fx_feed import (
    FxRateUnavailableError,
    UnsupportedCurrencyPairError,
)
from app.ports.price_feed import (
    PriceUnavailableError,
    TickerNotFoundError,
)
from app.ports.ticker_resolver import TickerMatch

_log = logging.getLogger(__name__)


_RESOLVER_TTL = 3600  # 1 hour — ticker metadata changes rarely


def _interval_for_period(period: ChartPeriod) -> str:
    if period == ChartPeriod.ONE_DAY:
        return "5m"
    if period == ChartPeriod.FIVE_DAY:
        return "15m"
    return "1d"


def _ttl_for_period(period: ChartPeriod) -> float:
    if period.is_intraday:
        return 15 * 60
    return 24 * 60 * 60


class YfinanceAdapter:
    """
    Adapter for yfinance providing stock prices, FX rates, and ticker search.
    Implements PriceProvider, FxProvider, and TickerResolver protocols.
    Includes in-memory caching with TTL for all lookups.
    """

    def __init__(self, current_ttl_seconds: int = 60):
        self.current_ttl_seconds = current_ttl_seconds
        # Key: "price:{ticker}" or "fx:{base}/{quote}"
        # Value: (timestamp, value)
        self._current_cache: dict[str, tuple[float, Any]] = {}
        # Key: "price:{ticker}:{date}" or "fx:{base}/{quote}:{date}"
        # Value: value
        self._historical_cache: dict[str, Any] = {}
        # Key: query string or "lookup:{symbol}"
        # Value: (timestamp, list[TickerMatch] | TickerMatch | None)
        self._resolver_cache: dict[str, tuple[float, Any]] = {}
        # Key: (ticker, period). Value: (timestamp, OhlcSeries)
        self._ohlc_cache: dict[tuple[str, ChartPeriod], tuple[float, OhlcSeries]] = {}

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

    def get_ohlc_history(self, ticker: str, period: ChartPeriod) -> OhlcSeries:
        normalized_ticker = ticker.strip().upper()
        cache_key = (normalized_ticker, period)
        now = time.monotonic()
        if cache_key in self._ohlc_cache:
            ts, cached = self._ohlc_cache[cache_key]
            if now - ts < _ttl_for_period(period):
                return cached

        yf_ticker = yf.Ticker(normalized_ticker)
        df = yf_ticker.history(
            period=period.value,
            interval=_interval_for_period(period),
            auto_adjust=False,
        )
        if df.empty:
            raise OhlcUnavailableError(
                normalized_ticker,
                f"yfinance returned no data for {normalized_ticker} period={period.value}",
            )

        bars: list[OhlcBar] = []
        for idx, row in df.iterrows():
            try:
                timestamp = idx.to_pydatetime().astimezone(UTC)
                raw_volume = row["Volume"]
                volume = None if raw_volume != raw_volume else int(raw_volume)
                bars.append(
                    OhlcBar(
                        timestamp=timestamp,
                        open=Decimal(str(row["Open"])),
                        high=Decimal(str(row["High"])),
                        low=Decimal(str(row["Low"])),
                        close=Decimal(str(row["Close"])),
                        volume=volume,
                    )
                )
            except ValueError as exc:
                _log.warning(
                    "Skipping invalid OHLC row for %s period=%s at %s: %s",
                    normalized_ticker,
                    period.value,
                    idx,
                    exc,
                )

        currency = infer_currency_from_ticker(normalized_ticker)
        try:
            series = OhlcSeries(
                ticker=normalized_ticker,
                currency=currency,
                period=period,
                bars=tuple(bars),
                fetched_at=datetime.now(UTC),
            )
        except ValueError as exc:
            raise OhlcUnavailableError(normalized_ticker, str(exc)) from exc

        self._ohlc_cache[cache_key] = (now, series)
        return series

    # ------------------------------------------------------------------
    # TickerResolver implementation
    # ------------------------------------------------------------------

    def _build_match(
        self,
        symbol: str,
        name: str,
        exchange: str,
        *,
        fetch_price: bool = True,
    ) -> TickerMatch | None:
        """
        Build a TickerMatch from raw fields.

        Returns None if the ticker's currency is not yet supported (e.g. HKD),
        so callers can silently omit unsupported results.
        """
        try:
            inferred = infer_currency_from_ticker(symbol)
        except UnsupportedTickerError:
            return None

        recent_price: Money | None = None
        if fetch_price:
            try:
                fi = yf.Ticker(symbol).fast_info
                raw = fi.get("lastPrice")
                if raw is not None and not (isinstance(raw, float) and raw != raw):
                    recent_price = Money(
                        amount=Decimal(str(raw)).quantize(Decimal("0.0001")),
                        currency=inferred,
                    )
            except Exception:
                pass  # recent_price stays None — non-critical

        return TickerMatch(
            symbol=symbol,
            name=name,
            exchange=exchange,
            currency=inferred,
            recent_price=recent_price,
        )

    def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]:
        """
        Fuzzy/prefix search for tickers matching *query*.

        Results whose native currency is not yet in the Currency enum are
        silently omitted — the form cannot record such transactions anyway.
        Empty query or no results returns [].
        """
        query = query.strip()
        if not query:
            return []

        cache_key = f"resolve:{query.upper()}:{limit}"
        now = time.monotonic()
        if cache_key in self._resolver_cache:
            ts, cached = self._resolver_cache[cache_key]
            if now - ts < _RESOLVER_TTL:
                return list(cached)

        results: list[TickerMatch] = []
        try:
            quotes = yf.Search(query, max_results=limit).quotes
            for q in quotes:
                symbol = q.get("symbol", "")
                if not symbol:
                    continue
                name = q.get("longname") or q.get("shortname") or symbol
                exchange = q.get("exchDisp") or q.get("exchange") or ""
                match = self._build_match(symbol, name, exchange, fetch_price=False)
                if match is not None:
                    results.append(match)
                if len(results) >= limit:
                    break
        except Exception as exc:
            _log.warning("yfinance Search failed for %r: %s", query, exc)

        self._resolver_cache[cache_key] = (now, results)
        return results

    def lookup(self, symbol: str) -> TickerMatch | None:
        """
        Exact-symbol metadata lookup. Returns None if the symbol is unknown
        or its currency is not yet supported.
        """
        symbol = symbol.strip().upper()
        if not symbol:
            return None

        cache_key = f"lookup:{symbol}"
        now = time.monotonic()
        if cache_key in self._resolver_cache:
            ts, cached = self._resolver_cache[cache_key]
            if now - ts < _RESOLVER_TTL:
                return cached if isinstance(cached, TickerMatch) else None

        result: TickerMatch | None = None
        try:
            info = yf.Ticker(symbol).info
            if info and info.get("symbol"):
                name = info.get("longName") or info.get("shortName") or symbol
                exchange = info.get("exchange") or ""
                result = self._build_match(symbol, name, exchange)
        except Exception as exc:
            _log.warning("yfinance Ticker.info failed for %r: %s", symbol, exc)

        self._resolver_cache[cache_key] = (now, result)
        return result

    def clear_cache(self) -> None:
        self._current_cache.clear()
        self._historical_cache.clear()
        self._resolver_cache.clear()
        self._ohlc_cache.clear()
