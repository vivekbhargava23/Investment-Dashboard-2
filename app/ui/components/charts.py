"""Plotly chart render functions. Each function takes a pre-fetched OhlcSeries,
renders a Plotly figure via st.plotly_chart, and returns None.
No fetching, no caching — the caller is responsible for those."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

import plotly.graph_objects as go
import streamlit as st

from app.domain.market_data import ChartPeriod, OhlcSeries
from app.domain.money import Currency
from app.ui.components._chart_styles import (
    CANDLE_DOWN,
    CANDLE_UP,
    CORRELATION_BUCKET_COLORS,
    CORRELATION_COLORSCALE,
    LINE_COLOR_DEFAULT,
    THEME_GREY,
    base_layout,
)


@dataclass(frozen=True)
class ChartPoint:
    timestamp: datetime
    value: Decimal


@dataclass(frozen=True)
class ChartSeries:
    ticker: str
    currency: Currency
    period: ChartPeriod
    points: tuple[ChartPoint, ...]


LineChartSeries = OhlcSeries | ChartSeries
YAxisMode = Literal["currency", "plain"]


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _weekend_rangebreaks() -> list[dict[str, Any]]:
    """Exclude Saturday–Sunday gaps from the x-axis for daily-bar charts."""
    return [{"bounds": ["sat", "mon"]}]


def _needs_weekend_rangebreaks(series: OhlcSeries) -> bool:
    """Return True only when bars are approximately daily-spaced.

    Weekly/monthly aggregated bars span weekends inside each bar — applying
    rangebreaks would visually compress the axis incorrectly.
    Intraday bars (sub-hourly) don't need weekend exclusion either.

    Daily bars have avg spacing ~24–40 h (Mon→Tue=24h; Fri→Mon=72h averages out
    to ~33h over a month). We use the window 8h–100h to safely identify daily.
    """
    if len(series.bars) < 2:
        return False
    total_s = (series.bars[-1].timestamp - series.bars[0].timestamp).total_seconds()
    avg_h = total_s / (len(series.bars) - 1) / 3600
    return 8.0 <= avg_h < 100.0


def _chart_timestamps(series: LineChartSeries) -> list[datetime]:
    if isinstance(series, OhlcSeries):
        return [bar.timestamp for bar in series.bars]
    return [point.timestamp for point in series.points]


def _chart_values(series: LineChartSeries) -> list[float]:
    if isinstance(series, OhlcSeries):
        return [float(bar.close) for bar in series.bars]
    return [float(point.value) for point in series.points]


def _chart_len(series: LineChartSeries) -> int:
    if isinstance(series, OhlcSeries):
        return len(series.bars)
    return len(series.points)


def _needs_line_rangebreaks(series: LineChartSeries) -> bool:
    if isinstance(series, OhlcSeries):
        return _needs_weekend_rangebreaks(series)
    if len(series.points) < 2:
        return False
    total_s = (series.points[-1].timestamp - series.points[0].timestamp).total_seconds()
    avg_h = total_s / (len(series.points) - 1) / 3600
    return 8.0 <= avg_h < 100.0


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
    if _needs_weekend_rangebreaks(series):
        layout["xaxis"]["rangebreaks"] = _weekend_rangebreaks()
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)


def render_line_chart(
    series: LineChartSeries,
    *,
    secondary_series: LineChartSeries | None = None,
    height: int = 200,
    color: str | None = None,
    secondary_color: str = THEME_GREY,
    y_axis_mode: YAxisMode = "currency",
    y_axis_title: str | None = None,
    primary_name: str | None = None,
    secondary_name: str | None = None,
    show_legend: bool | None = None,
    chart_title: str | None = None,
    fill_to_zero: bool = True,
) -> None:
    line_color = color or LINE_COLOR_DEFAULT
    timestamps = _chart_timestamps(series)
    closes = _chart_values(series)
    if secondary_series is not None and _chart_len(series) != _chart_len(secondary_series):
        raise ValueError("primary and secondary series must have equal length")

    # Dynamic y-range: price movements visible regardless of absolute price level.
    # fill="tozeroy" on a $800 stock collapses the visible change to a sliver.
    secondary_closes = (
        _chart_values(secondary_series)
        if secondary_series is not None
        else []
    )
    y_min, y_max = _dynamic_y_range(closes + secondary_closes)

    fig = go.Figure(
        data=[
            go.Scatter(
                x=timestamps,
                y=closes,
                name=primary_name or series.ticker,
                mode="lines",
                line={"color": line_color, "width": 2},
                fill="tozeroy" if fill_to_zero else None,
                fillcolor=_hex_to_rgba(line_color, 0.1) if fill_to_zero else None,
                connectgaps=True,
            )
        ]
    )
    if secondary_series is not None:
        fig.add_trace(
            go.Scatter(
                x=_chart_timestamps(secondary_series),
                y=secondary_closes,
                name=secondary_name or secondary_series.ticker,
                mode="lines",
                line={"color": secondary_color, "width": 2},
                connectgaps=True,
            )
        )
    layout = base_layout(height=height, show_axes=True)
    layout["yaxis"]["range"] = [y_min, y_max]
    if y_axis_mode == "currency":
        layout["yaxis"]["tickprefix"] = f"{series.currency.value} "
    else:
        layout["yaxis"]["tickprefix"] = ""
    if y_axis_title is not None:
        layout["yaxis"]["title"] = {"text": y_axis_title}
    if chart_title is not None:
        layout["title"] = {"text": chart_title, "x": 0, "font": {"size": 13}}
        layout["margin"]["t"] = 32
    legend_visible = secondary_series is not None if show_legend is None else show_legend
    layout["showlegend"] = legend_visible
    if legend_visible:
        layout["legend"] = {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        }
    if _needs_line_rangebreaks(series):
        layout["xaxis"]["rangebreaks"] = _weekend_rangebreaks()
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)


def render_drawdown_chart(
    series: LineChartSeries,
    *,
    height: int = 180,
    chart_title: str | None = "Drawdown",
) -> None:
    timestamps = _chart_timestamps(series)
    values = _chart_values(series)
    y_min, y_max = _dynamic_y_range(values + [0.0])

    fig = go.Figure(
        data=[
            go.Scatter(
                x=timestamps,
                y=values,
                mode="lines",
                line={"color": CANDLE_DOWN, "width": 1.5},
                fill="tozeroy",
                fillcolor=_hex_to_rgba(CANDLE_DOWN, 0.22),
                connectgaps=True,
                name=series.ticker,
            )
        ]
    )
    layout = base_layout(height=height, show_axes=True)
    layout["yaxis"]["range"] = [y_min, min(y_max, 0.01)]
    layout["yaxis"]["tickformat"] = ".1%"
    if chart_title is not None:
        layout["title"] = {"text": chart_title, "x": 0, "font": {"size": 13}}
        layout["margin"]["t"] = 32
    layout["shapes"] = [
        {
            "type": "line",
            "xref": "paper",
            "x0": 0,
            "x1": 1,
            "yref": "y",
            "y0": 0,
            "y1": 0,
            "line": {"color": THEME_GREY, "width": 1, "dash": "dash"},
        }
    ]
    if _needs_line_rangebreaks(series):
        layout["xaxis"]["rangebreaks"] = _weekend_rangebreaks()
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)


def render_correlation_heatmap(
    matrix: dict[str, dict[str, Decimal]],
    *,
    height: int = 500,
) -> None:
    tickers = sorted(matrix)
    z_values: list[list[float]] = []
    labels: list[list[str]] = []
    for row_ticker in tickers:
        z_row: list[float] = []
        label_row: list[str] = []
        for col_ticker in tickers:
            value = matrix[row_ticker][col_ticker]
            if row_ticker == col_ticker:
                z_row.append(0.5)
                label_row.append("—")
            else:
                z_row.append(float(value))
                label_row.append(f"{value:.2f}")
        z_values.append(z_row)
        labels.append(label_row)

    bucket_colors = [
        _correlation_bucket_color(_avg_off_diagonal(matrix, ticker))
        for ticker in tickers
    ]

    fig = go.Figure(
        data=[
            go.Heatmap(
                z=z_values,
                x=tickers,
                y=tickers,
                zmin=-1,
                zmax=1,
                colorscale=CORRELATION_COLORSCALE,
                text=labels,
                texttemplate="%{text}",
                hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>",
                colorbar={"title": "Corr"},
            )
        ]
    )
    layout = base_layout(height=height, show_axes=True)
    layout["margin"] = {"l": 58, "r": 10, "t": 68, "b": 20}
    layout["hovermode"] = "closest"
    layout["xaxis"]["side"] = "top"
    layout["xaxis"]["tickangle"] = -45
    layout["xaxis"]["tickfont"] = {"size": 11, "color": "#E5E7EB"}
    layout["xaxis"]["showline"] = True
    layout["xaxis"]["linecolor"] = "rgba(229,231,235,0.35)"
    layout["yaxis"]["autorange"] = "reversed"
    layout["yaxis"]["tickfont"] = {"size": 11, "color": "#E5E7EB"}
    layout["yaxis"]["showline"] = True
    layout["yaxis"]["linecolor"] = "rgba(229,231,235,0.35)"
    layout["shapes"] = _correlation_bucket_strip_shapes(tickers, bucket_colors)
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)


def _avg_off_diagonal(
    matrix: dict[str, dict[str, Decimal]],
    ticker: str,
) -> Decimal | None:
    peers = [value for peer, value in matrix[ticker].items() if peer != ticker]
    if not peers:
        return None
    return sum(peers, Decimal("0")) / Decimal(len(peers))


def _correlation_bucket_color(avg_corr: Decimal | None) -> str:
    if avg_corr is None:
        return CORRELATION_BUCKET_COLORS["neutral"]
    if avg_corr < Decimal("0.2"):
        return CORRELATION_BUCKET_COLORS["high"]
    if avg_corr < Decimal("0.4"):
        return CORRELATION_BUCKET_COLORS["moderate"]
    if avg_corr < Decimal("0.6"):
        return CORRELATION_BUCKET_COLORS["low"]
    return CORRELATION_BUCKET_COLORS["very low"]


def _correlation_bucket_strip_shapes(
    tickers: list[str],
    bucket_colors: list[str],
) -> list[dict[str, Any]]:
    shapes: list[dict[str, Any]] = []
    for ticker, color in zip(tickers, bucket_colors):
        shapes.append(
            {
                "type": "line",
                "xref": "paper",
                "x0": -0.018,
                "x1": -0.018,
                "yref": "y",
                "y0": ticker,
                "y1": ticker,
                "line": {"color": color, "width": 7},
            }
        )
        shapes.append(
            {
                "type": "line",
                "xref": "x",
                "x0": ticker,
                "x1": ticker,
                "yref": "paper",
                "y0": 1.018,
                "y1": 1.018,
                "line": {"color": color, "width": 7},
            }
        )
    return shapes


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


def render_weight_bar_chart(
    weights: list[tuple[str, Decimal]],
    *,
    max_position_pct: Decimal,
    height: int = 320,
) -> go.Figure:
    """Render current position weights as a horizontal bar chart."""
    tickers = [ticker for ticker, _ in weights]
    values = [float(weight) for _, weight in weights]
    colors = [
        CANDLE_DOWN if weight >= max_position_pct else LINE_COLOR_DEFAULT
        for _, weight in weights
    ]

    fig = go.Figure(
        data=[
            go.Bar(
                x=values,
                y=tickers,
                orientation="h",
                marker={"color": colors},
                text=[f"{value:.1f}%" for value in values],
                textposition="auto",
                hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
            )
        ]
    )
    layout = base_layout(height=height, show_axes=True)
    layout["xaxis"]["title"] = {"text": "Portfolio weight"}
    layout["xaxis"]["ticksuffix"] = "%"
    layout["yaxis"]["autorange"] = "reversed"
    layout["shapes"] = [
        {
            "type": "line",
            "xref": "x",
            "x0": float(max_position_pct),
            "x1": float(max_position_pct),
            "yref": "paper",
            "y0": 0,
            "y1": 1,
            "line": {"color": CANDLE_DOWN, "width": 1, "dash": "dash"},
        }
    ]
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)
    return fig


def render_currency_donut(
    split: list[tuple[Currency, Decimal]],
    *,
    height: int = 320,
) -> go.Figure:
    """Render native-currency exposure by EUR market value."""
    labels = [currency.value for currency, _ in split]
    values = [float(value) for _, value in split]
    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.58,
                marker={"colors": [LINE_COLOR_DEFAULT, THEME_GREY, CANDLE_DOWN]},
                textinfo="label+percent",
                hovertemplate="%{label}: €%{value:,.0f}<extra></extra>",
            )
        ]
    )
    layout = base_layout(height=height, show_axes=False)
    layout["showlegend"] = bool(split)
    if not split:
        layout["annotations"] = [
            {
                "text": "No currency data",
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"color": THEME_GREY, "size": 12},
            }
        ]
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)
    return fig
