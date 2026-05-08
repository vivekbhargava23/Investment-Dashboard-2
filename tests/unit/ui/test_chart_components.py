"""Smoke tests for chart render functions. Verify figure shape via mocked st.plotly_chart."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import plotly.graph_objects as go

from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries
from app.domain.money import Currency
from app.ui.components._chart_styles import CANDLE_UP
from app.ui.components.charts import (
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
