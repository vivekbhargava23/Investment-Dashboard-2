import plotly.graph_objects as go

from app.ui.components.chart_theme import (
    CHART_STYLE_PRESETS,
    STYLE_CLEAN,
    apply_style,
    get_accent_color,
    styled_bar_trace,
    styled_line_trace,
)


def test_apply_style_sets_layout_properties_for_each_preset() -> None:
    for style in CHART_STYLE_PRESETS:
        fig = apply_style(go.Figure(), style)

        assert fig.layout.paper_bgcolor == style.bg_color
        assert fig.layout.plot_bgcolor == style.bg_color
        assert fig.layout.font.family == style.font_family
        assert fig.layout.font.size == style.font_size
        assert fig.layout.font.color == style.text_color
        assert fig.layout.xaxis.gridcolor == style.grid_color
        assert fig.layout.xaxis.showgrid == style.show_gridx
        assert fig.layout.yaxis.gridcolor == style.grid_color
        assert fig.layout.yaxis.showgrid == style.show_gridy


def test_get_accent_color_wraps() -> None:
    assert get_accent_color(STYLE_CLEAN, 0) == STYLE_CLEAN.accent_colors[0]
    assert get_accent_color(STYLE_CLEAN, len(STYLE_CLEAN.accent_colors)) == (
        STYLE_CLEAN.accent_colors[0]
    )
    assert get_accent_color(STYLE_CLEAN, len(STYLE_CLEAN.accent_colors) + 1) == (
        STYLE_CLEAN.accent_colors[1]
    )


def test_styled_bar_trace_sets_color_and_opacity() -> None:
    trace = styled_bar_trace(STYLE_CLEAN, 2, x=["Q1"], y=[100])

    assert isinstance(trace, go.Bar)
    assert trace.marker.color == STYLE_CLEAN.accent_colors[2]
    assert trace.opacity == STYLE_CLEAN.bar_opacity


def test_styled_line_trace_sets_color_and_width() -> None:
    trace = styled_line_trace(STYLE_CLEAN, 3, x=["Q1"], y=[20])

    assert isinstance(trace, go.Scatter)
    assert trace.line.color == STYLE_CLEAN.accent_colors[3]
    assert trace.line.width == STYLE_CLEAN.line_width

