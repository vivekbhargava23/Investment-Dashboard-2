from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries
from app.domain.money import Currency


def _bar(
    timestamp: datetime = datetime(2026, 1, 1, tzinfo=UTC),
    open_: Decimal = Decimal("100"),
    high: Decimal = Decimal("110"),
    low: Decimal = Decimal("90"),
    close: Decimal = Decimal("105"),
) -> OhlcBar:
    return OhlcBar(
        timestamp=timestamp,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100,
    )


def test_ohlc_bar_happy_path_and_frozen() -> None:
    bar = _bar()

    assert bar.open == Decimal("100")
    with pytest.raises(ValidationError):
        bar.close = Decimal("106")  # type: ignore[misc]


@pytest.mark.parametrize(
    ("open_", "high", "low", "close"),
    [
        (Decimal("120"), Decimal("110"), Decimal("90"), Decimal("105")),
        (Decimal("100"), Decimal("110"), Decimal("90"), Decimal("80")),
    ],
)
def test_ohlc_bar_validates_integrity(
    open_: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
) -> None:
    with pytest.raises(ValidationError):
        _bar(open_=open_, high=high, low=low, close=close)


def test_ohlc_bar_rejects_non_positive_prices() -> None:
    with pytest.raises(ValidationError):
        _bar(open_=Decimal("-1"))


def test_ohlc_bar_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        _bar(timestamp=datetime(2026, 1, 1))


def test_ohlc_series_validates_non_empty_and_sorting() -> None:
    with pytest.raises(ValidationError):
        OhlcSeries(
            ticker="NVDA",
            currency=Currency.USD,
            period=ChartPeriod.SIX_MONTH,
            bars=(),
            fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
        )

    first = _bar()
    second = _bar(timestamp=first.timestamp + timedelta(days=1))
    with pytest.raises(ValidationError):
        OhlcSeries(
            ticker="NVDA",
            currency=Currency.USD,
            period=ChartPeriod.SIX_MONTH,
            bars=(second, first),
            fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
        )


def test_ohlc_series_helpers() -> None:
    first = _bar(open_=Decimal("100"), close=Decimal("105"))
    second = _bar(
        timestamp=first.timestamp + timedelta(days=1),
        open_=Decimal("105"),
        high=Decimal("125"),
        low=Decimal("100"),
        close=Decimal("120"),
    )

    series = OhlcSeries(
        ticker="nvda",
        currency=Currency.USD,
        period=ChartPeriod.SIX_MONTH,
        bars=(first, second),
        fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert series.ticker == "NVDA"
    assert series.latest_close == Decimal("120")
    assert series.period_change_pct == Decimal("20.0")


def test_chart_period_is_intraday() -> None:
    assert ChartPeriod.ONE_DAY.is_intraday
    assert ChartPeriod.FIVE_DAY.is_intraday
    assert not ChartPeriod.ONE_MONTH.is_intraday
    assert not ChartPeriod.YEAR_TO_DATE.is_intraday
