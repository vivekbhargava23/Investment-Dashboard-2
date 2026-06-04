"""Tests for ticket workflow dependency parsing and ranking."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "ticket_workflow.py"
_spec = importlib.util.spec_from_file_location("ticket_workflow", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["ticket_workflow"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]


def _ticket_file(
    root: Path,
    ticket_id: str,
    slug: str,
    title: str,
    body: str,
    *,
    status: str | None = None,
) -> None:
    status_lines = [f"**Status:** {status}"] if status is not None else []
    path = root / "docs" / "TICKETS" / f"{ticket_id}-{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join([
            f"# {ticket_id} \u2014 {title}",
            "",
            "**Priority:** HIGH",
            *status_lines,
            "**Recommended model:** Sonnet - test",
            body,
            "",
        ]),
        encoding="utf-8",
    )


def _item(number: int, ticket_id: str, title: str, status: str) -> dict:
    return {
        "status": status,
        "content": {
            "number": number,
            "title": f"{ticket_id} \u2014 {title}",
            "body": "",
        },
    }


def test_parse_dependencies_handles_dash_bare_and_full_ids() -> None:
    assert _mod.parse_dependencies("**Depends on:** \u2014") == ()
    assert _mod.parse_dependencies("**Depends on:** RD1 + RD2 (sortable table)") == (
        "TICKET-RD1",
        "TICKET-RD2",
    )
    assert _mod.parse_dependencies("**Depends on:** TICKET-013 (already merged)") == (
        "TICKET-013",
    )
    assert _mod.parse_dependencies("**Dependencies:** CSV-13 and ROBUST-1") == (
        "TICKET-CSV-13",
        "TICKET-ROBUST-1",
    )


def test_duplicate_ticket_file_resolution_uses_matching_title(tmp_path: Path) -> None:
    _ticket_file(
        tmp_path,
        "TICKET-M9",
        "automate-worktree-and-env",
        "Automate worktree creation and conda env activation in the agent ritual",
        "**Depends on:** \u2014",
    )
    _ticket_file(
        tmp_path,
        "TICKET-M9",
        "collapse-ritual-into-tools",
        "Collapse the session ritual into tools (cut token + permission overhead)",
        "**Depends on:** \u2014",
    )

    found = _mod.find_ticket_file(
        tmp_path,
        "TICKET-M9",
        "TICKET-M9 \u2014 Collapse the session ritual into tools (cut token + permission overhead)",
    )

    assert found is not None
    assert found.name == "TICKET-M9-collapse-ritual-into-tools.md"


def test_ranking_flags_blockers_and_prefers_unblockers(tmp_path: Path) -> None:
    tickets = [
        (
            "TICKET-M9",
            "collapse",
            "Collapse the session ritual into tools",
            "**Depends on:** \u2014",
        ),
        ("TICKET-RD6", "inline", "Inline tranches", "**Depends on:** RD1 + RD2"),
        ("TICKET-RD5", "nav", "NAV history backfill", "**Depends on:** TICKET-013"),
        ("TICKET-RD4", "analytics", "Split analytics", "**Depends on:** \u2014"),
        ("TICKET-RD3", "searchbox", "Unified ticker searchbox", "**Depends on:** RD0"),
        ("TICKET-RD2", "sort", "Sortable positions table", "**Depends on:** RD1"),
        ("TICKET-RD1", "html", "Overview HTML overhaul", "**Depends on:** \u2014"),
        ("TICKET-RD0", "nav", "Navigation focus spine", "**Depends on:** \u2014"),
        ("TICKET-RD7", "conc", "Concentration block", "**Depends on:** RD4"),
    ]
    for ticket_id, slug, title, body in tickets:
        _ticket_file(tmp_path, ticket_id, slug, title, body)
    _ticket_file(
        tmp_path,
        "TICKET-013",
        "daily-nav-snapshot",
        "Daily NAV snapshot service",
        "**Depends on:** \u2014",
        status="MERGED",
    )

    board_items = [
        _item(150, "TICKET-M9", "Collapse the session ritual into tools", "Backlog"),
        _item(145, "TICKET-RD6", "Inline tranches", "Backlog"),
        _item(144, "TICKET-RD5", "NAV history backfill", "Backlog"),
        _item(143, "TICKET-RD4", "Split analytics", "Backlog"),
        _item(142, "TICKET-RD3", "Unified ticker searchbox", "Backlog"),
        _item(141, "TICKET-RD2", "Sortable positions table", "Backlog"),
        _item(140, "TICKET-RD1", "Overview HTML overhaul", "Backlog"),
        _item(139, "TICKET-RD0", "Navigation focus spine", "Backlog"),
        _item(146, "TICKET-RD7", "Concentration block", "Backlog"),
    ]

    entries = _mod.enrich_missing_dependencies(
        _mod.build_ticket_entries(board_items, tmp_path),
        tmp_path,
    )
    by_id = _mod.entry_by_ticket_id(entries)
    ranked_ids = [entry.ticket_id for entry in _mod.rank_next_tickets(entries)]

    assert _mod.blockers_for(by_id["TICKET-RD5"], by_id) == ()
    assert _mod.blockers_for(by_id["TICKET-RD6"], by_id) == ("RD1", "RD2")
    assert _mod.blockers_for(by_id["TICKET-RD2"], by_id) == ("RD1",)
    assert _mod.blockers_for(by_id["TICKET-RD3"], by_id) == ("RD0",)
    assert _mod.blockers_for(by_id["TICKET-RD7"], by_id) == ("RD4",)
    assert ranked_ids.index("TICKET-RD1") < ranked_ids.index("TICKET-RD2")
    assert ranked_ids.index("TICKET-RD1") < ranked_ids.index("TICKET-RD6")
    assert ranked_ids.index("TICKET-RD4") < ranked_ids.index("TICKET-RD7")
