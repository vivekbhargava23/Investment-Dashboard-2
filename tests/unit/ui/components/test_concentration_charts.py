from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from app.domain.money import Currency
from app.ui.components.charts import render_currency_donut, render_weight_bar_chart


def test_render_weight_bar_chart_has_bar_trace_and_reference_line() -> None:
    weights = [("NVDA", Decimal("22")), ("RHM.DE", Decimal("14"))]

    with patch("app.ui.components.charts.st") as mock_st:
        fig = render_weight_bar_chart(weights, max_position_pct=Decimal("35"))

    assert fig is mock_st.plotly_chart.call_args.args[0]
    assert len(fig.data) == 1
    assert list(fig.data[0].y) == ["NVDA", "RHM.DE"]
    assert fig.layout.shapes[0].x0 == 35


def test_render_weight_bar_chart_empty_keeps_reference_line() -> None:
    with patch("app.ui.components.charts.st"):
        fig = render_weight_bar_chart([], max_position_pct=Decimal("35"))

    assert len(fig.data) == 1
    assert len(fig.data[0].y) == 0
    assert fig.layout.shapes[0].x0 == 35


def test_render_currency_donut_has_expected_slices() -> None:
    split = [(Currency.USD, Decimal("3000")), (Currency.EUR, Decimal("2000"))]

    with patch("app.ui.components.charts.st") as mock_st:
        fig = render_currency_donut(split)

    assert fig is mock_st.plotly_chart.call_args.args[0]
    assert len(fig.data) == 1
    assert list(fig.data[0].labels) == ["USD", "EUR"]


def test_render_currency_donut_empty_adds_annotation() -> None:
    with patch("app.ui.components.charts.st"):
        fig = render_currency_donut([])

    assert len(fig.data) == 1
    assert fig.layout.annotations[0].text == "No currency data"
