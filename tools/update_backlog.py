#!/usr/bin/env python3
"""
Update BACKLOG.md: append a ticket row to the named Milestone table,
and optionally update the "Next up" section.

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


def update_backlog(
    ticket_id: str,
    title: str,
    milestone: str,
    priority: str,
    estimate: str,
    next_up: bool,
) -> None:
    text = BACKLOG.read_text()

    # --- Append row to milestone table ---
    header = f"## Milestone — {milestone}"
    if header not in text:
        sys.exit(f"Error: milestone '{milestone}' not found in {BACKLOG}.\n"
                 f"Available milestones:\n" +
                 "\n".join(re.findall(r"## Milestone — (.+)", text)))

    # Find the table inside this milestone section (first | after the header)
    # Insert the new row before the blank line that ends the table
    section_start = text.index(header)
    # Find the last table row in this section (line starting with |)
    section_text = text[section_start:]
    # Find all | lines in the section before the next ## or end
    next_section = re.search(r"\n## ", section_text[len(header):])
    section_end = (section_start + len(header) + next_section.start()
                   if next_section else len(text))
    section = text[section_start:section_end]

    # Find position of last table row
    table_rows = list(re.finditer(r"\n\| [^|]", section))
    if not table_rows:
        sys.exit(f"Error: no table found in milestone section '{milestone}'")

    last_row_end = section_start + table_rows[-1].end() - 1
    # Move to end of that line
    eol = text.index("\n", last_row_end)

    new_row = f"\n| {ticket_id} | {title} | QUEUED | {priority} | {estimate} |"
    text = text[:eol] + new_row + text[eol:]

    # --- Update Next up section if requested ---
    if next_up:
        next_up_pattern = r"(## Next up \(in execution order\)\n\n)"
        match = re.search(next_up_pattern, text)
        if match:
            insert_pos = match.end()
            text = (text[:insert_pos] +
                    f"1. {ticket_id} — {title}\n" +
                    text[insert_pos:])

    BACKLOG.write_text(text)
    print(f"Updated {BACKLOG}: added {ticket_id} to '{milestone}' table"
          + (" and Next up" if next_up else ""))


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
