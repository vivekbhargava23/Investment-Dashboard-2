#!/usr/bin/env bash
# Draft a new ticket from a spec on stdin.
#
# Reads a header block (before "---") and a ticket body (after "---").
# Header format:
#   ID: TICKET-<NNN>
#   TITLE: <one-line title>
#   MILESTONE: <name, used for GitHub milestone assignment>
#   PRIORITY: CRITICAL | HIGH | MEDIUM | LOW
#   ESTIMATE: <free text, e.g. "1 – 1.5 hr">
#   POSITION: <optional integer; insert at position N in Up next; default: append>
#   ---
#   <full markdown ticket body>
#
# Example:
#   cat spec.txt | bash tools/draft_ticket.sh
#
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# --- Branch guard: must run from main ---
CURRENT_BRANCH="$(git branch --show-current)"
if [ "$CURRENT_BRANCH" != "main" ]; then
  echo "Error: tools/draft_ticket.sh must be run from main." >&2
  echo "  You are on: $CURRENT_BRANCH" >&2
  echo "  Run: git checkout main && git pull" >&2
  exit 1
fi

# --- Clean-tree guard: no uncommitted changes ---
if [ -n "$(git status --porcelain)" ]; then
  echo "Error: working tree is dirty. Commit or stash before drafting a ticket." >&2
  git status --short >&2
  exit 1
fi

# --- Reconcile state against GitHub before touching anything ---
echo "Reconciling state against GitHub..."
PYTHONPATH=. python3 tools/sync_state.py
echo ""

# --- Read stdin ---
INPUT="$(cat)"

# --- Parse header (everything before the first "---" line) ---
HEADER="$(echo "$INPUT" | awk '/^---$/{exit} {print}')"
BODY="$(echo "$INPUT" | awk 'found{print} /^---$/{found=1}')"

parse_field() {
  echo "$HEADER" | grep "^$1:" | sed "s/^$1: *//"
}

ID="$(parse_field ID)"
TITLE="$(parse_field TITLE)"
MILESTONE="$(parse_field MILESTONE)"
PRIORITY="$(parse_field PRIORITY)"
ESTIMATE="$(parse_field ESTIMATE)"
POSITION="$(parse_field POSITION)"

# --- Validate ---
if [ -z "$ID" ] || [ -z "$TITLE" ] || [ -z "$MILESTONE" ] || [ -z "$PRIORITY" ]; then
  echo "Error: missing required header field (ID, TITLE, MILESTONE, or PRIORITY)" >&2
  exit 1
fi

# --- Derive slug from title ---
SLUG="$(echo "$TITLE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//' | cut -c1-50)"
FILENAME="docs/TICKETS/${ID}-${SLUG}.md"

# --- Write ticket file ---
echo "$BODY" > "$FILENAME"
echo "Wrote ticket file: $FILENAME"

# --- Map priority to GitHub label ---
case "$PRIORITY" in
  CRITICAL) GH_PRIORITY_LABEL="critical" ;;
  HIGH)     GH_PRIORITY_LABEL="high" ;;
  MEDIUM)   GH_PRIORITY_LABEL="medium" ;;
  LOW)      GH_PRIORITY_LABEL="low" ;;
  *) echo "Error: unknown priority '$PRIORITY'" >&2; exit 1 ;;
esac

# --- Check GitHub milestone (only open milestones can be assigned via gh cli) ---
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
OPEN_MILESTONE="$(gh api "repos/$REPO/milestones?state=open" \
  --jq ".[] | select(.title == \"$MILESTONE\") | .title")"

# --- Create GitHub issue ---
GH_LABELS="queued,$GH_PRIORITY_LABEL"

ISSUE_BODY="Ticket file: \`$FILENAME\`

$(head -40 "$FILENAME")"

if [ -n "$OPEN_MILESTONE" ]; then
  ISSUE_URL="$(gh issue create \
    --title "$ID — $TITLE" \
    --body "$ISSUE_BODY" \
    --label "$GH_LABELS" \
    --milestone "$MILESTONE")"
else
  echo "Note: milestone '$MILESTONE' is closed or missing — creating issue without milestone assignment" >&2
  ISSUE_URL="$(gh issue create \
    --title "$ID — $TITLE" \
    --body "$ISSUE_BODY" \
    --label "$GH_LABELS")"
fi
echo "Created GitHub issue: $ISSUE_URL"

# --- Append to STATE.md "Up next" ---
PYTHONPATH=. python3 - <<PYEOF
import re, sys
from pathlib import Path

state = Path("docs/STATE.md")
text = state.read_text()

header = "### Next up 📋"
m = re.search(re.escape(header) + r"\n", text)
if not m:
    print("Warning: 'Next up 📋' section not found in STATE.md — skipping Up next update", flush=True)
    sys.exit(0)

start = m.end()
rest = text[start:]
next_sec = re.search(r"\n(###|---)", rest)
end = start + (next_sec.start() if next_sec else len(rest))
section = text[start:end]

numbers = [int(n) for n in re.findall(r"^(\d+)\.", section, re.MULTILINE)]
next_num = (max(numbers) if numbers else 0) + 1

ticket_id = "$ID"
title = "$TITLE"
priority = "$PRIORITY"
position_raw = "$POSITION"
new_line = f"{next_num}. {ticket_id} — {title} [{priority}]"

# Re-number if POSITION is given
if position_raw.strip().isdigit():
    pos = int(position_raw.strip())
    existing = [ln for ln in section.splitlines() if re.match(r"^\d+\.", ln.strip())]
    existing.insert(pos - 1, f"X. {ticket_id} — {title} [{priority}]")
    renumbered = []
    n = 1
    for ln in existing:
        if re.match(r"^\d+\.", ln.strip()):
            renumbered.append(re.sub(r"^\d+", str(n), ln.strip()))
            n += 1
    freeform = [ln for ln in section.splitlines() if ln.strip().startswith("*") and ln.strip().endswith("*")]
    for ff in freeform:
        renumbered.append(f"{n}. {ff.strip()}")
        n += 1
    new_section = "\n" + "\n".join(renumbered) + "\n"
else:
    stripped = section.rstrip("\n")
    new_section = stripped + "\n" + new_line + "\n"

new_text = text[:start] + new_section + text[end:]
state.write_text(new_text)
print(f"Appended to STATE.md 'Up next': {new_line}", flush=True)
PYEOF

# --- Commit and push ---
git add "$FILENAME" docs/STATE.md
git commit -m "docs: draft $ID $TITLE"
git push origin main
echo "Committed and pushed."
