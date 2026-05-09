"""Plotly layout constants and factory for the dashboard's dark chart theme."""

from typing import Any, TypeAlias

ColorScale: TypeAlias = list[list[float | str]]

CHART_BG = "rgba(0,0,0,0)"
GRID_COLOR = "rgba(255,255,255,0.05)"
AXIS_COLOR = "rgba(255,255,255,0.4)"
CANDLE_UP = "#26a69a"
CANDLE_DOWN = "#ef5350"
THEME_GREY = "#8a93a3"
LINE_COLOR_DEFAULT = "#26a69a"
CORRELATION_COLORSCALE_OPTIONS: tuple[tuple[str, ColorScale], ...] = (
    (
        "Option 1: Diverging Classic",
        [
            [0.0, "#2563EB"],
            [0.25, "#06B6D4"],
            [0.5, "#F8FAFC"],
            [0.75, "#F97316"],
            [1.0, "#DC2626"],
        ],
    ),
    (
        "Option 2: Financial Risk",
        [
            [0.0, "#10B981"],
            [0.25, "#14B8A6"],
            [0.5, "#E5E7EB"],
            [0.75, "#F59E0B"],
            [1.0, "#EF4444"],
        ],
    ),
    (
        "Option 3: High Contrast Scientific",
        [
            [0.0, "#7C3AED"],
            [0.25, "#0EA5E9"],
            [0.5, "#FFFFFF"],
            [0.75, "#FACC15"],
            [1.0, "#E11D48"],
        ],
    ),
    (
        "Option 4: Cool-to-Hot",
        [
            [0.0, "#4F46E5"],
            [0.25, "#22D3EE"],
            [0.5, "#F1F5F9"],
            [0.75, "#FB923C"],
            [1.0, "#DB2777"],
        ],
    ),
)
CORRELATION_COLORSCALE = CORRELATION_COLORSCALE_OPTIONS[0][1]
CORRELATION_BUCKET_COLORS = {
    "high": "#14B8A6",
    "moderate": "#F59E0B",
    "low": "#F97316",
    "very low": "#EF4444",
    "neutral": "#E5E7EB",
}


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
