"""Smoke tests for chart render functions. Verify figure shape via mocked st.plotly_chart."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import plotly.graph_objects as go

from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries
from app.domain.money import Currency
from app.ui.components._chart_styles import CANDLE_UP
from app.ui.components.charts import (
    _holiday_rangebreaks,
    _intraday_overnight_rangebreaks,
    _needs_weekend_rangebreaks,
    render_candlestick,
    render_line_chart,
    render_sparkline,
)
from tests.fakes.ohlc import FAKE_SERIES_NVDA_6MO


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=UTC)


def _bar(ts: str) -> OhlcBar:
    return OhlcBar(
        timestamp=_utc(ts),
        open=Decimal("100"), high=Decimal("110"),
        low=Decimal("95"), close=Decimal("105"), volume=1000,
    )


def _series(*bars: OhlcBar, period: ChartPeriod = ChartPeriod.SIX_MONTH) -> OhlcSeries:
    return OhlcSeries(
        ticker="TST", currency=Currency.USD, period=period,
        bars=tuple(bars), fetched_at=_utc("2024-07-01"),
    )


def test_render_candlestick_produces_candlestick_trace() -> None:
    with patch("app.ui.components.charts.st") as mock_st:
        render_candlestick(FAKE_SERIES_NVDA_6MO)
        mock_st.plotly_chart.assert_called_once()
        fig = mock_st.plotly_chart.call_args[0][0]
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1
        assert fig.data[0].type == "candlestick"


def test_render_line_chart_produces_scatter_lines_trace() -> None:
    with patch("app.ui.components.charts.st") as mock_st:
        render_line_chart(FAKE_SERIES_NVDA_6MO)
        mock_st.plotly_chart.assert_called_once()
        fig = mock_st.plotly_chart.call_args[0][0]
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1
        assert fig.data[0].type == "scatter"
        assert fig.data[0].mode == "lines"
        assert fig.layout.yaxis.tickprefix == "USD "


def test_render_sparkline_hides_axes() -> None:
    with patch("app.ui.components.charts.st") as mock_st:
        render_sparkline(FAKE_SERIES_NVDA_6MO)
        fig = mock_st.plotly_chart.call_args[0][0]
        assert fig.layout.xaxis.visible is False
        assert fig.layout.yaxis.visible is False


def test_render_line_chart_color_override() -> None:
    custom_color = "#ff0000"
    with patch("app.ui.components.charts.st") as mock_st:
        render_line_chart(FAKE_SERIES_NVDA_6MO, color=custom_color)
        fig = mock_st.plotly_chart.call_args[0][0]
        assert fig.data[0].line.color == custom_color


def test_render_sparkline_default_color_positive_change() -> None:
    # FAKE_SERIES_NVDA_6MO: first open=450, last close=472 → positive change → CANDLE_UP
    with patch("app.ui.components.charts.st") as mock_st:
        render_sparkline(FAKE_SERIES_NVDA_6MO)
        fig = mock_st.plotly_chart.call_args[0][0]
        assert fig.data[0].line.color == CANDLE_UP


# --- _needs_weekend_rangebreaks ---

def test_daily_series_needs_rangebreaks() -> None:
    """Bars spaced ~24h (daily) → True."""
    s = _series(_bar("2024-01-02"), _bar("2024-01-03"), _bar("2024-01-04"))
    assert _needs_weekend_rangebreaks(s) is True


def test_weekly_series_no_rangebreaks() -> None:
    """Bars spaced ~168h (weekly) → False."""
    s = _series(_bar("2024-01-02"), _bar("2024-01-09"), _bar("2024-01-16"))
    assert _needs_weekend_rangebreaks(s) is False


def test_intraday_series_no_rangebreaks() -> None:
    """Bars spaced 15min (intraday) → False."""
    s = _series(
        _bar("2024-01-02T09:30"), _bar("2024-01-02T09:45"), _bar("2024-01-02T10:00"),
        period=ChartPeriod.FIVE_DAY,
    )
    assert _needs_weekend_rangebreaks(s) is False


def test_single_bar_no_rangebreaks() -> None:
    """Single bar → can't compute avg spacing → False."""
    s = _series(_bar("2024-01-02"))
    assert _needs_weekend_rangebreaks(s) is False


# --- _holiday_rangebreaks ---

def test_holiday_rangebreaks_detects_missing_weekday() -> None:
    """Jan 2 and Jan 4 present; Jan 3 (Wednesday) is missing → included in values."""
    s = _series(_bar("2024-01-02"), _bar("2024-01-04"))
    breaks = _holiday_rangebreaks(s)
    assert len(breaks) == 1
    assert "2024-01-03" in breaks[0]["values"]


def test_holiday_rangebreaks_excludes_weekends_from_missing() -> None:
    """Jan 5 (Fri) to Jan 8 (Mon) skips Jan 6-7 (weekend) → no values."""
    s = _series(_bar("2024-01-05"), _bar("2024-01-08"))
    breaks = _holiday_rangebreaks(s)
    assert breaks == []


def test_holiday_rangebreaks_consecutive_days_no_missing() -> None:
    """Mon–Wed with no gaps → no holiday rangebreaks."""
    s = _series(_bar("2024-01-08"), _bar("2024-01-09"), _bar("2024-01-10"))
    breaks = _holiday_rangebreaks(s)
    assert breaks == []


def test_holiday_rangebreaks_single_bar_returns_empty() -> None:
    s = _series(_bar("2024-01-02"))
    assert _holiday_rangebreaks(s) == []


def test_holiday_rangebreaks_values_are_iso_strings() -> None:
    """Values must be ISO date strings (YYYY-MM-DD) not datetime strings."""
    s = _series(_bar("2024-01-02"), _bar("2024-01-04"))
    breaks = _holiday_rangebreaks(s)
    assert breaks[0]["values"][0] == "2024-01-03"


# --- _intraday_overnight_rangebreaks ---

def _intraday_bar(ts: str) -> OhlcBar:
    return OhlcBar(
        timestamp=datetime.fromisoformat(ts).replace(tzinfo=UTC),
        open=Decimal("100"), high=Decimal("110"),
        low=Decimal("95"), close=Decimal("105"), volume=1000,
    )


def _intraday_series(*bars: OhlcBar, ticker: str = "AAPL") -> OhlcSeries:
    return OhlcSeries(
        ticker=ticker, currency=Currency.USD, period=ChartPeriod.ONE_DAY,
        bars=tuple(bars), fetched_at=_utc("2024-07-01"),
    )


def test_intraday_overnight_derives_bounds_from_bar_hours() -> None:
    """NYSE: bars from 14:30–20:55 UTC → bounds [21, 14]."""
    bars = [_intraday_bar(f"2024-01-02T{h:02d}:30") for h in range(14, 21)]
    s = _intraday_series(*bars)
    breaks = _intraday_overnight_rangebreaks(s)
    assert len(breaks) == 1
    assert breaks[0]["pattern"] == "hour"
    assert breaks[0]["bounds"] == [21, 14]


def test_intraday_overnight_fx_ticker_returns_empty() -> None:
    """FX tickers (ending '=X') trade 24 h — no overnight break applied."""
    bars = [_intraday_bar(f"2024-01-02T{h:02d}:00") for h in range(0, 24)]
    s = _intraday_series(*bars, ticker="EURUSD=X")
    assert _intraday_overnight_rangebreaks(s) == []


def test_intraday_overnight_fallback_on_single_bar() -> None:
    """Single bar → fall back to default [22, 13]."""
    s = _intraday_series(_intraday_bar("2024-01-02T14:30"))
    breaks = _intraday_overnight_rangebreaks(s)
    assert breaks == [{"bounds": [22, 13], "pattern": "hour"}]


# --- render_candlestick wiring ---

def test_render_candlestick_daily_has_holiday_rangebreaks() -> None:
    """Daily series: rangebreaks include at least the weekend entry."""
    daily = _series(
        _bar("2024-01-02"), _bar("2024-01-03"), _bar("2024-01-04"),
        _bar("2024-01-05"), _bar("2024-01-08"),  # skip Jan 6-7 (weekend) and Jan 9 missing
        period=ChartPeriod.ONE_MONTH,
    )
    with patch("app.ui.components.charts.st") as mock_st:
        render_candlestick(daily)
    fig = mock_st.plotly_chart.call_args.args[0]
    breaks = list(fig.layout.xaxis.rangebreaks)
    assert len(breaks) >= 1
    weekend_break = next((b for b in breaks if b.bounds == ("sat", "mon")), None)
    assert weekend_break is not None


def test_render_candlestick_daily_includes_missing_holiday_in_rangebreaks() -> None:
    """Daily series with a missing weekday includes that date in rangebreaks values."""
    daily = _series(
        _bar("2024-01-02"), _bar("2024-01-04"),  # Jan 3 missing
        period=ChartPeriod.ONE_MONTH,
    )
    with patch("app.ui.components.charts.st") as mock_st:
        render_candlestick(daily)
    fig = mock_st.plotly_chart.call_args.args[0]
    breaks = list(fig.layout.xaxis.rangebreaks)
    all_values: list[str] = []
    for b in breaks:
        if b.values:
            all_values.extend(b.values)
    assert "2024-01-03" in all_values


def test_render_candlestick_intraday_has_overnight_rangebreak() -> None:
    """1D chart: rangebreaks use 'hour' pattern, not 'sat'/'mon' bounds."""
    bars = tuple(_intraday_bar(f"2024-01-02T{h:02d}:30") for h in range(14, 21))
    intraday = OhlcSeries(
        ticker="AAPL", currency=Currency.USD, period=ChartPeriod.ONE_DAY,
        bars=bars, fetched_at=_utc("2024-07-01"),
    )
    with patch("app.ui.components.charts.st") as mock_st:
        render_candlestick(intraday)
    fig = mock_st.plotly_chart.call_args.args[0]
    breaks = list(fig.layout.xaxis.rangebreaks)
    assert any(b.pattern == "hour" for b in breaks)


def test_render_candlestick_fx_intraday_has_no_rangebreaks() -> None:
    """FX 1D ticker: no rangebreaks applied (24 h trading)."""
    bars = tuple(_intraday_bar(f"2024-01-02T{h:02d}:00") for h in range(0, 24))
    fx = OhlcSeries(
        ticker="EURUSD=X", currency=Currency.USD, period=ChartPeriod.ONE_DAY,
        bars=bars, fetched_at=_utc("2024-07-01"),
    )
    with patch("app.ui.components.charts.st") as mock_st:
        render_candlestick(fx)
    fig = mock_st.plotly_chart.call_args.args[0]
    assert not fig.layout.xaxis.rangebreaks


def test_render_candlestick_weekly_has_no_rangebreaks() -> None:
    """Weekly-aggregated series (1Y): no rangebreaks at all."""
    weekly = _series(
        _bar("2024-01-02"), _bar("2024-01-09"), _bar("2024-01-16"),
        period=ChartPeriod.ONE_YEAR,
    )
    with patch("app.ui.components.charts.st") as mock_st:
        render_candlestick(weekly)
    fig = mock_st.plotly_chart.call_args.args[0]
    assert not fig.layout.xaxis.rangebreaks
