"""Plotly layout constants and factory for the dashboard's dark chart theme."""

from typing import Any

CHART_BG = "rgba(0,0,0,0)"
GRID_COLOR = "rgba(255,255,255,0.05)"
AXIS_COLOR = "rgba(255,255,255,0.4)"
CANDLE_UP = "#26a69a"
CANDLE_DOWN = "#ef5350"
THEME_GREY = "#8a93a3"
LINE_COLOR_DEFAULT = "#26a69a"
# Plotly normalises colorscale anchors across zmin=-1 and zmax=1, so
# correlation 0.5 sits at 0.75 on the scale.
CORRELATION_COLORSCALE = [
    [0.0, CANDLE_UP],
    [0.5, CANDLE_UP],
    [0.75, THEME_GREY],
    [1.0, CANDLE_DOWN],
]


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
