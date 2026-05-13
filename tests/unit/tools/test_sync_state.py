"""Tests for tools/sync_state.py."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.sync_state import (
    _replace_section,
    _section_content,
    mark_merged,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STATE_TEMPLATE = """\
# STATE.md

**Last updated:** 2026-01-01 by Claude Code

---

## Current status

### Done ✓ (last 5)
- TICKET-001 — Old ticket (PR #1)

### In review 👀
- TICKET-M3 — Tooling self-heal

### Closed without merging ⊘
(none)

### In progress 🚧
(none)

### Next up 📋
1. *Panel framework brainstorm session*

### Recent activity 📅

- 2026-01-01 — TICKET-001 merged (PR #1)
"""

BACKLOG_TEMPLATE = """\
## Milestone — Workflow & tooling

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-M3 | Tooling self-heal: ... | IN_REVIEW | HIGH | 1.5 – 2 hr |

---

## Next up (in execution order)

1. *Panel framework brainstorm session*

---

**Workflow reminder:** keep specs complete.
"""


def _write_fixtures(tmp_path: Path) -> tuple[Path, Path]:
    state = tmp_path / "PROJECT_STATE.md"
    backlog = tmp_path / "BACKLOG.md"
    state.write_text(STATE_TEMPLATE)
    backlog.write_text(BACKLOG_TEMPLATE)
    return state, backlog


# ---------------------------------------------------------------------------
# _section_content / _replace_section helpers
# ---------------------------------------------------------------------------

def test_section_content_extracts_correctly() -> None:
    text = "### In review 👀\n- TICKET-001 — Title\n\n### Next\n"
    content = _section_content(text, "### In review 👀")
    assert "TICKET-001" in content


def test_replace_section_replaces_correctly() -> None:
    text = "### In review 👀\n- TICKET-001 — Title\n\n### Next\n"
    new_text = _replace_section(text, "### In review 👀", "\n(none)\n")
    assert "TICKET-001" not in new_text
    assert "(none)" in new_text
    assert "### Next" in new_text


# ---------------------------------------------------------------------------
# mark_merged
# ---------------------------------------------------------------------------

def _no_gh(*args: object, **kwargs: object) -> MagicMock:  # type: ignore[type-arg]
    """Stub _gh calls in sync_state so mark_merged tests don't hit GitHub."""
    m = MagicMock()
    m.returncode = 0
    m.stdout = json.dumps([])
    return m


def test_mark_merged_moves_to_done(tmp_path: Path) -> None:
    state, backlog = _write_fixtures(tmp_path)

    with patch("tools.sync_state.subprocess.run", side_effect=_no_gh):
        with patch("tools._next_up.subprocess.run", side_effect=_no_gh):
            mark_merged("TICKET-M3", 99, state_path=state, backlog_path=backlog)

    text = state.read_text()
    assert "TICKET-M3 — Tooling self-heal (PR #99)" in text
    assert "### Done ✓" in text
    # Must no longer appear in In review
    in_review = _section_content(text, "### In review 👀")
    assert "TICKET-M3" not in in_review


def test_mark_merged_sets_last_updated(tmp_path: Path) -> None:
    state, backlog = _write_fixtures(tmp_path)
    with patch("tools.sync_state.subprocess.run", side_effect=_no_gh):
        with patch("tools._next_up.subprocess.run", side_effect=_no_gh):
            mark_merged("TICKET-M3", 42, state_path=state, backlog_path=backlog)

    from datetime import date
    today = date.today().isoformat()
    assert today in state.read_text()



def test_mark_merged_fails_when_ticket_not_in_review(tmp_path: Path) -> None:
    state, backlog = _write_fixtures(tmp_path)
    with pytest.raises(SystemExit, match="not found in 'In review"):
        mark_merged("TICKET-UNKNOWN", 99, state_path=state, backlog_path=backlog)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_sync_idempotent(tmp_path: Path) -> None:
    """Running sync twice should produce no diff on second run."""
    state, backlog = _write_fixtures(tmp_path)

    # Run mark_merged once
    with patch("tools.sync_state.subprocess.run", side_effect=_no_gh):
        with patch("tools._next_up.subprocess.run", side_effect=_no_gh):
            mark_merged("TICKET-M3", 99, state_path=state, backlog_path=backlog)

    state_after_first = state.read_text()
    backlog_after_first = backlog.read_text()

    # Import and run the sync again (without mark_merged)
    from tools.sync_state import _sync_all
    with patch("tools.sync_state.subprocess.run", side_effect=_no_gh):
        with patch("tools._next_up.subprocess.run", side_effect=_no_gh):
            _sync_all(state_path=state, backlog_path=backlog)

    assert state.read_text() == state_after_first
    assert backlog.read_text() == backlog_after_first
