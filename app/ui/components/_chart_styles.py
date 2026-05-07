CHART_BG = "rgba(0,0,0,0)"
GRID_COLOR = "rgba(255,255,255,0.05)"
AXIS_COLOR = "rgba(255,255,255,0.4)"
CANDLE_UP = "#26a69a"
CANDLE_DOWN = "#ef5350"
LINE_COLOR_DEFAULT = "#26a69a"


def base_layout(*, height: int, show_axes: bool = True) -> dict[str, object]:
    margin = {"l": 20, "r": 10, "t": 10, "b": 20} if show_axes else {"l": 0, "r": 0, "t": 0, "b": 0}
    axis = {
        "showgrid": show_axes,
        "gridcolor": GRID_COLOR,
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
        "xaxis": axis,
        "yaxis": axis,
        "hovermode": "x unified" if show_axes else False,
    }
