#!/usr/bin/env python3
"""Shared helper: rebuild the ordered Next-up list from GitHub Issues."""
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

BACKLOG_PATH = Path("docs/TICKETS/BACKLOG.md")


@dataclass
class NextUpEntry:
    ticket_id: str
    title: str
    issue_number: int
    milestone_name: str | None


def _get_milestone_order(backlog_path: Path = BACKLOG_PATH) -> dict[str, int]:
    if not backlog_path.exists():
        return {}
    text = backlog_path.read_text()
    milestones = re.findall(r"^## Milestone — (.+)$", text, re.MULTILINE)
    return {name.strip(): i for i, name in enumerate(milestones)}


def _run_gh(*args: str) -> list[dict]:  # type: ignore[type-arg]
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "gh CLI not authenticated or offline; cannot rebuild Next up: "
            + result.stderr.strip()
        )
    return json.loads(result.stdout)  # type: ignore[no-any-return]


def rebuild_next_up_list(
    backlog_path: Path = BACKLOG_PATH,
) -> list[NextUpEntry]:
    """Query GitHub Issues and return the ordered queued list.

    Ordering: QUEUED issues sorted by (milestone order if available, issue number asc).
    Issues labelled `superseded` or `blocked` are excluded.
    """
    issues = _run_gh(
        "issue", "list",
        "--label", "queued",
        "--state", "open",
        "--json", "number,title,labels,milestone",
        "--limit", "100",
    )

    milestone_order = _get_milestone_order(backlog_path)
    excluded_labels = {"superseded", "blocked"}

    entries: list[NextUpEntry] = []
    for issue in issues:
        label_names = {lbl["name"] for lbl in issue.get("labels", [])}
        if excluded_labels & label_names:
            continue

        milestone = issue.get("milestone")
        milestone_name = milestone["title"] if milestone else None

        m = re.match(r"^(TICKET-\S+)\s*—\s*(.+)$", issue["title"])
        if m:
            ticket_id = m.group(1)
            title = m.group(2).strip()
        else:
            ticket_id = issue["title"]
            title = issue["title"]

        entries.append(
            NextUpEntry(
                ticket_id=ticket_id,
                title=title,
                issue_number=issue["number"],
                milestone_name=milestone_name,
            )
        )

    def sort_key(e: NextUpEntry) -> tuple[int, int]:
        milestone_idx = (
            milestone_order.get(e.milestone_name, 999) if e.milestone_name else 999
        )
        return (milestone_idx, e.issue_number)

    entries.sort(key=sort_key)
    return entries


def extract_freeform_entries(section_text: str) -> list[str]:
    """Return lines starting and ending with * (italic markdown).

    These are non-ticket placeholders preserved across Next-up rebuilds.
    Callers strip numbered-list prefixes before passing section_text.
    """
    result = []
    for line in section_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2:
            result.append(stripped)
    return result
