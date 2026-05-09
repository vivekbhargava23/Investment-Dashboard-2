from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from app.ui.components._chart_styles import CORRELATION_BUCKET_COLORS
from app.ui.components.charts import render_correlation_heatmap


def test_render_correlation_heatmap_uses_labels_hover_and_neutral_diagonal() -> None:
    matrix = {
        "A": {"A": Decimal("1"), "B": Decimal("0.42")},
        "B": {"A": Decimal("0.42"), "B": Decimal("1")},
    }

    with patch("app.ui.components.charts.st") as mock_st:
        render_correlation_heatmap(matrix)

    fig = mock_st.plotly_chart.call_args.args[0]
    trace = fig.data[0]
    assert list(trace.x) == ["A", "B"]
    assert list(trace.y) == ["A", "B"]
    assert trace.text[0][0] == "—"
    assert trace.text[0][1] == "0.42"
    assert trace.z[0][0] == 0.0
    assert trace.z[1][1] == 0.0
    assert trace.z[0][1] == 0.42
    assert trace.hovertemplate == "%{y} vs %{x}: %{z:.2f}<extra></extra>"
    assert trace.zmin == -1
    assert trace.zmax == 1


def test_render_correlation_heatmap_uses_selected_palette_title() -> None:
    colorscale = [
        [0.0, "#111111"],
        [0.5, "#FFFFFF"],
        [1.0, "#999999"],
    ]
    with patch("app.ui.components.charts.st") as mock_st:
        render_correlation_heatmap(
            {"A": {"A": Decimal("1")}},
            colorscale=colorscale,
            title="Selected",
        )

    fig = mock_st.plotly_chart.call_args.args[0]
    assert fig.layout.title.text == "Selected"
    assert fig.data[0].colorscale == tuple(
        (anchor, color) for anchor, color in colorscale
    )


def test_render_correlation_heatmap_respects_height() -> None:
    with patch("app.ui.components.charts.st") as mock_st:
        render_correlation_heatmap(
            {"A": {"A": Decimal("1")}},
            height=360,
        )

    fig = mock_st.plotly_chart.call_args.args[0]
    assert fig.layout.height == 360


def test_render_correlation_heatmap_adds_bucket_side_indicators() -> None:
    matrix = {
        "HIGH": {
            "HIGH": Decimal("1"),
            "MOD": Decimal("0.10"),
            "LOW": Decimal("0.10"),
            "RISK": Decimal("0.10"),
        },
        "MOD": {
            "HIGH": Decimal("0.10"),
            "MOD": Decimal("1"),
            "LOW": Decimal("0.20"),
            "RISK": Decimal("0.85"),
        },
        "LOW": {
            "HIGH": Decimal("0.10"),
            "MOD": Decimal("0.20"),
            "LOW": Decimal("1"),
            "RISK": Decimal("0.90"),
        },
        "RISK": {
            "HIGH": Decimal("0.10"),
            "MOD": Decimal("0.85"),
            "LOW": Decimal("0.90"),
            "RISK": Decimal("1"),
        },
    }

    with patch("app.ui.components.charts.st") as mock_st:
        render_correlation_heatmap(matrix)

    fig = mock_st.plotly_chart.call_args.args[0]
    colors = [shape.line.color for shape in fig.layout.shapes]
    assert CORRELATION_BUCKET_COLORS["high"] in colors
    assert CORRELATION_BUCKET_COLORS["moderate"] in colors
    assert CORRELATION_BUCKET_COLORS["low"] in colors
    assert CORRELATION_BUCKET_COLORS["very low"] in colors
    assert len(fig.layout.shapes) == 8


def test_render_correlation_heatmap_single_ticker_uses_neutral_indicator() -> None:
    with patch("app.ui.components.charts.st") as mock_st:
        render_correlation_heatmap({"A": {"A": Decimal("1")}})

    fig = mock_st.plotly_chart.call_args.args[0]
    colors = [shape.line.color for shape in fig.layout.shapes]
    assert colors == [
        CORRELATION_BUCKET_COLORS["neutral"],
        CORRELATION_BUCKET_COLORS["neutral"],
    ]
