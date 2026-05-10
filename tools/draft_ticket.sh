#!/usr/bin/env bash
# Draft a new ticket from a spec on stdin.
#
# Reads a header block (before "---") and a ticket body (after "---").
# Header format:
#   ID: TICKET-<NNN>
#   TITLE: <one-line title>
#   MILESTONE: <name, must match an existing Milestone in BACKLOG.md>
#   PRIORITY: CRITICAL | HIGH | MEDIUM | LOW
#   ESTIMATE: <free text, e.g. "1 – 1.5 hr">
#   NEXT_UP: true | false
#   ---
#   <full markdown ticket body>
#
# Example:
#   cat spec.txt | bash tools/draft_ticket.sh
#
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

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
NEXT_UP="$(parse_field NEXT_UP)"

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

# --- Update BACKLOG.md ---
NEXT_UP_FLAG=""
[ "$NEXT_UP" = "true" ] && NEXT_UP_FLAG="--next-up"
python3 tools/update_backlog.py \
  --id "$ID" \
  --title "$TITLE" \
  --milestone "$MILESTONE" \
  --priority "$PRIORITY" \
  --estimate "$ESTIMATE" \
  $NEXT_UP_FLAG

# --- Update PROJECT_STATE.md Next up pointer ---
if [ "$NEXT_UP" = "true" ]; then
  python3 tools/update_state.py --id "$ID" --title "$TITLE"
fi

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
[ "$NEXT_UP" = "true" ] && GH_LABELS="$GH_LABELS,next-up"

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

# --- Commit and push ---
git add "$FILENAME" docs/TICKETS/BACKLOG.md docs/PROJECT_STATE.md
git commit -m "docs: draft $ID $TITLE"
git push origin main
echo "Committed and pushed."
