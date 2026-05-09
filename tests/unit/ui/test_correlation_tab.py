from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.services.analytics_correlation import CorrelationView, SkippedTicker
from app.ui.components._chart_styles import CORRELATION_COLORSCALE_OPTIONS
from app.ui.pages import analytics


def _columns(n: int) -> list[MagicMock]:
    cols = []
    for _ in range(n):
        col = MagicMock()
        col.__enter__ = MagicMock(return_value=col)
        col.__exit__ = MagicMock(return_value=False)
        cols.append(col)
    return cols


def _view() -> CorrelationView:
    return CorrelationView(
        matrix={
            "A": {"A": Decimal("1"), "B": Decimal("0.7"), "C": Decimal("0.2")},
            "B": {"A": Decimal("0.7"), "B": Decimal("1"), "C": Decimal("0.65")},
            "C": {"A": Decimal("0.2"), "B": Decimal("0.65"), "C": Decimal("1")},
        },
        included_tickers=["A", "B", "C"],
        skipped=[],
        avg_correlation={
            "A": Decimal("0.45"),
            "B": Decimal("0.675"),
            "C": Decimal("0.425"),
        },
        clusters=[["A", "B", "C"]],
    )


def test_correlation_view_empty_state_skips_grid() -> None:
    view = CorrelationView(
        matrix={"A": {"A": Decimal("1")}},
        included_tickers=["A"],
        skipped=[],
        avg_correlation={},
        clusters=[],
    )
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.render_correlation_heatmap") as mock_heatmap,
    ):
        analytics._render_correlation_view(view)

    mock_st.info.assert_called_once_with(
        "Need at least 2 positions with sufficient history to compute correlations."
    )
    mock_st.columns.assert_not_called()
    mock_heatmap.assert_not_called()


def test_correlation_view_renders_skipped_banner() -> None:
    view = CorrelationView(
        matrix={"A": {"A": Decimal("1")}},
        included_tickers=["A"],
        skipped=[
            SkippedTicker(ticker="SHORT", available_days=12, required_days=60),
        ],
        avg_correlation={},
        clusters=[],
    )
    with patch("app.ui.pages.analytics.st") as mock_st:
        analytics._render_correlation_view(view)

    mock_st.warning.assert_called_once()
    assert "SHORT (12 days available, window requires 60)" in mock_st.warning.call_args.args[0]


def test_correlation_view_renders_heatmap_table_and_cluster_warning() -> None:
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.render_correlation_heatmap") as mock_heatmap,
    ):
        mock_st.columns.return_value = _columns(2)
        analytics._render_correlation_view(_view())

    mock_st.columns.assert_called_once_with([10, 1])
    mock_heatmap.assert_called_once()
    assert mock_heatmap.call_args.kwargs["colorscale"] == CORRELATION_COLORSCALE_OPTIONS[0][1]
    mock_st.dataframe.assert_called_once()
    mock_st.popover.assert_called_once_with("ⓘ", use_container_width=False)
    warning_text = mock_st.warning.call_args.args[0]
    assert "3 positions move together" in warning_text
    assert "A, B, C" in warning_text


def test_correlation_table_sorts_by_avg_correlation_descending() -> None:
    with patch("app.ui.pages.analytics.st") as mock_st:
        analytics._render_correlation_table(_view())

    table = mock_st.dataframe.call_args.args[0].data
    assert list(table.columns) == ["Ticker", "Avg Correlation", "Diversification"]
    assert list(table["Ticker"]) == ["B", "A", "C"]
    assert table.iloc[0]["Diversification"] == "very low"
    assert "Name" not in table.columns


def test_correlation_view_passes_selected_color_scheme_to_heatmap() -> None:
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.render_correlation_heatmap") as mock_heatmap,
    ):
        mock_st.columns.return_value = _columns(2)
        analytics._render_correlation_view(
            _view(),
            color_scheme="4",
        )

    mock_heatmap.assert_called_once()
    assert mock_heatmap.call_args.kwargs["colorscale"] == CORRELATION_COLORSCALE_OPTIONS[3][1]


def test_correlation_view_help_text_explains_thresholds() -> None:
    """Popover inside _render_correlation_view explains all diversification thresholds."""
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.render_correlation_heatmap"),
        patch("app.ui.pages.analytics._render_correlation_table"),
    ):
        mock_st.columns.return_value = _columns(2)
        analytics._render_correlation_view(_view())

    help_text = mock_st.markdown.call_args.args[0]
    assert "self-correlation is excluded" in help_text
    assert "<0.20 high" in help_text
    assert "<0.40 moderate" in help_text
    assert "<0.60 low" in help_text
    assert ">=0.60 very low" in help_text
