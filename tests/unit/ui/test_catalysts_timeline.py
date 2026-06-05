"""Tests for the catalysts timeline component (TICKET-PANEL-2).

The timeline is a Plotly scatter: events are markers laid out left → right across
time-zone bands, on a book-wide lane (y=1) and a per-holding lane (y=0), sized by
impact, hollow when estimated, with detail in the hover. Cover band grouping/order,
lane placement, the estimated-vs-confirmed symbol, impact sizing, category colour,
the portfolio-vs-position ticker label, hover content + escaping, and the empty state.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from app.domain.catalysts import CatalystEvent
from app.ui.components._chart_styles import CATALYST_CATEGORY_COLORS
from app.ui.components.catalysts_timeline import (
    _legend_html,
    build_catalysts_timeline_figure,
    build_timeline_points,
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


def _macro(date_: date, **kw: object) -> CatalystEvent:
    return _event(
        date_=date_, ticker=None, category="macro", scope="portfolio", **kw  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Band grouping — ordered, non-empty, date-ascending within a band
# ---------------------------------------------------------------------------

def test_groups_into_ordered_nonempty_bands() -> None:
    events = [
        _event(date_=date(2026, 6, 8), label="this week"),    # +3d  → this_week
        _event(date_=date(2026, 6, 25), label="this month"),  # +20d → this_month
        _event(date_=date(2026, 12, 22), label="later"),      # +200d → later
    ]
    bands = group_events_by_band(events, as_of=AS_OF)
    # next_3_months is empty and omitted; order is nearest-term first.
    assert [band for band, _ in bands] == ["this_week", "this_month", "later"]


def test_events_within_band_are_date_ascending() -> None:
    events = [
        _event(date_=date(2026, 6, 11), label="later in week"),
        _event(date_=date(2026, 6, 6), label="tomorrow"),
    ]
    bands = group_events_by_band(events, as_of=AS_OF)
    assert [e.label for e in bands[0][1]] == ["tomorrow", "later in week"]


# ---------------------------------------------------------------------------
# Lane placement — book-wide above (y=1), per-holding below (y=0)
# ---------------------------------------------------------------------------

def test_bookwide_and_position_events_on_separate_lanes() -> None:
    points = build_timeline_points(
        [
            _macro(date(2026, 6, 17), label="FOMC"),
            _event(date_=date(2026, 6, 8), label="earnings"),
        ],
        as_of=AS_OF,
        mode="portfolio",
    )
    ys = {round(p.y, 3) for p in points}
    assert ys == {0.0, 1.0}


def test_x_increases_across_bands() -> None:
    # One event in this_week (band 0) and one in this_month (band 1).
    points = build_timeline_points(
        [_event(date_=date(2026, 6, 8)), _event(date_=date(2026, 6, 25))],
        as_of=AS_OF,
        mode="portfolio",
    )
    xs = sorted(p.x for p in points)
    assert xs[0] < 1.0 <= xs[1]


def test_events_in_same_band_and_lane_spread_in_x() -> None:
    points = build_timeline_points(
        [
            _event(date_=date(2026, 6, 7), ticker="AAA"),
            _event(date_=date(2026, 6, 9), ticker="BBB"),
        ],
        as_of=AS_OF,
        mode="portfolio",
    )
    xs = [p.x for p in points]
    assert len(set(xs)) == 2  # no overlap


# ---------------------------------------------------------------------------
# Estimated vs confirmed, impact size, category colour
# ---------------------------------------------------------------------------

def test_estimated_marker_is_hollow_confirmed_is_filled() -> None:
    estimated = build_timeline_points(
        [_event(date_=date(2026, 6, 8), date_confidence="estimated")],
        as_of=AS_OF,
        mode="portfolio",
    )[0]
    confirmed = build_timeline_points(
        [_event(date_=date(2026, 6, 8), date_confidence="confirmed")],
        as_of=AS_OF,
        mode="portfolio",
    )[0]
    assert estimated.symbol == "circle-open"
    assert confirmed.symbol == "circle"


def test_impact_drives_marker_size() -> None:
    def size(impact: str) -> int:
        return build_timeline_points(
            [_event(date_=date(2026, 6, 8), impact=impact)], as_of=AS_OF, mode="portfolio"
        )[0].size

    assert size("high") > size("med") > size("low")


def test_marker_uses_category_colour_token() -> None:
    point = build_timeline_points(
        [_event(date_=date(2026, 6, 8), category="earnings")], as_of=AS_OF, mode="portfolio"
    )[0]
    assert point.color == CATALYST_CATEGORY_COLORS["earnings"]


# ---------------------------------------------------------------------------
# On-marker label — ticker in portfolio mode, nothing in position mode
# ---------------------------------------------------------------------------

def test_portfolio_position_marker_labelled_with_ticker() -> None:
    point = build_timeline_points(
        [_event(date_=date(2026, 6, 8), ticker="MRVL")], as_of=AS_OF, mode="portfolio"
    )[0]
    assert point.text == "MRVL"


def test_bookwide_marker_has_no_ticker_label() -> None:
    point = build_timeline_points(
        [_macro(date(2026, 6, 17))], as_of=AS_OF, mode="portfolio"
    )[0]
    assert point.text == ""


def test_position_mode_omits_ticker_label() -> None:
    point = build_timeline_points(
        [_event(date_=date(2026, 6, 8), ticker="NVDA")], as_of=AS_OF, mode="position"
    )[0]
    assert point.text == ""


# ---------------------------------------------------------------------------
# Hover — content + book-wide marking + escaping (ROBUST-1 spirit)
# ---------------------------------------------------------------------------

def test_hover_marks_macro_event_as_portfolio() -> None:
    point = build_timeline_points(
        [_macro(date(2026, 6, 17), label="FOMC decision")], as_of=AS_OF, mode="portfolio"
    )[0]
    assert "Portfolio · FOMC decision" in point.hover
    assert "Macro" in point.hover


def test_hover_includes_ticker_category_impact() -> None:
    point = build_timeline_points(
        [_event(date_=date(2026, 6, 8), ticker="NVDA", impact="high")],
        as_of=AS_OF,
        mode="portfolio",
    )[0]
    assert "NVDA · Q2 earnings" in point.hover
    assert "Earnings · High" in point.hover


def test_estimated_hover_is_marked_and_tilde_prefixed() -> None:
    point = build_timeline_points(
        [_event(date_=date(2026, 6, 8), date_confidence="estimated")],
        as_of=AS_OF,
        mode="portfolio",
    )[0]
    assert point.hover.startswith("~")
    assert "estimated" in point.hover


def test_hover_label_is_escaped() -> None:
    point = build_timeline_points(
        [_event(date_=date(2026, 6, 8), label="<script>alert(1)</script>")],
        as_of=AS_OF,
        mode="portfolio",
    )[0]
    assert "<script>" not in point.hover
    assert "&lt;script&gt;" in point.hover


# ---------------------------------------------------------------------------
# Figure plumbing + empty state + render
# ---------------------------------------------------------------------------

def test_figure_has_one_marker_per_event() -> None:
    events = [
        _event(date_=date(2026, 6, 8)),
        _macro(date(2026, 6, 17)),
        _event(date_=date(2026, 6, 25)),
    ]
    fig = build_catalysts_timeline_figure(events, as_of=AS_OF, mode="portfolio")
    assert fig is not None
    assert len(fig.data[0].x) == 3


def test_empty_input_returns_none_figure() -> None:
    assert build_catalysts_timeline_figure([], as_of=AS_OF, mode="portfolio") is None


def test_render_empty_shows_message_no_chart() -> None:
    with (
        patch("app.ui.components.catalysts_timeline.render_html") as mock_html,
        patch("app.ui.components.catalysts_timeline.st") as mock_st,
    ):
        render_catalysts_timeline([], as_of=AS_OF, mode="portfolio")
    rendered = " ".join(call.args[0] for call in mock_html.call_args_list)
    assert "No upcoming catalysts" in rendered
    mock_st.plotly_chart.assert_not_called()


def test_render_draws_legend_chart_and_updated() -> None:
    events = [_event(date_=date(2026, 6, 8))]
    with (
        patch("app.ui.components.catalysts_timeline.render_html") as mock_html,
        patch("app.ui.components.catalysts_timeline.st") as mock_st,
    ):
        render_catalysts_timeline(
            events, as_of=AS_OF, mode="portfolio", updated=date(2026, 6, 5)
        )
    rendered = " ".join(call.args[0] for call in mock_html.call_args_list)
    assert "catalysts-legend" in rendered
    assert "catalysts as of 2026-06-05" in rendered
    mock_st.plotly_chart.assert_called_once()


# ---------------------------------------------------------------------------
# Legend covers all six categories + estimated + today marker
# ---------------------------------------------------------------------------

def test_legend_lists_all_categories_estimated_and_today() -> None:
    html = _legend_html(AS_OF)
    for label in ("Earnings", "Macro", "Product", "Regulatory", "Dividend", "Lockup"):
        assert label in html
    assert "estimated" in html
    assert "today · 2026-06-05" in html
