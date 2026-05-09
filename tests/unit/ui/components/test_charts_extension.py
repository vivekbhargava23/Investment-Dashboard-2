from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.domain.market_data import ChartPeriod
from app.domain.money import Currency
from app.ui.components._chart_styles import CANDLE_DOWN, THEME_GREY
from app.ui.components.charts import (
    ChartPoint,
    ChartSeries,
    render_drawdown_chart,
    render_line_chart,
)


def _series(values: list[str], *, ticker: str = "TST") -> ChartSeries:
    start = datetime(2025, 1, 1, 16, tzinfo=UTC)
    return ChartSeries(
        ticker=ticker,
        currency=Currency.EUR,
        period=ChartPeriod.ONE_MONTH,
        points=tuple(
            ChartPoint(timestamp=start + timedelta(days=i), value=Decimal(value))
            for i, value in enumerate(values)
        ),
    )


def test_render_line_chart_without_secondary_has_one_trace() -> None:
    with patch("app.ui.components.charts.st") as mock_st:
        render_line_chart(_series(["100", "101", "102"]))

    fig = mock_st.plotly_chart.call_args.args[0]
    assert len(fig.data) == 1


def test_render_line_chart_with_secondary_has_two_traces() -> None:
    with patch("app.ui.components.charts.st") as mock_st:
        render_line_chart(
            _series(["100", "101", "102"]),
            secondary_series=_series(["100", "100.5", "101"], ticker="SPY"),
            primary_name="Portfolio",
            secondary_name="SPY",
        )

    fig = mock_st.plotly_chart.call_args.args[0]
    assert len(fig.data) == 2
    assert fig.data[0].name == "Portfolio"
    assert fig.data[1].name == "SPY"
    assert fig.data[1].line.color == THEME_GREY
    assert fig.layout.showlegend is True


def test_render_line_chart_can_disable_currency_axis_for_indexed_values() -> None:
    with patch("app.ui.components.charts.st") as mock_st:
        render_line_chart(
            _series(["100", "101", "102"]),
            y_axis_mode="plain",
            y_axis_title="Index, start = 100",
            fill_to_zero=False,
        )

    fig = mock_st.plotly_chart.call_args.args[0]
    assert fig.layout.yaxis.tickprefix == ""
    assert fig.layout.yaxis.title.text == "Index, start = 100"
    assert fig.data[0].fill is None


def test_render_line_chart_secondary_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="primary and secondary series must have equal length"):
        render_line_chart(
            _series(["100", "101", "102"]),
            secondary_series=_series(["100", "101"]),
        )


def test_render_drawdown_chart_uses_red_area_fill() -> None:
    with patch("app.ui.components.charts.st") as mock_st:
        render_drawdown_chart(_series(["0", "-0.1", "0"]))

    fig = mock_st.plotly_chart.call_args.args[0]
    assert fig.data[0].fill == "tozeroy"
    assert fig.data[0].line.color == CANDLE_DOWN


def test_render_drawdown_chart_has_dashed_zero_line() -> None:
    with patch("app.ui.components.charts.st") as mock_st:
        render_drawdown_chart(_series(["0", "-0.1", "0"]))

    fig = mock_st.plotly_chart.call_args.args[0]
    assert fig.layout.shapes[0].y0 == 0
    assert fig.layout.shapes[0].line.dash == "dash"


def test_render_drawdown_chart_uses_percentage_axis_and_title() -> None:
    with patch("app.ui.components.charts.st") as mock_st:
        render_drawdown_chart(_series(["0", "-0.1", "0"]))

    fig = mock_st.plotly_chart.call_args.args[0]
    assert fig.layout.yaxis.tickformat == ".1%"
    assert fig.layout.title.text == "Drawdown"
