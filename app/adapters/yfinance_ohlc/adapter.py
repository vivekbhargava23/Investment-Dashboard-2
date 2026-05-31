import logging
import time
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

    def get_ohlc_history(self, ticker: str, period: ChartPeriod) -> OhlcSeries:
        key = (ticker, period)
        now = time.monotonic()
        if key in self._ohlc_cache:
            ts, cached = self._ohlc_cache[key]
            if now - ts < self._ttl_for_period(period):
                return cached

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

        currency: Currency = infer_currency_from_ticker(ticker)
        series = OhlcSeries(
            ticker=ticker,
            currency=currency,
            period=period,
            bars=tuple(bars),
            fetched_at=datetime.now(tz=UTC),
        )
        self._ohlc_cache[key] = (now, series)
        return series

    def clear_cache(self) -> None:
        self._ohlc_cache.clear()
