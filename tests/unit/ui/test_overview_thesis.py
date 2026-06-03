"""Thesis/horizon rendering on the Overview page reads from data, not hardcoded dicts.

Regression guard for TICKET-THESIS-1: an unknown ticker must render an explicit
"unknown"/"—" badge, never a false "intact"/"H2".
"""
from __future__ import annotations

from app.domain.thesis_map import ThesisEntry
from app.ui.pages.overview import _build_positions_table_html
from tests.unit.ui.test_overview_render import _make_live_position, _make_summary


def test_known_ticker_renders_its_thesis_and_horizon() -> None:
    positions = {"NVDA": _make_live_position("NVDA")}
    summary = _make_summary(positions)
    thesis_entries = {"NVDA": ThesisEntry(thesis="watch", horizon="H1")}

    html = _build_positions_table_html(positions, summary, thesis_entries=thesis_entries)

    assert "Watch" in html  # thesis badge label
    assert ">H1<" in html   # horizon cell


def test_unknown_ticker_renders_unknown_not_intact() -> None:
    """A holding with no thesis entry must not be silently reported as intact/H2."""
    positions = {"ZZZZ": _make_live_position("ZZZZ")}
    summary = _make_summary(positions)

    html = _build_positions_table_html(positions, summary, thesis_entries={})

    assert "Unknown" in html
    assert "badge-grey" in html
    assert "Intact" not in html
    # Horizon cell is the honest em-dash, not a defaulted "H2".
    assert ">H2<" not in html


def test_no_thesis_entries_arg_defaults_to_unknown() -> None:
    """Backward-compat: omitting thesis_entries yields unknown, never intact."""
    positions = {"NVDA": _make_live_position("NVDA")}
    summary = _make_summary(positions)

    html = _build_positions_table_html(positions, summary)

    assert "Unknown" in html
    assert "Intact" not in html
