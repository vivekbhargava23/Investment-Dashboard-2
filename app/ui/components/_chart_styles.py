"""Plotly layout constants and factory for the dashboard's dark chart theme."""

from typing import Any

CHART_BG = "rgba(0,0,0,0)"
GRID_COLOR = "rgba(255,255,255,0.05)"
AXIS_COLOR = "rgba(255,255,255,0.4)"
CANDLE_UP = "#26a69a"
CANDLE_DOWN = "#ef5350"
LINE_COLOR_DEFAULT = "#26a69a"


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
