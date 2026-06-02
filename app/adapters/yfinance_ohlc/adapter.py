import logging
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from app.adapters._yfinance_client import yf
from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries, OhlcUnavailableError
from app.domain.money import Currency
from app.domain.tickers import infer_currency_from_ticker

_log = logging.getLogger(__name__)

_OHLC_INTRADAY_TTL = 15 * 60.0
_OHLC_DAILY_TTL = 24 * 60 * 60.0

# Cap concurrency so a large portfolio doesn't hammer yfinance with one thread per ticker.
_MAX_WORKERS = 8

_INTERVAL_MAP: dict[ChartPeriod, str] = {
    ChartPeriod.ONE_DAY: "5m",
    ChartPeriod.FIVE_DAY: "15m",
}
_DEFAULT_INTERVAL = "1d"


class YfinanceOhlcAdapter:
    """OhlcDataProvider backed by yfinance with in-memory TTL cache."""

    def __init__(self) -> None:
        self._ohlc_cache: dict[tuple[str, ChartPeriod], tuple[float, OhlcSeries]] = {}

    @staticmethod
    def _interval_for_period(period: ChartPeriod) -> str:
        return _INTERVAL_MAP.get(period, _DEFAULT_INTERVAL)

    @staticmethod
    def _ttl_for_period(period: ChartPeriod) -> float:
        return _OHLC_INTRADAY_TTL if period.is_intraday else _OHLC_DAILY_TTL

    def _cached_series(
        self, ticker: str, period: ChartPeriod, now: float
    ) -> OhlcSeries | None:
        """Return a still-fresh cached series, or None on miss/expiry."""
        key = (ticker, period)
        if key in self._ohlc_cache:
            ts, cached = self._ohlc_cache[key]
            if now - ts < self._ttl_for_period(period):
                return cached
        return None

    def _fetch_series(self, ticker: str, period: ChartPeriod) -> OhlcSeries:
        """Network fetch + parse for a single ticker. Raises on failure; no caching.

        Shared by the single-ticker and batch paths so currency inference, NaN
        handling, and bar construction can never drift between them.
        """
        interval = self._interval_for_period(period)
        df = yf.Ticker(ticker).history(period=period.value, interval=interval, auto_adjust=False)

        if df.empty:
            raise OhlcUnavailableError(
                reason=f"yfinance returned no data for {ticker} period={period.value}"
            )

        bars: list[OhlcBar] = []
        for row in df.itertuples():
            try:
                ts_bar = row.Index.to_pydatetime().astimezone(UTC)
                bar = OhlcBar(
                    timestamp=ts_bar,
                    open=Decimal(str(row.Open)),
                    high=Decimal(str(row.High)),
                    low=Decimal(str(row.Low)),
                    close=Decimal(str(row.Close)),
                    volume=int(row.Volume) if pd.notna(row.Volume) else None,
                )
                bars.append(bar)
            except (ValueError, AttributeError) as exc:
                _log.warning("Skipping malformed OHLC row for %s: %s", ticker, exc)

        if not bars:
            raise OhlcUnavailableError(
                reason=f"yfinance returned no usable bars for {ticker} period={period.value}"
            )

        currency: Currency = infer_currency_from_ticker(ticker)
        return OhlcSeries(
            ticker=ticker,
            currency=currency,
            period=period,
            bars=tuple(bars),
            fetched_at=datetime.now(tz=UTC),
        )

    def get_ohlc_history(self, ticker: str, period: ChartPeriod) -> OhlcSeries:
        now = time.monotonic()
        cached = self._cached_series(ticker, period, now)
        if cached is not None:
            return cached

        series = self._fetch_series(ticker, period)
        self._ohlc_cache[(ticker, period)] = (now, series)
        return series

    def get_ohlc_histories(
        self, tickers: Sequence[str], period: ChartPeriod
    ) -> dict[str, OhlcSeries]:
        now = time.monotonic()
        result: dict[str, OhlcSeries] = {}
        misses: list[str] = []

        for ticker in dict.fromkeys(tickers):  # dedupe, preserve order
            cached = self._cached_series(ticker, period, now)
            if cached is not None:
                result[ticker] = cached
            else:
                misses.append(ticker)

        if not misses:
            return result

        # yfinance is blocking I/O; threads parallelise the network round-trips.
        with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(misses))) as pool:
            fetched = pool.map(lambda t: self._fetch_series_safe(t, period), misses)

        for ticker, series in zip(misses, fetched):
            if series is not None:
                self._ohlc_cache[(ticker, period)] = (now, series)
                result[ticker] = series

        return result

    def _fetch_series_safe(self, ticker: str, period: ChartPeriod) -> OhlcSeries | None:
        """Batch helper: isolate per-ticker failures so one bad ticker never fails the batch."""
        try:
            return self._fetch_series(ticker, period)
        except OhlcUnavailableError:
            return None

    def clear_cache(self) -> None:
        self._ohlc_cache.clear()
