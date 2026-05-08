"""Smoke tests for chart render functions. Verify figure shape via mocked st.plotly_chart."""

from unittest.mock import patch

import plotly.graph_objects as go

from app.ui.components._chart_styles import CANDLE_UP
from app.ui.components.charts import render_candlestick, render_line_chart, render_sparkline
from tests.fakes.ohlc import FAKE_SERIES_NVDA_6MO


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
