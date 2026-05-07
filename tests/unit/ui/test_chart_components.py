from typing import Any

import plotly.graph_objects as go

from app.domain.market_data import ChartPeriod
from app.ui.components import charts
from tests.fakes.ohlc import make_ohlc_series


def _capture_plotly_calls(monkeypatch) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    calls: list[dict[str, Any]] = []

    def fake_plotly_chart(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(charts.st, "plotly_chart", fake_plotly_chart)
    return calls


def test_render_candlestick_calls_plotly_chart(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = _capture_plotly_calls(monkeypatch)

    charts.render_candlestick(make_ohlc_series())

    fig = calls[0]["args"][0]
    assert isinstance(fig, go.Figure)
    assert fig.data[0].type == "candlestick"
    assert calls[0]["kwargs"]["use_container_width"] is True


def test_render_line_chart_produces_scatter_with_color_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = _capture_plotly_calls(monkeypatch)

    charts.render_line_chart(make_ohlc_series(), color="#abc123")

    fig = calls[0]["args"][0]
    assert fig.data[0].type == "scatter"
    assert fig.data[0].mode == "lines"
    assert fig.data[0].line.color == "#abc123"


def test_render_sparkline_hides_axes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = _capture_plotly_calls(monkeypatch)

    charts.render_sparkline(make_ohlc_series())

    fig = calls[0]["args"][0]
    assert fig.layout.xaxis.visible is False
    assert fig.layout.yaxis.visible is False
    assert calls[0]["kwargs"]["use_container_width"] is False


def test_intraday_candlestick_uses_rangebreaks(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = _capture_plotly_calls(monkeypatch)

    charts.render_candlestick(make_ohlc_series(period=ChartPeriod.FIVE_DAY))

    fig = calls[0]["args"][0]
    assert len(fig.layout.xaxis.rangebreaks) == 2
