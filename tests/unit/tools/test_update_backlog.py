"""Tests for tools/update_backlog.py."""
import json
from pathlib import Path
from unittest.mock import MagicMock

BACKLOG_WITH_MILESTONE = """\
## Milestone — Foundation

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-001 | First ticket | MERGED | CRITICAL | 1 hr |

---

## Milestone — UI core

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|

---

## Next up (in execution order)

1. *Panel framework brainstorm session*

---

**Workflow reminder:** complete specs first.
"""

BACKLOG_WITHOUT_NEW_MILESTONE = """\
## Milestone — Foundation

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|

---

## Next up (in execution order)

1. *Panel framework brainstorm session*

---

**Workflow reminder:** complete specs first.
"""


def _no_gh(*args: object, **kwargs: object) -> MagicMock:  # type: ignore[type-arg]
    m = MagicMock()
    m.returncode = 0
    m.stdout = json.dumps([])
    return m


def _run_update(
    backlog_path: Path,
    ticket_id: str = "TICKET-042",
    title: str = "Test ticket",
    milestone: str = "Foundation",
    priority: str = "HIGH",
    estimate: str = "1 hr",
    next_up: bool = False,
) -> None:
    from unittest.mock import patch as _patch

    # Patch BACKLOG constant so the function works on our temp file
    with _patch("tools.update_backlog.BACKLOG", backlog_path):
        with _patch("tools._next_up.BACKLOG_PATH", backlog_path):
            with _patch("tools.sync_state.subprocess.run", side_effect=_no_gh):
                with _patch("tools._next_up.subprocess.run", side_effect=_no_gh):
                    from tools.update_backlog import update_backlog
                    update_backlog(ticket_id, title, milestone, priority, estimate, next_up)


# ---------------------------------------------------------------------------
# Auto-create milestone
# ---------------------------------------------------------------------------

def test_missing_milestone_auto_created(tmp_path: Path) -> None:
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text(BACKLOG_WITHOUT_NEW_MILESTONE)

    _run_update(backlog, milestone="Company Deep Dive")

    text = backlog.read_text()
    assert "## Milestone — Company Deep Dive" in text


def test_auto_created_section_has_correct_template(tmp_path: Path) -> None:
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text(BACKLOG_WITHOUT_NEW_MILESTONE)

    _run_update(backlog, milestone="New Milestone")

    text = backlog.read_text()
    assert "| ID | Title | Status | Priority | Est |" in text
    assert "|---|---|---|---|---|" in text


def test_auto_created_section_is_before_next_up(tmp_path: Path) -> None:
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text(BACKLOG_WITHOUT_NEW_MILESTONE)

    _run_update(backlog, milestone="Inserted Milestone")

    text = backlog.read_text()
    inserted_pos = text.index("## Milestone — Inserted Milestone")
    next_up_pos = text.index("## Next up (in execution order)")
    assert inserted_pos < next_up_pos


# ---------------------------------------------------------------------------
# Row insertion — correct separator placement
# ---------------------------------------------------------------------------

def test_new_row_goes_after_separator_not_after_another_row(tmp_path: Path) -> None:
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text(BACKLOG_WITH_MILESTONE)

    _run_update(backlog, ticket_id="TICKET-042", milestone="Foundation")

    text = backlog.read_text()
    lines = text.splitlines()

    # Find the Foundation section
    sep_idx = next(
        i for i, line in enumerate(lines)
        if line.startswith("|---|") and "Foundation" in text[: text.index(line)]
    )
    # The separator must come BEFORE any TICKET-042 row
    ticket_idx = next(i for i, line in enumerate(lines) if "TICKET-042" in line)
    assert sep_idx < ticket_idx, "Separator row must appear before data row"


def test_appending_to_existing_section(tmp_path: Path) -> None:
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text(BACKLOG_WITH_MILESTONE)

    _run_update(backlog, ticket_id="TICKET-042", milestone="Foundation")

    text = backlog.read_text()
    assert "TICKET-001" in text  # existing row preserved
    assert "TICKET-042" in text  # new row added


# ---------------------------------------------------------------------------
# All CLI flags preserved
# ---------------------------------------------------------------------------

def test_all_cli_flags_accepted(tmp_path: Path) -> None:
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text(BACKLOG_WITH_MILESTONE)

    _run_update(
        backlog,
        ticket_id="TICKET-099",
        title="Full test",
        milestone="Foundation",
        priority="CRITICAL",
        estimate="2 hr",
        next_up=True,
    )

    text = backlog.read_text()
    assert "TICKET-099" in text
