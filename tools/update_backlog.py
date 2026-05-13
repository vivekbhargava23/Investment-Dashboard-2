#!/usr/bin/env python3
"""
Update BACKLOG.md: append a ticket row to the named Milestone table and
rebuild the "Next up" section from GitHub Issues.

If the named Milestone section doesn't exist it is auto-created before the
"Next up" section.

Usage:
    python tools/update_backlog.py \\
        --id TICKET-042 \\
        --title "My ticket title" \\
        --milestone "UI polish" \\
        --priority HIGH \\
        --estimate "1 – 1.5 hr" \\
        [--next-up]
"""
import argparse
import re
import sys
from pathlib import Path

BACKLOG = Path("docs/TICKETS/BACKLOG.md")

_MILESTONE_TEMPLATE = """\
## Milestone — {name}

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|

---

"""


def _create_milestone_section(text: str, milestone: str) -> str:
    """Insert a new Milestone section immediately before '## Next up'."""
    next_up_header = "## Next up (in execution order)"
    if next_up_header not in text:
        return text + "\n" + _MILESTONE_TEMPLATE.format(name=milestone)
    insert_pos = text.index(next_up_header)
    new_section = _MILESTONE_TEMPLATE.format(name=milestone)
    return text[:insert_pos] + new_section + text[insert_pos:]


def _append_ticket_row(
    text: str,
    milestone: str,
    ticket_id: str,
    title: str,
    priority: str,
    estimate: str,
) -> str:
    header = f"## Milestone — {milestone}"
    section_start = text.index(header)
    section_text = text[section_start:]

    # Find the end of this milestone section
    next_section = re.search(r"\n## ", section_text[len(header):])
    section_end = (
        section_start + len(header) + next_section.start()
        if next_section
        else len(text)
    )
    section = text[section_start:section_end]

    # Find the separator row (|---|...); the new data row goes immediately after it.
    # This fixes the old bug where rows landed after a stray trailing separator.
    separator_match = re.search(r"\n(\|---[|\-]+)\n", section)
    if separator_match:
        insert_offset = section_start + separator_match.end() - 1  # just before the \n after sep
    else:
        # Fallback: insert after the last table row
        table_rows = list(re.finditer(r"\n\|", section))
        if not table_rows:
            sys.exit(f"Error: no table found in milestone section '{milestone}'")
        insert_offset = section_start + table_rows[-1].end() - 1
        # Advance to end of that line
        insert_offset = text.index("\n", insert_offset)

    new_row = f"\n| {ticket_id} | {title} | QUEUED | {priority} | {estimate} |"
    return text[:insert_offset] + new_row + text[insert_offset:]


def update_backlog(
    ticket_id: str,
    title: str,
    milestone: str,
    priority: str,
    estimate: str,
    next_up: bool,  # kept for backwards compat; Next up is always rebuilt from GitHub
) -> None:
    text = BACKLOG.read_text()

    # Auto-create milestone section if missing
    header = f"## Milestone — {milestone}"
    if header not in text:
        print(f"Milestone '{milestone}' not found — creating section automatically.")
        text = _create_milestone_section(text, milestone)

    # Append the new ticket row (with correct separator placement)
    text = _append_ticket_row(text, milestone, ticket_id, title, priority, estimate)

    # Rebuild Next up from GitHub (always; --next-up flag is now informational only)
    # NOTE: --next-up is still accepted for backwards compat with draft_ticket.sh,
    # but has no effect on output — the rebuild queries GitHub directly.
    try:
        from tools._next_up import extract_freeform_entries, rebuild_next_up_list
        from tools.sync_state import (
            _build_next_up_lines,
            _extract_numbered_items,
            _replace_section,
            _section_content,
        )

        next_up_header = "## Next up (in execution order)"
        old_content = _section_content(text, next_up_header)
        old_items = _extract_numbered_items(old_content)
        freeform = extract_freeform_entries("\n".join(old_items))

        entries = rebuild_next_up_list()
        new_lines = _build_next_up_lines(entries, freeform)
        new_content = "\n" + new_lines if new_lines else "\n"
        text = _replace_section(text, next_up_header, new_content)
        print(f"Rebuilt Next up: {len(entries)} entries from GitHub")
    except RuntimeError as e:
        print(f"Warning: could not rebuild Next up from GitHub: {e}", file=sys.stderr)
        print("Next up section left unchanged.", file=sys.stderr)

    BACKLOG.write_text(text)
    print(f"Updated {BACKLOG}: added {ticket_id} to '{milestone}' table")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--milestone", required=True)
    parser.add_argument("--priority", required=True,
                        choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"])
    parser.add_argument("--estimate", required=True)
    parser.add_argument("--next-up", action="store_true")
    args = parser.parse_args()

    update_backlog(
        ticket_id=args.id,
        title=args.title,
        milestone=args.milestone,
        priority=args.priority,
        estimate=args.estimate,
        next_up=args.next_up,
    )


if __name__ == "__main__":
    main()
