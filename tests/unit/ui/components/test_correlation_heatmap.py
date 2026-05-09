from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from app.ui.components.charts import render_correlation_heatmap


def test_render_correlation_heatmap_uses_labels_and_hover_template() -> None:
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
    assert trace.hovertemplate == "%{y} vs %{x}: %{z:.2f}<extra></extra>"
    assert trace.zmin == -1
    assert trace.zmax == 1


def test_render_correlation_heatmap_respects_height() -> None:
    with patch("app.ui.components.charts.st") as mock_st:
        render_correlation_heatmap(
            {"A": {"A": Decimal("1")}},
            height=360,
        )

    fig = mock_st.plotly_chart.call_args.args[0]
    assert fig.layout.height == 360
