#!/usr/bin/env python3
"""
Update PROJECT_STATE.md "Next up" pointer.

Usage:
    python tools/update_state.py --id TICKET-042 --title "My ticket title"

Prepends a new item to the "Next up" ordered list.
"""
import argparse
import re
from pathlib import Path

STATE = Path("docs/PROJECT_STATE.md")


def update_next_up(ticket_id: str, title: str) -> None:
    text = STATE.read_text()

    pattern = r"(### Next up 📋\n1\.)"
    match = re.search(pattern, text)
    if not match:
        # Section may be empty or numbered differently — just insert after header
        pattern2 = r"(### Next up 📋\n)"
        match2 = re.search(pattern2, text)
        if not match2:
            raise SystemExit("Error: 'Next up' section not found in PROJECT_STATE.md")
        insert_pos = match2.end()
        text = text[:insert_pos] + f"1. {ticket_id} — {title}\n" + text[insert_pos:]
    else:
        # Renumber: insert as item 1, shift existing items down
        insert_pos = match.start() + len("### Next up 📋\n")
        text = text[:insert_pos] + f"1. {ticket_id} — {title}\n" + text[insert_pos:]
        # Renumber old items (they were 1., 2., ...) — now shift by 1
        # Find the block of numbered items after our insertion
        after = text[insert_pos + len(f"1. {ticket_id} — {title}\n"):]
        def renumber(m: re.Match) -> str:
            return f"{int(m.group(1)) + 1}."
        renumbered = re.sub(r"^(\d+)\.", renumber, after, flags=re.MULTILINE, count=10)
        text = text[:insert_pos + len(f"1. {ticket_id} — {title}\n")] + renumbered

    STATE.write_text(text)
    print(f"Updated {STATE}: prepended '{ticket_id} — {title}' to Next up")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--title", required=True)
    args = parser.parse_args()
    update_next_up(ticket_id=args.id, title=args.title)


if __name__ == "__main__":
    main()
