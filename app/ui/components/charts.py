from decimal import Decimal

import plotly.graph_objects as go
import streamlit as st

from app.domain.market_data import OhlcSeries
from app.ui.components._chart_styles import (
    CANDLE_DOWN,
    CANDLE_UP,
    LINE_COLOR_DEFAULT,
    base_layout,
)

_INTRADAY_RANGEBREAKS: list[dict[str, object]] = [
    {"bounds": ["sat", "mon"]},
    {"bounds": [16, 9.5], "pattern": "hour"},
]


def _low_alpha(hex_color: str) -> str:
    color = hex_color.lstrip("#")
    if len(color) != 6:
        return "rgba(38,166,154,0.12)"
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    return f"rgba({red},{green},{blue},0.12)"


def _rangebreaks_for(series: OhlcSeries) -> list[dict[str, object]] | None:
    if not series.period.is_intraday:
        return None
    return _INTRADAY_RANGEBREAKS


def _apply_x_axis_format(fig: go.Figure, series: OhlcSeries) -> None:
    fig.update_xaxes(
        tickformat="%H:%M" if series.period.is_intraday else "%b %Y",
        rangebreaks=_rangebreaks_for(series),
    )


def render_candlestick(series: OhlcSeries, *, height: int = 400) -> None:
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=[bar.timestamp for bar in series.bars],
                open=[bar.open for bar in series.bars],
                high=[bar.high for bar in series.bars],
                low=[bar.low for bar in series.bars],
                close=[bar.close for bar in series.bars],
                increasing_line_color=CANDLE_UP,
                decreasing_line_color=CANDLE_DOWN,
            )
        ]
    )
    fig.update_layout(**base_layout(height=height, show_axes=True))
    fig.update_layout(xaxis_rangeslider_visible=False)
    _apply_x_axis_format(fig, series)
    fig.update_yaxes(tickprefix=f"{series.currency.value} ")
    st.plotly_chart(fig, use_container_width=True)


def render_line_chart(
    series: OhlcSeries,
    *,
    height: int = 200,
    color: str | None = None,
) -> None:
    line_color = color or LINE_COLOR_DEFAULT
    fig = go.Figure(
        data=[
            go.Scatter(
                x=[bar.timestamp for bar in series.bars],
                y=[bar.close for bar in series.bars],
                mode="lines",
                line={"color": line_color, "width": 2},
                fill="tozeroy",
                fillcolor=_low_alpha(line_color),
            )
        ]
    )
    fig.update_layout(**base_layout(height=height, show_axes=True))
    _apply_x_axis_format(fig, series)
    st.plotly_chart(fig, use_container_width=True)


def render_sparkline(series: OhlcSeries, *, height: int = 40, width: int = 120) -> None:
    change_pct = series.period_change_pct or Decimal("0")
    line_color = CANDLE_UP if change_pct >= 0 else CANDLE_DOWN
    fig = go.Figure(
        data=[
            go.Scatter(
                x=[bar.timestamp for bar in series.bars],
                y=[bar.close for bar in series.bars],
                mode="lines",
                line={"color": line_color, "width": 1.5},
                hoverinfo="skip",
            )
        ]
    )
    fig.update_layout(**base_layout(height=height, show_axes=False))
    fig.update_layout(width=width, margin={"l": 0, "r": 0, "t": 0, "b": 0})
    fig.update_xaxes(rangebreaks=_rangebreaks_for(series))
    st.plotly_chart(fig, use_container_width=False, config={"displayModeBar": False})
