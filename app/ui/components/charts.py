"""Plotly chart render functions. Each function takes a pre-fetched OhlcSeries,
renders a Plotly figure via st.plotly_chart, and returns None.
No fetching, no caching — the caller is responsible for those."""

from decimal import Decimal
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from app.domain.market_data import OhlcSeries
from app.ui.components._chart_styles import (
    CANDLE_DOWN,
    CANDLE_UP,
    LINE_COLOR_DEFAULT,
    base_layout,
)


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _weekend_rangebreaks() -> list[dict[str, Any]]:
    """Exclude Saturday–Sunday gaps from the x-axis for daily-bar charts."""
    return [{"bounds": ["sat", "mon"]}]


def _dynamic_y_range(values: list[float], padding_pct: float = 0.05) -> list[float]:
    """Return [y_min, y_max] with *padding_pct* margin above and below the data range."""
    lo, hi = min(values), max(values)
    margin = (hi - lo) * padding_pct if hi != lo else hi * padding_pct
    return [lo - margin, hi + margin]


def render_candlestick(series: OhlcSeries, *, height: int = 400) -> None:
    timestamps = [bar.timestamp for bar in series.bars]
    opens = [float(bar.open) for bar in series.bars]
    highs = [float(bar.high) for bar in series.bars]
    lows = [float(bar.low) for bar in series.bars]
    closes = [float(bar.close) for bar in series.bars]

    fig = go.Figure(
        data=[
            go.Candlestick(
                x=timestamps,
                open=opens,
                high=highs,
                low=lows,
                close=closes,
                increasing_line_color=CANDLE_UP,
                decreasing_line_color=CANDLE_DOWN,
            )
        ]
    )
    layout = base_layout(height=height, show_axes=True)
    layout["xaxis"]["rangeslider"] = {"visible": False}
    layout["xaxis"]["tickformat"] = "%H:%M" if series.period.is_intraday else "%b %Y"
    layout["yaxis"]["tickprefix"] = f"{series.currency.value} "
    # Hide weekend gaps for daily bars; intraday data only has market-hours bars already
    if not series.period.is_intraday:
        layout["xaxis"]["rangebreaks"] = _weekend_rangebreaks()
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)


def render_line_chart(
    series: OhlcSeries, *, height: int = 200, color: str | None = None
) -> None:
    line_color = color or LINE_COLOR_DEFAULT
    timestamps = [bar.timestamp for bar in series.bars]
    closes = [float(bar.close) for bar in series.bars]

    # Use a dynamic y-range so movements are visible regardless of absolute price level.
    # fill="tozeroy" on a $800 stock would collapse the visible change to a thin sliver.
    y_min, y_max = _dynamic_y_range(closes)

    fig = go.Figure(
        data=[
            go.Scatter(
                x=timestamps,
                y=closes,
                mode="lines",
                line={"color": line_color, "width": 2},
                fill="tozeroy",
                fillcolor=_hex_to_rgba(line_color, 0.1),
            )
        ]
    )
    layout = base_layout(height=height, show_axes=True)
    layout["yaxis"]["range"] = [y_min, y_max]
    layout["yaxis"]["tickprefix"] = f"{series.currency.value} "
    if not series.period.is_intraday:
        layout["xaxis"]["rangebreaks"] = _weekend_rangebreaks()
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)


def render_sparkline(series: OhlcSeries, *, height: int = 40, width: int = 120) -> None:
    pct = series.period_change_pct
    line_color = CANDLE_UP if (pct is None or pct >= Decimal("0")) else CANDLE_DOWN
    timestamps = [bar.timestamp for bar in series.bars]
    closes = [float(bar.close) for bar in series.bars]

    fig = go.Figure(
        data=[
            go.Scatter(
                x=timestamps,
                y=closes,
                mode="lines",
                line={"color": line_color, "width": 1.5},
            )
        ]
    )
    layout = base_layout(height=height, show_axes=False)
    layout["width"] = width
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=False, config={"displayModeBar": False})
