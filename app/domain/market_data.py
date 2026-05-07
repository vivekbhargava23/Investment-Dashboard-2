from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self

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
        return self in {ChartPeriod.ONE_DAY, ChartPeriod.FIVE_DAY}


class OhlcUnavailableError(Exception):
    """Raised when OHLC history cannot be fetched for a ticker."""

    def __init__(self, ticker: str, reason: str):
        super().__init__(f"OHLC unavailable for {ticker}: {reason}")
        self.ticker = ticker
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
    def timestamp_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("OhlcBar.timestamp must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_prices(self) -> Self:
        prices = (self.open, self.high, self.low, self.close)
        if any(price <= 0 for price in prices):
            raise ValueError(f"OhlcBar prices must be positive at {self.timestamp.isoformat()}")
        if not (self.low <= self.open <= self.high):
            raise ValueError(
                f"OhlcBar open must be within low/high at {self.timestamp.isoformat()}"
            )
        if not (self.low <= self.close <= self.high):
            raise ValueError(
                f"OhlcBar close must be within low/high at {self.timestamp.isoformat()}"
            )
        return self


class OhlcSeries(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    currency: Currency
    period: ChartPeriod
    bars: tuple[OhlcBar, ...]
    fetched_at: datetime

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("fetched_at")
    @classmethod
    def fetched_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("OhlcSeries.fetched_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_bars(self) -> Self:
        if not self.bars:
            raise ValueError("OhlcSeries.bars must be non-empty")
        timestamps = tuple(bar.timestamp for bar in self.bars)
        if timestamps != tuple(sorted(timestamps)):
            raise ValueError("OhlcSeries.bars must be sorted by timestamp")
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
