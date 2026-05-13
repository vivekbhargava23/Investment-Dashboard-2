#!/usr/bin/env python3
"""
Update STATE.md "Next up 📋" section.

Usage:
    python tools/update_state.py --id TICKET-042 --title "My ticket title"

The --id and --title arguments are kept for backwards compatibility with
draft_ticket.sh but have no effect on the output — the Next up section is
always fully rebuilt from GitHub Issues (not prepended).
"""
import argparse
from pathlib import Path

STATE = Path("docs/STATE.md")


def update_next_up(ticket_id: str, title: str) -> None:  # noqa: ARG001 (backwards compat args)
    try:
        from tools._next_up import extract_freeform_entries, rebuild_next_up_list
        from tools.sync_state import (
            _build_next_up_lines,
            _extract_numbered_items,
            _replace_section,
            _section_content,
        )
    except RuntimeError as e:
        raise SystemExit(f"Error importing helpers: {e}") from e

    text = STATE.read_text()
    header = "### Next up 📋"

    old_content = _section_content(text, header)
    old_items = _extract_numbered_items(old_content)
    freeform = extract_freeform_entries("\n".join(old_items))

    try:
        entries = rebuild_next_up_list()
    except RuntimeError as e:
        raise SystemExit(
            f"Error: could not rebuild Next up from GitHub: {e}"
        ) from e

    new_lines = _build_next_up_lines(entries, freeform)
    new_content = "\n" + new_lines if new_lines else "\n"
    new_text = _replace_section(text, header, new_content)

    STATE.write_text(new_text)
    print(f"Updated {STATE}: rebuilt Next up with {len(entries)} entries from GitHub")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--title", required=True)
    args = parser.parse_args()
    update_next_up(ticket_id=args.id, title=args.title)


if __name__ == "__main__":
    main()
