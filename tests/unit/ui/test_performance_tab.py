from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.services.analytics_performance import PerformancePeriod, PerformanceView
from app.ui.pages import analytics


def _view(
    *,
    benchmark_indexed: list[Decimal] | None = None,
    benchmark_fetch_error: str | None = None,
    dates: list[date] | None = None,
    sharpe: Decimal | None = Decimal("1.25"),
    available_days: int = 30,
    requested_period_days: int = 30,
) -> PerformanceView:
    resolved_dates = [
        date(2025, 1, 1),
        date(2025, 1, 2),
        date(2025, 1, 3),
    ] if dates is None else dates
    return PerformanceView(
        period=PerformancePeriod.ONE_MONTH,
        benchmark_label="SPY",
        dates=resolved_dates,
        portfolio_indexed=[Decimal("100"), Decimal("101"), Decimal("102")][
            : len(resolved_dates)
        ],
        benchmark_indexed=benchmark_indexed,
        portfolio_navs_raw=[Decimal("100"), Decimal("101"), Decimal("102")][
            : len(resolved_dates)
        ],
        period_return_pct=Decimal("2"),
        alpha_pct=Decimal("0.4") if benchmark_indexed is not None else None,
        max_drawdown_pct=Decimal("0"),
        volatility_annualised_pct=Decimal("3.2"),
        sharpe=sharpe,
        requested_period_days=requested_period_days,
        available_days=available_days,
        benchmark_fetch_error=benchmark_fetch_error,
    )


def _columns(n: int) -> list[MagicMock]:
    cols = []
    for _ in range(n):
        col = MagicMock()
        col.__enter__ = MagicMock(return_value=col)
        col.__exit__ = MagicMock(return_value=False)
        cols.append(col)
    return cols


def test_empty_state_skips_charts() -> None:
    empty = _view(dates=[], sharpe=None)
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.render_line_chart") as mock_line,
        patch("app.ui.pages.analytics.render_drawdown_chart") as mock_drawdown,
    ):
        analytics._render_performance_view(empty)

    mock_st.info.assert_called_once_with(
        "Performance data is being collected. Check back after the next NAV snapshot."
    )
    mock_line.assert_not_called()
    mock_drawdown.assert_not_called()


def test_full_render_draws_kpis_and_charts() -> None:
    view = _view(benchmark_indexed=[Decimal("100"), Decimal("100.5"), Decimal("101")])
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.render_metric_card"),
        patch("app.ui.pages.analytics.render_line_chart") as mock_line,
        patch("app.ui.pages.analytics.render_drawdown_chart") as mock_drawdown,
    ):
        mock_st.columns.return_value = _columns(5)
        analytics._render_performance_view(view)

    mock_st.columns.assert_called_once_with(5)
    assert mock_line.call_args.kwargs["secondary_series"] is not None
    assert mock_line.call_args.kwargs["primary_name"] == "Portfolio"
    assert mock_line.call_args.kwargs["secondary_name"] == "SPY"
    assert mock_line.call_args.kwargs["y_axis_mode"] == "plain"
    assert mock_line.call_args.kwargs["y_axis_title"] == "Index, start = 100"
    mock_drawdown.assert_called_once()


def test_benchmark_none_renders_alpha_placeholder() -> None:
    view = _view(benchmark_indexed=None)
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.render_metric_card") as mock_card,
        patch("app.ui.pages.analytics.render_line_chart") as mock_line,
        patch("app.ui.pages.analytics.render_drawdown_chart"),
    ):
        mock_st.columns.return_value = _columns(5)
        analytics._render_performance_view(view)

    assert mock_line.call_args.kwargs["secondary_series"] is None
    alpha_call = mock_card.call_args_list[1]
    assert alpha_call.args[1] == "—"


def test_benchmark_fetch_error_surfaces_warning() -> None:
    view = _view(benchmark_indexed=None, benchmark_fetch_error="rate limit")
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.render_metric_card"),
        patch("app.ui.pages.analytics.render_line_chart"),
        patch("app.ui.pages.analytics.render_drawdown_chart"),
    ):
        mock_st.columns.return_value = _columns(5)
        analytics._render_performance_view(view)

    mock_st.warning.assert_called_once()
    assert "rate limit" in mock_st.warning.call_args.args[0]


def test_available_days_caption_is_rendered() -> None:
    view = _view(available_days=12, requested_period_days=30)
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.render_metric_card"),
        patch("app.ui.pages.analytics.render_line_chart"),
        patch("app.ui.pages.analytics.render_drawdown_chart"),
    ):
        mock_st.columns.return_value = _columns(5)
        analytics._render_performance_view(view)

    mock_st.caption.assert_called_once_with("1M (showing 12 days available)")


def test_negative_sharpe_uses_neutral_class() -> None:
    view = _view(sharpe=Decimal("-0.42"))
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.render_metric_card") as mock_card,
        patch("app.ui.pages.analytics.render_line_chart"),
        patch("app.ui.pages.analytics.render_drawdown_chart"),
    ):
        mock_st.columns.return_value = _columns(5)
        analytics._render_performance_view(view)

    sharpe_call = mock_card.call_args_list[4]
    assert sharpe_call.kwargs["value_class"] == "gain-neutral"
