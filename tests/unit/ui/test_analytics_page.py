"""Smoke / call-shape tests for app.ui.pages.analytics."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.ui.pages.analytics import _shell


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
        patch("app.ui.pages.analytics._shell.st") as mock_st,
        patch("app.ui.pages.analytics._shell.performance.render"),
        patch("app.ui.pages.analytics._shell.correlation.render"),
        patch("app.ui.pages.analytics._shell.technicals.render"),
        patch("app.ui.pages.analytics._shell.sizer.render"),
        patch("app.ui.pages.analytics._shell.concentration.render"),
    ):
        mock_st.tabs.return_value = tabs
        _shell.render()


def test_five_tabs_with_expected_labels() -> None:
    """st.tabs is called once with the exact five-label list."""
    tabs = _make_tab_mocks(5)
    with (
        patch("app.ui.pages.analytics._shell.st") as mock_st,
        patch("app.ui.pages.analytics._shell.performance.render"),
        patch("app.ui.pages.analytics._shell.correlation.render"),
        patch("app.ui.pages.analytics._shell.technicals.render"),
        patch("app.ui.pages.analytics._shell.sizer.render"),
        patch("app.ui.pages.analytics._shell.concentration.render"),
    ):
        mock_st.tabs.return_value = tabs
        _shell.render()

    mock_st.tabs.assert_called_once_with(
        ["Performance", "Correlation", "Technicals", "Position Sizer", "Concentration"],
        key="analytics_tabs",
        default="Performance",
    )


def test_no_placeholder_info_messages_remain() -> None:
    """No tab should be calling st.info with a placeholder TICKET-AX message."""
    tabs = _make_tab_mocks(5)
    info_calls: list[str] = []

    with (
        patch("app.ui.pages.analytics._shell.st") as mock_st,
        patch("app.ui.pages.analytics._shell.performance.render"),
        patch("app.ui.pages.analytics._shell.correlation.render"),
        patch("app.ui.pages.analytics._shell.technicals.render"),
        patch("app.ui.pages.analytics._shell.sizer.render"),
        patch("app.ui.pages.analytics._shell.concentration.render"),
    ):
        mock_st.tabs.return_value = tabs
        mock_st.info.side_effect = lambda msg: info_calls.append(msg)
        _shell.render()

    assert "Coming in TICKET-A3" not in info_calls
    assert len(info_calls) == 0


def test_performance_tab_body_is_called() -> None:
    tabs = _make_tab_mocks(5)
    with (
        patch("app.ui.pages.analytics._shell.st") as mock_st,
        patch("app.ui.pages.analytics._shell.performance.render") as mock_perf,
        patch("app.ui.pages.analytics._shell.correlation.render"),
        patch("app.ui.pages.analytics._shell.technicals.render"),
        patch("app.ui.pages.analytics._shell.sizer.render"),
        patch("app.ui.pages.analytics._shell.concentration.render"),
    ):
        mock_st.tabs.return_value = tabs
        _shell.render()

    mock_perf.assert_called_once()


def test_correlation_tab_body_is_called() -> None:
    tabs = _make_tab_mocks(5)
    with (
        patch("app.ui.pages.analytics._shell.st") as mock_st,
        patch("app.ui.pages.analytics._shell.performance.render"),
        patch("app.ui.pages.analytics._shell.correlation.render") as mock_corr,
        patch("app.ui.pages.analytics._shell.technicals.render"),
        patch("app.ui.pages.analytics._shell.sizer.render"),
        patch("app.ui.pages.analytics._shell.concentration.render"),
    ):
        mock_st.tabs.return_value = tabs
        _shell.render()

    mock_corr.assert_called_once()


def test_technicals_tab_body_is_called() -> None:
    tabs = _make_tab_mocks(5)
    with (
        patch("app.ui.pages.analytics._shell.st") as mock_st,
        patch("app.ui.pages.analytics._shell.performance.render"),
        patch("app.ui.pages.analytics._shell.correlation.render"),
        patch("app.ui.pages.analytics._shell.technicals.render") as mock_tech,
        patch("app.ui.pages.analytics._shell.sizer.render"),
        patch("app.ui.pages.analytics._shell.concentration.render"),
    ):
        mock_st.tabs.return_value = tabs
        _shell.render()

    mock_tech.assert_called_once()


def test_no_duplicate_page_header() -> None:
    """render() must not emit a duplicate h1/h2 page header (topbar owns the title)."""
    tabs = _make_tab_mocks(5)
    markdown_calls: list[str] = []

    with (
        patch("app.ui.pages.analytics._shell.st") as mock_st,
        patch("app.ui.pages.analytics._shell.performance.render"),
        patch("app.ui.pages.analytics._shell.correlation.render"),
        patch("app.ui.pages.analytics._shell.technicals.render"),
        patch("app.ui.pages.analytics._shell.sizer.render"),
        patch("app.ui.pages.analytics._shell.concentration.render"),
    ):
        mock_st.tabs.return_value = tabs
        mock_st.markdown.side_effect = lambda s, **kw: markdown_calls.append(str(s))
        _shell.render()

    assert not any("# 📊 Analytics" in s for s in markdown_calls), (
        "Duplicate '# 📊 Analytics' header found — topbar already shows the page title"
    )
