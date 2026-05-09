"""Smoke / call-shape tests for app.ui.pages.analytics."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.ui.pages import analytics


def _make_tab_mocks(n: int) -> list[MagicMock]:
    """Return n MagicMock context managers (each supports 'with' syntax)."""
    tabs = []
    for _ in range(n):
        tab = MagicMock()
        tab.__enter__ = MagicMock(return_value=tab)
        tab.__exit__ = MagicMock(return_value=False)
        tabs.append(tab)
    return tabs


def test_render_no_exception() -> None:
    """Page renders without raising when called with no positions."""
    tabs = _make_tab_mocks(5)
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics._render_performance_tab"),
        patch("app.ui.pages.analytics._render_sizer_tab"),
        patch("app.ui.pages.analytics._render_concentration_tab"),
    ):
        mock_st.tabs.return_value = tabs
        analytics.render()


def test_five_tabs_with_expected_labels() -> None:
    """st.tabs is called once with the exact five-label list."""
    tabs = _make_tab_mocks(5)
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics._render_performance_tab"),
        patch("app.ui.pages.analytics._render_sizer_tab"),
        patch("app.ui.pages.analytics._render_concentration_tab"),
    ):
        mock_st.tabs.return_value = tabs
        analytics.render()

    mock_st.tabs.assert_called_once_with(
        ["Performance", "Correlation", "Technicals", "Position Sizer", "Concentration"]
    )


def test_non_performance_tabs_show_correct_info_message() -> None:
    """Placeholder tabs still call st.info with their corresponding TICKET-AX message."""
    tabs = _make_tab_mocks(5)
    info_calls: list[str] = []

    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics._render_performance_tab"),
        patch("app.ui.pages.analytics._render_sizer_tab"),
        patch("app.ui.pages.analytics._render_concentration_tab"),
    ):
        mock_st.tabs.return_value = tabs
        mock_st.info.side_effect = lambda msg: info_calls.append(msg)
        analytics.render()

    assert "Coming in TICKET-A2" in info_calls
    assert "Coming in TICKET-A3" in info_calls
    assert len(info_calls) == 2


def test_performance_tab_body_is_called() -> None:
    tabs = _make_tab_mocks(5)
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics._render_performance_tab") as mock_perf,
        patch("app.ui.pages.analytics._render_sizer_tab"),
        patch("app.ui.pages.analytics._render_concentration_tab"),
    ):
        mock_st.tabs.return_value = tabs
        analytics.render()

    mock_perf.assert_called_once()


def test_page_header_uses_analytics_icon() -> None:
    """st.markdown is called with '# 📊 Analytics' for the page header."""
    tabs = _make_tab_mocks(5)
    markdown_calls: list[str] = []

    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics._render_performance_tab"),
        patch("app.ui.pages.analytics._render_sizer_tab"),
        patch("app.ui.pages.analytics._render_concentration_tab"),
    ):
        mock_st.tabs.return_value = tabs
        mock_st.markdown.side_effect = lambda s, **kw: markdown_calls.append(str(s))
        analytics.render()

    assert any("# 📊 Analytics" in s for s in markdown_calls)
