"""Plotly layout constants and factory for the dashboard's dark chart theme."""

from decimal import Decimal
from typing import Any, TypeAlias

ColorScale: TypeAlias = list[list[float | str]]

CHART_BG = "rgba(0,0,0,0)"
GRID_COLOR = "rgba(255,255,255,0.05)"
AXIS_COLOR = "rgba(255,255,255,0.4)"
CHART_AXIS_LABEL_COLOR = "#374151"
CANDLE_UP = "#26a69a"
CANDLE_DOWN = "#ef5350"
THEME_GREY = "#8a93a3"
LINE_COLOR_DEFAULT = "#26a69a"

CORRELATION_COLORSCALES: dict[str, ColorScale] = {
    "Diverging (red–white–blue)": [
        [0.0, "#1E40AF"],
        [0.5, "#F1F5F9"],
        [1.0, "#DC2626"],
    ],
    "Financial (red–neutral–green)": [
        [0.0, "#15803D"],
        [0.5, "#E5E7EB"],
        [1.0, "#DC2626"],
    ],
    "Sequential (white–orange–red)": [
        [0.0, "#FFF7ED"],
        [0.5, "#F97316"],
        [1.0, "#991B1B"],
    ],
}
CORRELATION_COLORSCALE: ColorScale = CORRELATION_COLORSCALES["Financial (red–neutral–green)"]

CORRELATION_BUCKET_COLORS = {
    "high": "#14B8A6",
    "moderate": "#F59E0B",
    "low": "#F97316",
    "very low": "#EF4444",
    "neutral": "#E5E7EB",
}


# Diverging return scale shared by the Overview treemap (RD10) and performance
# heatmap (RD11). Both colour cells by window return on this single green↔red scale
# centred at 0 with a symmetric ±RETURN_CLAMP_PCT clamp, so one outlier can't wash
# out the rest and the two views can't drift apart. Built from existing tokens:
# CANDLE_DOWN (loss) → neutral grey → CANDLE_UP (gain).
RETURN_CLAMP_PCT = Decimal("14")
RETURN_COLORSCALE: ColorScale = [
    [0.0, CANDLE_DOWN],
    [0.5, CORRELATION_BUCKET_COLORS["neutral"]],
    [1.0, CANDLE_UP],
]


# SMA overlay styles for the Technicals tab candlestick chart.
# Amber (#F59E0B) matches the existing "moderate" bucket in CORRELATION_BUCKET_COLORS.
# Blue (#3B82F6, Tailwind blue-500) is visible on both light and dark chart backgrounds.
SMA_50_STYLE: dict[str, Any] = {"color": "#F59E0B", "dash": "dash", "width": 1.5}
SMA_200_STYLE: dict[str, Any] = {"color": "#3B82F6", "dash": "dash", "width": 1.5}


def base_layout(*, height: int, show_axes: bool = True) -> dict[str, Any]:
    """Return a Plotly figure layout dict for the dark dashboard theme."""
    margin = {"l": 20, "r": 10, "t": 10, "b": 20} if show_axes else {"l": 0, "r": 0, "t": 0, "b": 0}
    def _axis() -> dict[str, Any]:
        return {
            "showgrid": show_axes,
            "zeroline": False,
            "color": AXIS_COLOR,
            "visible": show_axes,
        }

    return {
        "height": height,
        "paper_bgcolor": CHART_BG,
        "plot_bgcolor": CHART_BG,
        "margin": margin,
        "showlegend": False,
        "hovermode": "x unified" if show_axes else False,
        "xaxis": _axis(),
        "yaxis": _axis(),
    }
