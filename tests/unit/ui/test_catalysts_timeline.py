"""Tests for the catalysts timeline component (TICKET-PANEL-2).

Cover band grouping/ordering, the portfolio vs position differences (ticker column,
book-wide marker), the estimated-vs-confirmed visual distinction, companion-table
sorting, the empty state, and HTML escaping of event-supplied text.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from app.domain.catalysts import CatalystEvent
from app.ui.components._chart_styles import CATALYST_CATEGORY_COLORS
from app.ui.components.catalysts_timeline import (
    _event_html,
    _legend_html,
    build_catalysts_table,
    group_events_by_band,
    render_catalysts_timeline,
)

AS_OF = date(2026, 6, 5)


def _event(
    *,
    date_: date,
    label: str = "Q2 earnings",
    ticker: str | None = "NVDA",
    category: str = "earnings",
    impact: str = "high",
    scope: str = "position",
    date_confidence: str = "confirmed",
) -> CatalystEvent:
    return CatalystEvent(
        ticker=ticker,
        date=date_,
        label=label,
        category=category,  # type: ignore[arg-type]
        impact=impact,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        date_confidence=date_confidence,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Test case 1 — band grouping, empty bands omitted, ordered this_week → later
# ---------------------------------------------------------------------------

def test_groups_into_ordered_nonempty_bands() -> None:
    events = [
        _event(date_=date(2026, 6, 8), label="this week"),       # +3d  → this_week
        _event(date_=date(2026, 6, 25), label="this month"),     # +20d → this_month
        _event(date_=date(2026, 12, 22), label="later"),         # +200d → later
    ]
    bands = group_events_by_band(events, as_of=AS_OF)
    # next_3_months is empty and omitted; order is nearest-term first.
    assert [band for band, _ in bands] == ["this_week", "this_month", "later"]
    assert [len(evs) for _, evs in bands] == [1, 1, 1]


def test_events_within_band_are_date_ascending() -> None:
    events = [
        _event(date_=date(2026, 6, 11), label="later in week"),
        _event(date_=date(2026, 6, 6), label="tomorrow"),
    ]
    bands = group_events_by_band(events, as_of=AS_OF)
    assert len(bands) == 1
    labels = [e.label for e in bands[0][1]]
    assert labels == ["tomorrow", "later in week"]


# ---------------------------------------------------------------------------
# Test case 2 — portfolio mode: ticker shown; book-wide macro marked once
# ---------------------------------------------------------------------------

def test_portfolio_position_event_shows_ticker() -> None:
    html = _event_html(_event(date_=date(2026, 6, 8), ticker="MRVL"), mode="portfolio")
    assert '<span class="catalyst-ticker">MRVL</span>' in html
    assert "Book-wide" not in html


def test_portfolio_macro_event_marked_book_wide_without_ticker() -> None:
    macro = _event(
        date_=date(2026, 6, 17),
        label="FOMC decision",
        ticker=None,
        category="macro",
        scope="portfolio",
    )
    html = _event_html(macro, mode="portfolio")
    assert "Book-wide" in html
    assert 'class="catalyst-ticker"' not in html


def test_position_mode_omits_ticker_chip() -> None:
    # In position mode the ticker is page context, so it isn't repeated per row.
    html = _event_html(_event(date_=date(2026, 6, 8), ticker="NVDA"), mode="position")
    assert 'class="catalyst-ticker"' not in html


# ---------------------------------------------------------------------------
# Test case 3 — estimated vs confirmed render distinctly
# ---------------------------------------------------------------------------

def test_estimated_event_distinct_from_confirmed() -> None:
    confirmed = _event_html(
        _event(date_=date(2026, 6, 8), date_confidence="confirmed"), mode="portfolio"
    )
    estimated = _event_html(
        _event(date_=date(2026, 6, 8), date_confidence="estimated"), mode="portfolio"
    )
    # Confirmed: filled dot, no tilde, no estimated class.
    assert "estimated" not in confirmed
    assert "~" not in confirmed
    assert "background:" in confirmed
    # Estimated: hollow dot (border only), "~" prefix, estimated class.
    assert "catalyst-event impact-high estimated" in estimated
    assert "cat-dot estimated" in estimated
    assert "~" in estimated
    assert "border-color:" in estimated


def test_event_uses_category_colour_token() -> None:
    html = _event_html(_event(date_=date(2026, 6, 8), category="earnings"), mode="portfolio")
    assert CATALYST_CATEGORY_COLORS["earnings"] in html


# ---------------------------------------------------------------------------
# Test case 4 — companion table sorting + ticker column only in portfolio mode
# ---------------------------------------------------------------------------

def test_table_sorted_by_date_with_ticker_in_portfolio_mode() -> None:
    events = [
        _event(date_=date(2026, 8, 26), ticker="NVDA", label="late"),
        _event(date_=date(2026, 6, 11), ticker="MRVL", label="early"),
    ]
    df = build_catalysts_table(events, mode="portfolio")
    assert list(df.columns) == ["Date", "Event", "Ticker", "Category", "Impact"]
    assert list(df["Date"]) == ["2026-06-11", "2026-08-26"]
    assert list(df["Ticker"]) == ["MRVL", "NVDA"]


def test_table_macro_event_ticker_is_portfolio_label() -> None:
    macro = _event(date_=date(2026, 6, 17), ticker=None, scope="portfolio")
    df = build_catalysts_table([macro], mode="portfolio")
    assert list(df["Ticker"]) == ["Portfolio"]


def test_table_omits_ticker_column_in_position_mode() -> None:
    df = build_catalysts_table([_event(date_=date(2026, 6, 8))], mode="position")
    assert list(df.columns) == ["Date", "Event", "Category", "Impact"]


# ---------------------------------------------------------------------------
# Test case 5 — empty state
# ---------------------------------------------------------------------------

def test_empty_input_renders_message_without_exception() -> None:
    with (
        patch("app.ui.components.catalysts_timeline.render_html") as mock_html,
        patch("app.ui.components.catalysts_timeline.st") as mock_st,
    ):
        render_catalysts_timeline([], as_of=AS_OF, mode="portfolio")
    rendered = " ".join(call.args[0] for call in mock_html.call_args_list)
    assert "No upcoming catalysts" in rendered
    # No timeline grid and no table when empty.
    mock_st.dataframe.assert_not_called()


def test_nonempty_renders_legend_timeline_and_table() -> None:
    events = [_event(date_=date(2026, 6, 8))]
    with (
        patch("app.ui.components.catalysts_timeline.render_html") as mock_html,
        patch("app.ui.components.catalysts_timeline.st") as mock_st,
    ):
        render_catalysts_timeline(events, as_of=AS_OF, mode="portfolio", updated=date(2026, 6, 5))
    rendered = " ".join(call.args[0] for call in mock_html.call_args_list)
    assert "catalysts-legend" in rendered
    assert "catalysts-timeline" in rendered
    assert "catalysts as of 2026-06-05" in rendered
    mock_st.dataframe.assert_called_once()


# ---------------------------------------------------------------------------
# Test case 6 — HTML escaping of event-supplied text (ROBUST-1)
# ---------------------------------------------------------------------------

def test_label_is_html_escaped() -> None:
    html = _event_html(
        _event(date_=date(2026, 6, 8), label="<script>alert(1)</script>"),
        mode="portfolio",
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_ticker_is_html_escaped() -> None:
    html = _event_html(
        _event(date_=date(2026, 6, 8), ticker="<b>X</b>"), mode="portfolio"
    )
    assert "<b>X</b>" not in html
    assert "&lt;b&gt;X&lt;/b&gt;" in html


# ---------------------------------------------------------------------------
# Legend covers all six categories + the today marker
# ---------------------------------------------------------------------------

def test_legend_lists_all_categories_and_today() -> None:
    html = _legend_html(AS_OF)
    for label in ("Earnings", "Macro", "Product", "Regulatory", "Dividend", "Lockup"):
        assert label in html
    assert "today · 2026-06-05" in html
