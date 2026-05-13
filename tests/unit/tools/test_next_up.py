"""Tests for tools/_next_up.py."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools._next_up import (
    _get_milestone_order,
    extract_freeform_entries,
    rebuild_next_up_list,
)

BACKLOG_SAMPLE = """\
## Milestone — Foundation

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|

---

## Milestone — UI core

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|

---

## Milestone — Company Deep Dive

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|

---

## Next up (in execution order)

1. *Panel framework brainstorm session*

---
"""


def _fake_issues(*issues: dict) -> MagicMock:  # type: ignore[type-arg]
    m = MagicMock()
    m.returncode = 0
    m.stdout = json.dumps(list(issues))
    return m


def _make_issue(
    number: int,
    title: str,
    labels: list[str],
    milestone: str | None = None,
) -> dict:  # type: ignore[type-arg]
    return {
        "number": number,
        "title": title,
        "labels": [{"name": lbl} for lbl in labels],
        "milestone": {"title": milestone} if milestone else None,
    }


# ---------------------------------------------------------------------------
# _get_milestone_order
# ---------------------------------------------------------------------------

def test_milestone_order_returns_correct_indices(tmp_path: Path) -> None:
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text(BACKLOG_SAMPLE)
    order = _get_milestone_order(backlog)
    assert order["Foundation"] == 0
    assert order["UI core"] == 1
    assert order["Company Deep Dive"] == 2


# ---------------------------------------------------------------------------
# rebuild_next_up_list — ordering
# ---------------------------------------------------------------------------

def test_ordering_by_milestone_then_issue_number(tmp_path: Path) -> None:
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text(BACKLOG_SAMPLE)

    issues = [
        _make_issue(20, "TICKET-020 — Third", ["queued"], "Company Deep Dive"),
        _make_issue(15, "TICKET-015 — First", ["queued"], "Foundation"),
        _make_issue(18, "TICKET-018 — Second", ["queued"], "Foundation"),
    ]
    with patch("tools._next_up.subprocess.run", return_value=_fake_issues(*issues)):
        entries = rebuild_next_up_list(backlog)

    assert [e.ticket_id for e in entries] == ["TICKET-015", "TICKET-018", "TICKET-020"]


def test_issue_number_is_tiebreaker(tmp_path: Path) -> None:
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text(BACKLOG_SAMPLE)

    issues = [
        _make_issue(12, "TICKET-012 — B", ["queued"], "UI core"),
        _make_issue(11, "TICKET-011 — A", ["queued"], "UI core"),
    ]
    with patch("tools._next_up.subprocess.run", return_value=_fake_issues(*issues)):
        entries = rebuild_next_up_list(backlog)

    assert entries[0].issue_number == 11
    assert entries[1].issue_number == 12


# ---------------------------------------------------------------------------
# rebuild_next_up_list — filtering
# ---------------------------------------------------------------------------

def test_superseded_issues_excluded(tmp_path: Path) -> None:
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text(BACKLOG_SAMPLE)

    issues = [
        _make_issue(1, "TICKET-001 — Keep", ["queued"]),
        _make_issue(2, "TICKET-002 — Drop", ["queued", "superseded"]),
    ]
    with patch("tools._next_up.subprocess.run", return_value=_fake_issues(*issues)):
        entries = rebuild_next_up_list(backlog)

    assert len(entries) == 1
    assert entries[0].ticket_id == "TICKET-001"


def test_blocked_issues_excluded(tmp_path: Path) -> None:
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text(BACKLOG_SAMPLE)

    issues = [
        _make_issue(3, "TICKET-003 — Blocked", ["queued", "blocked"]),
    ]
    with patch("tools._next_up.subprocess.run", return_value=_fake_issues(*issues)):
        entries = rebuild_next_up_list(backlog)

    assert entries == []


# ---------------------------------------------------------------------------
# rebuild_next_up_list — gh failure
# ---------------------------------------------------------------------------

def test_raises_on_gh_failure(tmp_path: Path) -> None:
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text(BACKLOG_SAMPLE)

    failed = MagicMock()
    failed.returncode = 1
    failed.stderr = "authentication required"

    with patch("tools._next_up.subprocess.run", return_value=failed):
        with pytest.raises(RuntimeError, match="gh CLI not authenticated or offline"):
            rebuild_next_up_list(backlog)


# ---------------------------------------------------------------------------
# extract_freeform_entries
# ---------------------------------------------------------------------------

def test_extract_freeform_returns_italic_lines() -> None:
    text = "*Panel framework brainstorm session*\nsome other line"
    assert extract_freeform_entries(text) == ["*Panel framework brainstorm session*"]


def test_extract_freeform_skips_non_italic() -> None:
    text = "TICKET-001 — Normal entry\n*freeform*\nplain text"
    assert extract_freeform_entries(text) == ["*freeform*"]


def test_extract_freeform_empty_on_no_matches() -> None:
    assert extract_freeform_entries("TICKET-001 — Normal\n2. Another item") == []
