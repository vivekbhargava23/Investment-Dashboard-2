from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries, OhlcUnavailableError
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
