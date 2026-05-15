from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
from pydantic import BaseModel, ConfigDict, Field


class ChartStyle(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    bg_color: str
    grid_color: str
    text_color: str
    font_family: str
    font_size: int
    accent_colors: list[str] = Field(min_length=1)
    bar_opacity: float
    line_width: float
    grid_width: float
    show_gridx: bool
    show_gridy: bool
    margin: dict[str, int]
    hover_template_style: str


_APP_FONT_STACK = (
    "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "
    "'Segoe UI', sans-serif"
)

STYLE_CLEAN = ChartStyle(
    name="Clean",
    description="Light, minimal, and direct for dense comparison work.",
    bg_color="#ffffff",
    grid_color="#f0f0f0",
    text_color="#1f2937",
    font_family=_APP_FONT_STACK,
    font_size=12,
    accent_colors=["#4f6f8f", "#4d908e", "#8c8c84", "#b77982", "#87a878", "#c9953a"],
    bar_opacity=0.72,
    line_width=1.5,
    grid_width=1,
    show_gridx=True,
    show_gridy=True,
    margin={"l": 34, "r": 18, "t": 18, "b": 32},
    hover_template_style="<b>%{x}</b><br>%{y}<extra></extra>",
)

STYLE_DARK = ChartStyle(
    name="Dark",
    description="High-contrast fintech styling with brighter accents.",
    bg_color="#1a1a2e",
    grid_color="#2a2a3e",
    text_color="#e0e0e0",
    font_family=_APP_FONT_STACK,
    font_size=12,
    accent_colors=["#38bdf8", "#fb7185", "#5eead4", "#facc15", "#a78bfa", "#fca5a5"],
    bar_opacity=0.78,
    line_width=2,
    grid_width=1,
    show_gridx=True,
    show_gridy=True,
    margin={"l": 34, "r": 18, "t": 18, "b": 32},
    hover_template_style="<b>%{x}</b><br>%{y}<extra></extra>",
)

STYLE_EDITORIAL = ChartStyle(
    name="Editorial",
    description="Print-like chart treatment with muted, durable colors.",
    bg_color="#fafaf8",
    grid_color="#e4e2dc",
    text_color="#222222",
    font_family="Source Sans Pro, Georgia, 'Times New Roman', serif",
    font_size=12,
    accent_colors=["#17324d", "#b45f3c", "#2f5d50", "#3f3f3f", "#7a3145", "#737a3c"],
    bar_opacity=0.68,
    line_width=1.8,
    grid_width=1,
    show_gridx=False,
    show_gridy=True,
    margin={"l": 34, "r": 18, "t": 18, "b": 32},
    hover_template_style="<b>%{x}</b><br>%{y}<extra></extra>",
)

CHART_STYLE_PRESETS = (STYLE_CLEAN, STYLE_DARK, STYLE_EDITORIAL)

DEFAULT_STYLE = STYLE_CLEAN


def apply_style(fig: go.Figure, style: ChartStyle) -> go.Figure:
    fig.update_layout(
        paper_bgcolor=style.bg_color,
        plot_bgcolor=style.bg_color,
        font={"family": style.font_family, "size": style.font_size, "color": style.text_color},
        margin=style.margin,
        hovermode="x unified",
        showlegend=False,
    )
    axis_style: dict[str, Any] = {
        "gridcolor": style.grid_color,
        "gridwidth": style.grid_width,
        "zeroline": False,
        "linecolor": style.grid_color,
        "tickfont": {"color": style.text_color, "size": style.font_size},
    }
    fig.update_xaxes(showgrid=style.show_gridx, **axis_style)
    fig.update_yaxes(showgrid=style.show_gridy, **axis_style)
    return fig


def get_accent_color(style: ChartStyle, index: int) -> str:
    return style.accent_colors[index % len(style.accent_colors)]


def styled_bar_trace(style: ChartStyle, index: int, **kwargs: Any) -> go.Bar:
    return go.Bar(
        marker={"color": get_accent_color(style, index)},
        opacity=style.bar_opacity,
        hovertemplate=style.hover_template_style,
        **kwargs,
    )


def styled_line_trace(style: ChartStyle, index: int, **kwargs: Any) -> go.Scatter:
    return go.Scatter(
        mode="lines+markers",
        line={"color": get_accent_color(style, index), "width": style.line_width},
        hovertemplate=style.hover_template_style,
        **kwargs,
    )
