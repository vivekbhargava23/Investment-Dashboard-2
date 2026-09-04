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
    priority: str = "HIGH",
) -> None:
    status_lines = [f"**Status:** {status}"] if status is not None else []
    path = root / "docs" / "TICKETS" / f"{ticket_id}-{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join([
            f"# {ticket_id} \u2014 {title}",
            "",
            f"**Priority:** {priority}",
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

    # Every startable ticket outranks every blocked one, whatever the priorities.
    blocked_positions = [
        index
        for index, entry in enumerate(_mod.rank_next_tickets(entries))
        if _mod.blockers_for(entry, by_id)
    ]
    startable_positions = [
        index
        for index, entry in enumerate(_mod.rank_next_tickets(entries))
        if not _mod.blockers_for(entry, by_id)
    ]
    assert max(startable_positions) < min(blocked_positions)


def test_blocked_critical_ranks_below_startable_lower_priority(tmp_path: Path) -> None:
    """A CRITICAL you cannot start must not sit above a HIGH you can."""
    _ticket_file(
        tmp_path, "TICKET-A1", "root", "Root work", "**Depends on:** \u2014",
        priority="HIGH",
    )
    _ticket_file(
        tmp_path, "TICKET-A2", "gated", "Gated work", "**Depends on:** A1",
        priority="CRITICAL",
    )
    board_items = [
        _item(301, "TICKET-A2", "Gated work", "Backlog"),
        _item(302, "TICKET-A1", "Root work", "Backlog"),
    ]
    entries = _mod.enrich_missing_dependencies(
        _mod.build_ticket_entries(board_items, tmp_path), tmp_path
    )

    ranked_ids = [entry.ticket_id for entry in _mod.rank_next_tickets(entries)]

    assert ranked_ids == ["TICKET-A1", "TICKET-A2"]


def test_ready_outranks_backlog_among_startable_tickets(tmp_path: Path) -> None:
    """Dragging a card to Ready is Vivek's override; it beats computed priority."""
    _ticket_file(
        tmp_path, "TICKET-B1", "vetted", "Vetted work", "**Depends on:** \u2014",
        priority="MEDIUM",
    )
    _ticket_file(
        tmp_path, "TICKET-B2", "urgent", "Urgent work", "**Depends on:** \u2014",
        priority="CRITICAL",
    )
    board_items = [
        _item(311, "TICKET-B2", "Urgent work", "Backlog"),
        _item(312, "TICKET-B1", "Vetted work", "Ready"),
    ]
    entries = _mod.enrich_missing_dependencies(
        _mod.build_ticket_entries(board_items, tmp_path), tmp_path
    )

    ranked_ids = [entry.ticket_id for entry in _mod.rank_next_tickets(entries)]

    assert ranked_ids == ["TICKET-B1", "TICKET-B2"]


def test_unblock_score_counts_the_whole_downstream_chain(tmp_path: Path) -> None:
    """Direct-dependent counting under-scored the root of a dependency chain."""
    chain = [
        ("TICKET-S2", "mapping", "Mapping write path", "**Depends on:** \u2014"),
        ("TICKET-S3", "manage", "Manage rows read-only", "**Depends on:** S2"),
        ("TICKET-S6A", "engine", "Sync engine", "**Depends on:** S2 + S3"),
        ("TICKET-S6B", "page", "Sync page", "**Depends on:** S6A"),
        ("TICKET-S7", "retire", "Retire workbench", "**Depends on:** S6B"),
    ]
    for ticket_id, slug, title, body in chain:
        _ticket_file(tmp_path, ticket_id, slug, title, body)
    board_items = [
        _item(400 + offset, ticket_id, title, "Backlog")
        for offset, (ticket_id, _, title, _) in enumerate(chain)
    ]
    entries = _mod.enrich_missing_dependencies(
        _mod.build_ticket_entries(board_items, tmp_path), tmp_path
    )
    by_id = _mod.entry_by_ticket_id(entries)

    assert _mod.unblock_score(by_id["TICKET-S2"], entries) == 4
    assert _mod.unblock_score(by_id["TICKET-S6A"], entries) == 2
    assert _mod.unblock_score(by_id["TICKET-S7"], entries) == 0


_SYNC_ROW = (
    "1",
    "SYNC-1",
    "CRITICAL",
    "Sonnet",
    "#204",
    "Backlog",
    "Stamp ISIN on every row",
    "unblocks 5",
)


def test_truncate_marks_elided_text() -> None:
    assert _mod.truncate("NAV history", 20) == "NAV history"
    assert _mod.truncate("NAV history backfill", 11) == "NAV histor…"
    assert _mod.truncate("anything", 0) == ""


def test_menu_table_aligns_columns_and_fits_terminal_width() -> None:
    rows = [
        _SYNC_ROW,
        ("2", "RD5", "HIGH", "Opus", "#144", "Backlog", "NAV history backfill", "ready"),
    ]

    lines = _mod.format_menu_table(rows, 120)

    assert lines[0].split() == list(_mod.MENU_HEADERS)
    assert set(lines[1].strip()) == {"-", " "}
    assert "SYNC-1" in lines[2] and "unblocks 5" in lines[2]
    assert all(len(line) <= 120 for line in lines)
    header_offset = lines[0].index("Title")
    assert lines[2].index("Stamp ISIN") == header_offset
    assert lines[3].index("NAV history") == header_offset


def test_menu_table_keeps_title_readable_on_narrow_terminals() -> None:
    lines = _mod.format_menu_table([_SYNC_ROW], 40)

    assert "Stamp" in lines[2]


def _reorder_fixture(tmp_path: Path) -> list:
    """A board whose card stack is deliberately in the wrong order."""
    tickets = [
        ("TICKET-C1", "root", "Root work", "**Depends on:** \u2014", "HIGH"),
        ("TICKET-C2", "gated", "Gated work", "**Depends on:** C1", "CRITICAL"),
        ("TICKET-C3", "loose", "Loose work", "**Depends on:** \u2014", "MEDIUM"),
    ]
    for ticket_id, slug, title, body, priority in tickets:
        _ticket_file(tmp_path, ticket_id, slug, title, body, priority=priority)
    # Board order: the blocked CRITICAL sits on top, which is what we are fixing.
    board_items = [
        dict(_item(501, "TICKET-C2", "Gated work", "Backlog"), id="PVTI_c2"),
        dict(_item(502, "TICKET-C3", "Loose work", "Backlog"), id="PVTI_c3"),
        dict(_item(503, "TICKET-C1", "Root work", "Backlog"), id="PVTI_c1"),
    ]
    return _mod.enrich_missing_dependencies(
        _mod.build_ticket_entries(board_items, tmp_path), tmp_path
    )


def test_build_ticket_entries_captures_board_item_id(tmp_path: Path) -> None:
    entries = _reorder_fixture(tmp_path)
    by_id = _mod.entry_by_ticket_id(entries)

    assert by_id["TICKET-C1"].board_item_id == "PVTI_c1"


def test_reorder_dry_run_reports_target_order_without_moving(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("dry run must not touch the board")

    monkeypatch.setattr(_mod, "move_board_item_after", _fail)
    monkeypatch.setattr(_mod, "project_id", _fail)

    assert _mod.reorder_board(_reorder_fixture(tmp_path), dry_run=True) == 0

    out = capsys.readouterr().out
    assert out.index("C1") < out.index("C3") < out.index("C2")
    assert "Dry run" in out


def test_reorder_pins_each_card_after_the_previous_one(
    tmp_path: Path, monkeypatch
) -> None:
    moves: list[tuple[str, str | None]] = []
    monkeypatch.setattr(_mod, "project_id", lambda: "PVT_board")
    monkeypatch.setattr(
        _mod,
        "move_board_item_after",
        lambda project, item, after: moves.append((item, after)),
    )

    assert _mod.reorder_board(_reorder_fixture(tmp_path)) == 0

    # Startable HIGH, then startable MEDIUM, then the blocked CRITICAL — each one
    # anchored to the card placed immediately above it.
    assert moves == [
        ("PVTI_c1", None),
        ("PVTI_c3", "PVTI_c1"),
        ("PVTI_c2", "PVTI_c3"),
    ]


def test_reorder_is_a_noop_when_the_board_already_matches(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("a matching board must not be touched")

    monkeypatch.setattr(_mod, "move_board_item_after", _fail)
    monkeypatch.setattr(_mod, "project_id", _fail)
    entries = _reorder_fixture(tmp_path)
    ranked = _mod.rank_next_tickets(entries)
    # Rebuild with the board already in ranked order.
    ordered = [
        entry.__class__(**{**entry.__dict__, "board_index": index})
        for index, entry in enumerate(ranked)
    ]

    assert _mod.reorder_board(ordered) == 0
    assert "already matches" in capsys.readouterr().out
