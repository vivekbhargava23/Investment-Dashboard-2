#!/usr/bin/env python3
"""
Reconcile STATE.md against GitHub Issues ground truth.

Usage:
    python3 tools/sync_state.py
        Rebuild In review and In progress sections from GitHub.

    python3 tools/sync_state.py --mark-merged TICKET-XXX --pr N
        Move TICKET-XXX from "In review" to "Done" (with PR #N), append to
        "Recent activity", update "Last updated:", then reconcile.

Does NOT commit. Edits files in place. Idempotent.
Exit 0 on success, 1 on failure.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from tools._next_up import BACKLOG_PATH, NextUpEntry, extract_freeform_entries, rebuild_next_up_list

STATE_PATH = Path("docs/STATE.md")


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------

def _section_bounds(text: str, header: str) -> tuple[int, int]:
    """Return (content_start, content_end) for the section with the given header.

    content_start is the index just after the header newline.
    content_end is the index of the newline that starts the next section (or EOF).
    Returns (-1, -1) if the header is not found.
    """
    pattern = re.escape(header) + r"\n"
    m = re.search(pattern, text)
    if not m:
        return -1, -1
    start = m.end()
    rest = text[start:]
    next_sec = re.search(r"\n(###|---)", rest)
    end = start + (next_sec.start() if next_sec else len(rest))
    return start, end


def _replace_section(text: str, header: str, new_content: str) -> str:
    start, end = _section_bounds(text, header)
    if start == -1:
        return text
    return text[:start] + new_content + text[end:]


def _section_content(text: str, header: str) -> str:
    start, end = _section_bounds(text, header)
    if start == -1:
        return ""
    return text[start:end]


# ---------------------------------------------------------------------------
# GitHub queries
# ---------------------------------------------------------------------------

def _gh(*args: str) -> list[dict]:  # type: ignore[type-arg]
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gh failed: {result.stderr.strip()}")
    return json.loads(result.stdout)  # type: ignore[no-any-return]


def _get_in_review_entries() -> list[tuple[str, str]]:
    """Return (ticket_id, title) for issues linked to open PRs."""
    prs = _gh("pr", "list", "--state", "open", "--json", "number,body", "--limit", "100")
    linked_issue_nums: set[int] = set()
    for pr in prs:
        for m in re.finditer(r"[Cc]loses\s+#(\d+)", pr.get("body") or ""):
            linked_issue_nums.add(int(m.group(1)))

    if not linked_issue_nums:
        return []

    all_open = _gh(
        "issue", "list", "--state", "open",
        "--json", "number,title",
        "--limit", "200",
    )
    entries = []
    for issue in all_open:
        if issue["number"] not in linked_issue_nums:
            continue
        m = re.match(r"^(TICKET-\S+)\s*—\s*(.+)$", issue["title"])
        if m:
            entries.append((m.group(1), m.group(2).strip()))
        else:
            entries.append((issue["title"], issue["title"]))
    return entries


def _get_in_progress_entries() -> list[tuple[str, str]]:
    """Return (ticket_id, title) for issues labelled in-progress."""
    issues = _gh(
        "issue", "list", "--label", "in-progress",
        "--state", "open",
        "--json", "number,title",
        "--limit", "100",
    )
    entries = []
    for issue in issues:
        m = re.match(r"^(TICKET-\S+)\s*—\s*(.+)$", issue["title"])
        if m:
            entries.append((m.group(1), m.group(2).strip()))
        else:
            entries.append((issue["title"], issue["title"]))
    return entries


# ---------------------------------------------------------------------------
# Next-up rebuild helpers
# ---------------------------------------------------------------------------

def _build_next_up_lines(
    entries: list[NextUpEntry], freeform: list[str]
) -> str:
    lines = []
    for i, e in enumerate(entries, 1):
        lines.append(f"{i}. {e.ticket_id} — {e.title}")
    offset = len(entries) + 1
    for j, item in enumerate(freeform):
        lines.append(f"{offset + j}. {item}")
    return "\n".join(lines) + "\n" if lines else ""


def _extract_numbered_items(section_content: str) -> list[str]:
    """Strip N. prefix from numbered list lines; return the content parts."""
    items = []
    for line in section_content.splitlines():
        m = re.match(r"^\d+\.\s+(.+)$", line.strip())
        if m:
            items.append(m.group(1))
    return items


# ---------------------------------------------------------------------------
# STATE.md updates
# ---------------------------------------------------------------------------

def _update_last_updated(text: str) -> str:
    today = date.today().isoformat()
    return re.sub(
        r"\*\*Last updated:\*\*.*",
        f"**Last updated:** {today} by GitHub Actions (post-merge housekeeping)",
        text,
        count=1,
    )


def _rebuild_next_up_state(state_path: Path, backlog_path: Path) -> str:
    text = state_path.read_text()
    header = "### Next up 📋"

    old_content = _section_content(text, header)
    old_items = _extract_numbered_items(old_content)
    freeform = extract_freeform_entries("\n".join(old_items))

    entries = rebuild_next_up_list(backlog_path)
    new_lines = _build_next_up_lines(entries, freeform)

    # Preserve the trailing "See BACKLOG.md..." line that follows the section
    new_content = "\n" + new_lines if new_lines else "\n"
    text = _replace_section(text, header, new_content)
    return text


def _rebuild_in_review(state_path: Path) -> tuple[str, int, int]:
    """Return (updated_text, old_count, new_count)."""
    text = state_path.read_text()
    header = "### In review 👀"
    old_content = _section_content(text, header)
    old_count = sum(
        1 for line in old_content.splitlines() if line.strip().startswith("- TICKET-")
    )

    try:
        entries = _get_in_review_entries()
    except RuntimeError as e:
        raise RuntimeError(f"update_in_review: {e}") from e

    if entries:
        lines = "\n".join(f"- {tid} — {title}" for tid, title in entries)
        new_content = "\n" + lines + "\n"
    else:
        new_content = "\n(none)\n"

    text = _replace_section(text, header, new_content)
    return text, old_count, len(entries)


def _rebuild_in_progress(state_path: Path) -> tuple[str, int, int]:
    """Return (updated_text, old_count, new_count)."""
    text = state_path.read_text()
    header = "### In progress 🚧"
    old_content = _section_content(text, header)
    old_count = sum(
        1 for line in old_content.splitlines() if line.strip().startswith("- TICKET-")
    )

    try:
        entries = _get_in_progress_entries()
    except RuntimeError as e:
        raise RuntimeError(f"update_in_progress: {e}") from e

    if entries:
        lines = "\n".join(f"- {tid} — {title}" for tid, title in entries)
        new_content = "\n" + lines + "\n"
    else:
        new_content = "\n(none)\n"

    text = _replace_section(text, header, new_content)
    return text, old_count, len(entries)


# ---------------------------------------------------------------------------
# BACKLOG.md updates
# ---------------------------------------------------------------------------

def _rebuild_next_up_backlog(backlog_path: Path) -> str:
    text = backlog_path.read_text()
    header = "## Next up (in execution order)"

    old_content = _section_content(text, header)
    old_items = _extract_numbered_items(old_content)
    freeform = extract_freeform_entries("\n".join(old_items))

    entries = rebuild_next_up_list(backlog_path)
    new_lines = _build_next_up_lines(entries, freeform)

    new_content = "\n" + new_lines if new_lines else "\n"
    return _replace_section(text, header, new_content)


def _mark_merged_backlog(backlog_path: Path, ticket_id: str) -> None:
    text = backlog_path.read_text()
    # Match the row for this ticket and replace its status column (3rd column)
    pattern = re.compile(
        r"(\|\s*" + re.escape(ticket_id) + r"\s*\|[^|]*\|)\s*\S+\s*(\|)",
    )
    new_text, n = pattern.subn(r"\1 MERGED \2", text, count=1)
    if n == 0:
        print(f"  Warning: {ticket_id} row not found in {backlog_path}", file=sys.stderr)
    backlog_path.write_text(new_text)


# ---------------------------------------------------------------------------
# mark_merged
# ---------------------------------------------------------------------------

def mark_merged(
    ticket_id: str,
    pr_num: int,
    state_path: Path = STATE_PATH,
    backlog_path: Path = BACKLOG_PATH,  # kept for backwards compat; no longer used
) -> None:
    """Move ticket_id from 'In review' to 'Done' in STATE.md.

    Also appends to 'Recent activity' and bumps 'Last updated:'.
    Then runs the standard reconciliation.
    """
    text = state_path.read_text()

    # Find the ticket's entry in In review
    in_review_content = _section_content(text, "### In review 👀")
    pattern = re.compile(r"^- (" + re.escape(ticket_id) + r") — (.+)$", re.MULTILINE)
    m = pattern.search(in_review_content)
    if not m:
        raise SystemExit(
            f"Error: {ticket_id} not found in 'In review 👀' section of {state_path}.\n"
            "The workflow expects the agent to have set IN_REVIEW before push."
        )
    title = m.group(2).strip()

    # Remove from In review
    new_in_review = re.sub(
        r"\n- " + re.escape(ticket_id) + r" —[^\n]*", "", in_review_content
    )
    remaining = [
        ln for ln in new_in_review.splitlines() if ln.strip().startswith("- TICKET-")
    ]
    new_in_review_content = (
        "\n" + "\n".join(f"- {ln.strip().lstrip('- ')}" for ln in remaining) + "\n"
        if remaining
        else "\n(none)\n"
    )
    text = _replace_section(text, "### In review 👀", new_in_review_content)

    # Append to Done ✓
    done_header = "### Done ✓ (last 5)"
    done_content = _section_content(text, done_header)
    new_entry = f"- {ticket_id} — {title} (PR #{pr_num})"
    stripped = done_content.rstrip("\n")
    new_done_content = stripped + "\n" + new_entry + "\n"
    text = _replace_section(text, done_header, new_done_content)

    # Update Last updated
    text = _update_last_updated(text)
    state_path.write_text(text)
    print(f"  {ticket_id}: moved In review → Done ✓ (PR #{pr_num})")

    # Append to Recent activity (create section if missing)
    text = state_path.read_text()
    today = date.today().isoformat()
    activity_header = "### Recent activity 📅"
    activity_entry = f"- {today} — {ticket_id} merged (PR #{pr_num})"
    if activity_header not in text:
        # Create section before "## Key decisions" or at end
        key_decisions = "## Key decisions"
        if key_decisions in text:
            insert_pos = text.index(key_decisions)
            new_section = f"{activity_header}\n\n{activity_entry}\n\n---\n\n"
            text = text[:insert_pos] + new_section + text[insert_pos:]
        else:
            text = text.rstrip("\n") + f"\n\n{activity_header}\n\n{activity_entry}\n"
    else:
        ra_start, ra_end = _section_bounds(text, activity_header)
        old_content = text[ra_start:ra_end]
        existing = [ln for ln in old_content.splitlines() if ln.strip().startswith("-")]
        all_entries = [activity_entry] + existing
        all_entries = all_entries[:10]  # keep newest 10
        new_content = "\n" + "\n".join(all_entries) + "\n"
        text = text[:ra_start] + new_content + text[ra_end:]
    state_path.write_text(text)
    print(f"  {ticket_id}: Recent activity updated")

    # Remove from Up next if still present (defense in depth)
    text = state_path.read_text()
    up_next_header = "### Next up 📋"
    if up_next_header in text:
        up_start, up_end = _section_bounds(text, up_next_header)
        old_up = text[up_start:up_end]
        new_up_lines = [
            ln for ln in old_up.splitlines()
            if ticket_id not in ln
        ]
        new_up = "\n".join(new_up_lines)
        if not new_up.strip():
            new_up = "\n(none)\n"
        elif not new_up.startswith("\n"):
            new_up = "\n" + new_up
        if not new_up.endswith("\n"):
            new_up = new_up + "\n"
        text = text[:up_start] + new_up + text[up_end:]
        state_path.write_text(text)

    # Standard reconciliation
    _sync_all(state_path, backlog_path)


# ---------------------------------------------------------------------------
# Standard reconciliation
# ---------------------------------------------------------------------------

def _sync_all(
    state_path: Path = STATE_PATH,
    backlog_path: Path = BACKLOG_PATH,  # kept for backwards compat; no longer used
) -> None:
    # Rebuild In review in STATE.md
    try:
        text, old, new = _rebuild_in_review(state_path)
        state_path.write_text(text)
        change = f" (was {old})" if old != new else ""
        print(f"  In review: {new} entries{change}")
    except RuntimeError as e:
        print(f"  Warning: could not rebuild In review: {e}", file=sys.stderr)

    # Rebuild In progress in STATE.md
    try:
        text, old, new = _rebuild_in_progress(state_path)
        state_path.write_text(text)
        change = f" (was {old})" if old != new else ""
        print(f"  In progress: {new} entries{change}")
    except RuntimeError as e:
        print(f"  Warning: could not rebuild In progress: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mark-merged", metavar="TICKET-ID",
                        help="ticket ID to move from In review to Done")
    parser.add_argument("--pr", type=int, metavar="N",
                        help="PR number (required with --mark-merged)")
    args = parser.parse_args()

    if args.mark_merged and not args.pr:
        parser.error("--pr N is required with --mark-merged")
    if args.pr and not args.mark_merged:
        parser.error("--mark-merged TICKET-ID is required with --pr")

    try:
        if args.mark_merged:
            mark_merged(args.mark_merged, args.pr)
        else:
            _sync_all()
    except (RuntimeError, SystemExit) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
