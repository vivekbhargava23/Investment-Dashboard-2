from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from itertools import groupby
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.domain.money import Currency


class ChartPeriod(StrEnum):
    ONE_DAY = "1d"
    FIVE_DAY = "5d"
    ONE_MONTH = "1mo"
    THREE_MONTH = "3mo"
    SIX_MONTH = "6mo"
    ONE_YEAR = "1y"
    TWO_YEAR = "2y"
    FIVE_YEAR = "5y"
    YEAR_TO_DATE = "ytd"

    @property
    def is_intraday(self) -> bool:
        return self in (ChartPeriod.ONE_DAY, ChartPeriod.FIVE_DAY)


class OhlcUnavailableError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class OhlcBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None

    @field_validator("timestamp")
    @classmethod
    def _require_tzinfo(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError(f"OhlcBar.timestamp must be timezone-aware, got naive: {v}")
        return v

    @model_validator(mode="after")
    def _check_ohlc_integrity(self) -> OhlcBar:
        for price in (self.open, self.high, self.low, self.close):
            if price <= 0:
                raise ValueError(
                    f"OhlcBar prices must be positive at {self.timestamp}; got {price}"
                )
        if not (self.low <= self.open <= self.high):
            raise ValueError(
                f"OhlcBar integrity: low={self.low} <= open={self.open} <= high={self.high} "
                f"violated at {self.timestamp}"
            )
        if not (self.low <= self.close <= self.high):
            raise ValueError(
                f"OhlcBar integrity: low={self.low} <= close={self.close} <= high={self.high} "
                f"violated at {self.timestamp}"
            )
        return self


class OhlcSeries(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    currency: Currency
    period: ChartPeriod
    bars: tuple[OhlcBar, ...]
    fetched_at: datetime

    @field_validator("bars")
    @classmethod
    def _require_non_empty(cls, v: tuple[OhlcBar, ...]) -> tuple[OhlcBar, ...]:
        if len(v) == 0:
            raise ValueError("OhlcSeries.bars must be non-empty")
        return v

    @model_validator(mode="after")
    def _require_sorted(self) -> OhlcSeries:
        for i in range(1, len(self.bars)):
            if self.bars[i].timestamp <= self.bars[i - 1].timestamp:
                raise ValueError("OhlcSeries.bars must be sorted by timestamp ascending")
        return self

    @property
    def latest_close(self) -> Decimal:
        return self.bars[-1].close

    @property
    def period_change_pct(self) -> Decimal | None:
        first_open = self.bars[0].open
        if first_open == 0:
            return None
        return (self.latest_close - first_open) / first_open * Decimal("100")


AggregationFreq = Literal["hour", "day", "week", "month"]


def aggregate_ohlc_series(series: OhlcSeries, freq: AggregationFreq) -> OhlcSeries:
    """Aggregate OhlcBars to a coarser time frequency for display.

    Groups bars by calendar bucket; each bucket produces one bar:
        open  = first bar's open
        high  = max of all highs
        low   = min of all lows
        close = last bar's close
        volume = sum of non-None volumes, or None if all are None

    Use this to turn 252 daily bars (1Y) into ~52 weekly bars, or
    5-day intraday 15m bars into 5 clean daily bars.
    """
    def _key(bar: OhlcBar) -> tuple[int, ...]:
        ts = bar.timestamp
        if freq == "hour":
            return (ts.year, ts.month, ts.day, ts.hour)
        if freq == "day":
            return (ts.year, ts.month, ts.day)
        if freq == "week":
            iso = ts.isocalendar()
            return (iso.year, iso.week)
        # month
        return (ts.year, ts.month)

    aggregated: list[OhlcBar] = []
    for _, group_iter in groupby(series.bars, key=_key):
        group = list(group_iter)
        vols = [b.volume for b in group if b.volume is not None]
        aggregated.append(
            OhlcBar(
                timestamp=group[0].timestamp,
                open=group[0].open,
                high=max(b.high for b in group),
                low=min(b.low for b in group),
                close=group[-1].close,
                volume=sum(vols) if vols else None,
            )
        )

    if not aggregated:
        raise OhlcUnavailableError(
            f"No bars remain after aggregating {series.ticker} to {freq}"
        )

    return OhlcSeries(
        ticker=series.ticker,
        currency=series.currency,
        period=series.period,
        bars=tuple(aggregated),
        fetched_at=series.fetched_at,
    )
