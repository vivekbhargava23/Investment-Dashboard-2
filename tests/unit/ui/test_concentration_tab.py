from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.domain.analytics_views import ConcentrationView
from app.domain.money import Currency
from app.services.analytics_concentration import compute_concentration_view
from app.ui.pages.analytics import concentration
from tests.fixtures.concentration_fixtures import make_live_position, make_summary


def _columns(n: int) -> list[MagicMock]:
    cols = []
    for _ in range(n):
        col = MagicMock()
        col.__enter__ = MagicMock(return_value=col)
        col.__exit__ = MagicMock(return_value=False)
        cols.append(col)
    return cols


def test_concentration_tab_empty_state_skips_charts() -> None:
    view = ConcentrationView(
        top_1_pct=Decimal("0"),
        top_3_pct=Decimal("0"),
        herfindahl=Decimal("0"),
        weights_by_ticker=[],
        currency_split=[],
        rows=[],
    )

    with (
        patch("app.ui.pages.analytics.concentration.st") as mock_st,
        patch("app.ui.pages.analytics.concentration.render_weight_bar_chart") as mock_bar_chart,
        patch("app.ui.pages.analytics.concentration.render_currency_donut") as mock_donut,
    ):
        concentration._render_concentration_view(view)

    mock_st.info.assert_called_once_with("No positions yet — add transactions in Manage Portfolio.")
    mock_bar_chart.assert_not_called()
    mock_donut.assert_not_called()


def test_concentration_tab_smoke_renders_kpis_charts_and_table() -> None:
    positions = [
        make_live_position("A", "600", Currency.USD),
        make_live_position("B", "400", Currency.EUR),
    ]
    view = compute_concentration_view(positions, make_summary(positions))

    with (
        patch("app.ui.pages.analytics.concentration.st") as mock_st,
        patch("app.ui.pages.analytics.concentration.render_metric_card") as mock_card,
        patch("app.ui.pages.analytics.concentration.render_explainable_metric") as mock_explain,
        patch("app.ui.pages.analytics.concentration.render_weight_bar_chart") as mock_bar_chart,
        patch("app.ui.pages.analytics.concentration.render_currency_donut") as mock_donut,
        patch("app.ui.pages.analytics.concentration.render_html") as mock_html,
    ):
        mock_st.columns.side_effect = [_columns(3), _columns(2)]
        concentration._render_concentration_view(view)

    # Top-1 and Top-3 use the KPI tile; Herfindahl now uses the explain component.
    assert mock_card.call_count == 2
    mock_explain.assert_called_once()
    mock_bar_chart.assert_called_once()
    mock_donut.assert_called_once()
    mock_html.assert_called_once()
    assert "positions-table" in mock_html.call_args.args[0]


def test_concentration_tab_stale_banner_renders_count() -> None:
    positions = [
        make_live_position("A", "600", Currency.USD),
        make_live_position("STALE", "400", Currency.EUR, stale=True),
    ]
    view = compute_concentration_view(positions, make_summary(positions))

    with (
        patch("app.ui.pages.analytics.concentration.st") as mock_st,
        patch("app.ui.pages.analytics.concentration.render_metric_card"),
        patch("app.ui.pages.analytics.concentration.render_explainable_metric"),
        patch("app.ui.pages.analytics.concentration.render_weight_bar_chart"),
        patch("app.ui.pages.analytics.concentration.render_currency_donut"),
        patch("app.ui.pages.analytics.concentration.render_html"),
    ):
        mock_st.columns.side_effect = [_columns(3), _columns(2)]
        concentration._render_concentration_view(view)

    mock_st.warning.assert_called_once()
    assert "1 positions" in mock_st.warning.call_args.args[0]
