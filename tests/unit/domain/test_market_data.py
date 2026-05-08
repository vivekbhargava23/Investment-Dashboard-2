from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.market_data import (
    ChartPeriod,
    OhlcBar,
    OhlcSeries,
    OhlcUnavailableError,
    aggregate_ohlc_series,
)
from app.domain.money import Currency


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=UTC)


def _bar(ts: str, o: str = "100", h: str = "110", lo: str = "95", c: str = "105") -> OhlcBar:
    return OhlcBar(
        timestamp=_utc(ts),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(lo),
        close=Decimal(c),
        volume=1000,
    )


def _series(*bars: OhlcBar, period: ChartPeriod = ChartPeriod.SIX_MONTH) -> OhlcSeries:
    return OhlcSeries(
        ticker="NVDA",
        currency=Currency.USD,
        period=period,
        bars=tuple(bars),
        fetched_at=_utc("2024-07-01"),
    )


# --- ChartPeriod.is_intraday ---

def test_is_intraday_one_day() -> None:
    assert ChartPeriod.ONE_DAY.is_intraday is True


def test_is_intraday_five_day() -> None:
    assert ChartPeriod.FIVE_DAY.is_intraday is True


def test_not_intraday_one_month() -> None:
    assert ChartPeriod.ONE_MONTH.is_intraday is False


def test_not_intraday_six_month() -> None:
    assert ChartPeriod.SIX_MONTH.is_intraday is False


def test_not_intraday_ytd() -> None:
    assert ChartPeriod.YEAR_TO_DATE.is_intraday is False


# --- OhlcBar happy path ---

def test_ohlcbar_happy_path() -> None:
    bar = _bar("2024-01-02")
    assert bar.open == Decimal("100")
    assert bar.high == Decimal("110")
    assert bar.low == Decimal("95")
    assert bar.close == Decimal("105")
    assert bar.volume == 1000


def test_ohlcbar_frozen() -> None:
    bar = _bar("2024-01-02")
    with pytest.raises(Exception):
        bar.open = Decimal("999")  # type: ignore[misc]


# --- OhlcBar validators ---

def test_ohlcbar_rejects_open_above_high() -> None:
    with pytest.raises(ValueError):
        OhlcBar(
            timestamp=_utc("2024-01-02"),
            open=Decimal("115"),
            high=Decimal("110"),
            low=Decimal("95"),
            close=Decimal("105"),
            volume=None,
        )


def test_ohlcbar_rejects_close_below_low() -> None:
    with pytest.raises(ValueError):
        OhlcBar(
            timestamp=_utc("2024-01-02"),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("95"),
            close=Decimal("90"),
            volume=None,
        )


def test_ohlcbar_rejects_negative_open() -> None:
    with pytest.raises(ValueError):
        OhlcBar(
            timestamp=_utc("2024-01-02"),
            open=Decimal("-1"),
            high=Decimal("5"),
            low=Decimal("-2"),
            close=Decimal("3"),
            volume=None,
        )


def test_ohlcbar_rejects_zero_price() -> None:
    with pytest.raises(ValueError):
        OhlcBar(
            timestamp=_utc("2024-01-02"),
            open=Decimal("0"),
            high=Decimal("0"),
            low=Decimal("0"),
            close=Decimal("0"),
            volume=None,
        )


def test_ohlcbar_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError):
        OhlcBar(
            timestamp=datetime(2024, 1, 2),  # naive
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("95"),
            close=Decimal("105"),
            volume=None,
        )


def test_ohlcbar_none_volume_allowed() -> None:
    bar = OhlcBar(
        timestamp=_utc("2024-01-02"),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("95"),
        close=Decimal("105"),
        volume=None,
    )
    assert bar.volume is None


# --- OhlcSeries validators ---

def test_ohlcseries_rejects_empty_bars() -> None:
    with pytest.raises(ValueError):
        OhlcSeries(
            ticker="NVDA",
            currency=Currency.USD,
            period=ChartPeriod.SIX_MONTH,
            bars=(),
            fetched_at=_utc("2024-07-01"),
        )


def test_ohlcseries_rejects_unsorted_bars() -> None:
    with pytest.raises(ValueError, match="sorted"):
        _series(_bar("2024-01-03"), _bar("2024-01-02"))


def test_ohlcseries_latest_close() -> None:
    s = _series(_bar("2024-01-02", c="105"), _bar("2024-01-03", c="110"))
    assert s.latest_close == Decimal("110")


def test_ohlcseries_period_change_pct() -> None:
    s = _series(
        _bar("2024-01-02", o="100", h="115", lo="95", c="110"),
        _bar("2024-01-03", o="110", h="125", lo="105", c="120"),
    )
    expected = (Decimal("120") - Decimal("100")) / Decimal("100") * Decimal("100")
    assert s.period_change_pct == expected


def test_ohlcseries_period_change_pct_zero_open() -> None:
    # OhlcBar rejects open=0, so this case is only reachable if someone bypasses
    # validation. We test the property's None branch via model_construct.
    bar = OhlcBar.model_construct(
        timestamp=_utc("2024-01-02"),
        open=Decimal("0"),
        high=Decimal("1"),
        low=Decimal("0"),
        close=Decimal("1"),
        volume=None,
    )
    s = OhlcSeries.model_construct(
        ticker="NVDA",
        currency=Currency.USD,
        period=ChartPeriod.SIX_MONTH,
        bars=(bar,),
        fetched_at=_utc("2024-07-01"),
    )
    assert s.period_change_pct is None


# --- OhlcUnavailableError ---

def test_ohlc_unavailable_error_has_reason() -> None:
    err = OhlcUnavailableError(reason="no data")
    assert err.reason == "no data"
    assert "no data" in str(err)


# --- aggregate_ohlc_series ---

def test_aggregate_day_collapses_same_day_bars() -> None:
    s = _series(
        _bar("2024-01-02T09:30", "100", "112", "98", "105"),
        _bar("2024-01-02T10:00", "105", "115", "103", "110"),
        _bar("2024-01-02T10:30", "110", "120", "108", "118"),
    )
    result = aggregate_ohlc_series(s, "day")
    assert len(result.bars) == 1
    bar = result.bars[0]
    assert bar.open == Decimal("100")
    assert bar.high == Decimal("120")
    assert bar.low == Decimal("98")
    assert bar.close == Decimal("118")
    assert bar.volume == 3000


def test_aggregate_day_multiple_days() -> None:
    s = _series(
        _bar("2024-01-02T09:30", "100", "110", "95", "105"),
        _bar("2024-01-02T10:00", "105", "112", "103", "108"),
        _bar("2024-01-03T09:30", "108", "115", "106", "112"),
    )
    result = aggregate_ohlc_series(s, "day")
    assert len(result.bars) == 2
    assert result.bars[0].open == Decimal("100")
    assert result.bars[1].open == Decimal("108")


def test_aggregate_week_collapses_same_week_bars() -> None:
    # 2024-01-02 (Tue) and 2024-01-05 (Fri) are in the same ISO week (week 1)
    s = _series(
        _bar("2024-01-02", "200", "210", "195", "205"),
        _bar("2024-01-03", "205", "215", "202", "210"),
        _bar("2024-01-05", "210", "220", "208", "218"),
    )
    result = aggregate_ohlc_series(s, "week")
    assert len(result.bars) == 1
    bar = result.bars[0]
    assert bar.open == Decimal("200")   # first bar's open
    assert bar.close == Decimal("218")  # last bar's close
    assert bar.high == Decimal("220")
    assert bar.low == Decimal("195")


def test_aggregate_month_collapses_same_month_bars() -> None:
    s = _series(
        _bar("2024-01-02", "300", "310", "295", "305"),
        _bar("2024-01-15", "305", "315", "300", "312"),
        _bar("2024-01-31", "312", "320", "308", "318"),
    )
    result = aggregate_ohlc_series(s, "month")
    assert len(result.bars) == 1
    bar = result.bars[0]
    assert bar.open == Decimal("300")
    assert bar.close == Decimal("318")


def test_aggregate_preserves_series_metadata() -> None:
    s = _series(_bar("2024-01-02"), _bar("2024-01-03"))
    result = aggregate_ohlc_series(s, "week")
    assert result.ticker == s.ticker
    assert result.currency == s.currency
    assert result.period == s.period
    assert result.fetched_at == s.fetched_at


def test_aggregate_volume_summed() -> None:
    s = _series(
        _bar("2024-01-02T09:00", "100", "110", "95", "105"),
        _bar("2024-01-02T10:00", "105", "112", "103", "108"),
    )
    result = aggregate_ohlc_series(s, "day")
    assert result.bars[0].volume == 2000


def test_aggregate_all_none_volumes_stays_none() -> None:
    b1 = OhlcBar(
        timestamp=_utc("2024-01-02T09:00"),
        open=Decimal("100"), high=Decimal("110"),
        low=Decimal("95"), close=Decimal("105"), volume=None,
    )
    b2 = OhlcBar(
        timestamp=_utc("2024-01-02T10:00"),
        open=Decimal("105"), high=Decimal("112"),
        low=Decimal("103"), close=Decimal("108"), volume=None,
    )
    s = _series(b1, b2)
    result = aggregate_ohlc_series(s, "day")
    assert result.bars[0].volume is None


def test_aggregate_timestamp_is_first_bar_of_bucket() -> None:
    s = _series(
        _bar("2024-01-02T09:30", "100", "110", "95", "105"),
        _bar("2024-01-02T15:00", "105", "112", "103", "108"),
    )
    result = aggregate_ohlc_series(s, "day")
    assert result.bars[0].timestamp == _utc("2024-01-02T09:30")
