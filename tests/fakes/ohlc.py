from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries, OhlcUnavailableError
from app.domain.money import Currency


def make_ohlc_series(
    ticker: str = "NVDA",
    period: ChartPeriod = ChartPeriod.SIX_MONTH,
    currency: Currency = Currency.USD,
) -> OhlcSeries:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = (
        OhlcBar(
            timestamp=start,
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("95"),
            close=Decimal("108"),
            volume=1000,
        ),
        OhlcBar(
            timestamp=start + timedelta(days=1),
            open=Decimal("108"),
            high=Decimal("115"),
            low=Decimal("105"),
            close=Decimal("112"),
            volume=1200,
        ),
    )
    return OhlcSeries(
        ticker=ticker,
        currency=currency,
        period=period,
        bars=bars,
        fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


class FakeOhlcDataProvider:
    def __init__(self) -> None:
        self.call_count = 0
        self.clear_count = 0
        self.raise_for: set[tuple[str, ChartPeriod]] = set()

    def get_ohlc_history(self, ticker: str, period: ChartPeriod) -> OhlcSeries:
        self.call_count += 1
        key = (ticker.strip().upper(), period)
        if key in self.raise_for:
            raise OhlcUnavailableError(key[0], "fixture unavailable")
        return make_ohlc_series(ticker=key[0], period=period)

    def clear_cache(self) -> None:
        self.clear_count += 1
