#!/usr/bin/env bash
# tools/file.sh — file one or more TICKET-*.md files as GitHub issues + board items
#
# Usage: bash tools/file.sh
#
# Finds every untracked docs/TICKETS/TICKET-*.md, validates them, creates GitHub
# issues, adds each issue to the project board (Backlog), sets each item's
# position by priority band (banded-prepend, ADR-010), commits, and pushes.
# No POSITION field. No clean-tree guard for ticket files. No batch separator.
#
# Portability: POSIX sh + bash 3.2+. No GNU-only constructs.
#   Tested on: Linux (bash 5.2, GNU grep 3.11)
#   Known macOS invocation: bash tools/file.sh  (works on stock macOS bash 3.2 + BSD grep)
#   See tools/README.md for toolchain requirements.

set -euo pipefail

PROJECT_NUMBER=2
REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

# ---------------------------------------------------------------------------
# Step 1 — Branch handling
# ---------------------------------------------------------------------------
current_branch="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
if [ "$current_branch" != "main" ]; then
  echo "Not on main (on '$current_branch'). Attempting to switch..."
  # Check for dirty working tree (excluding docs/TICKETS/*.md which we're about to file)
  dirty="$(git -C "$REPO_ROOT" status --porcelain | grep -v '^?? docs/TICKETS/TICKET-' || true)"
  if [ -n "$dirty" ]; then
    echo "Error: working tree has uncommitted changes outside docs/TICKETS/:"
    echo "$dirty"
    echo "Commit or stash these changes before running file.sh."
    exit 1
  fi
  if ! git -C "$REPO_ROOT" checkout main 2>&1; then
    echo "Error: could not switch to main. Resolve the issue above and retry."
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# Step 2 — Pull
# ---------------------------------------------------------------------------
echo "Pulling main..."
if ! git -C "$REPO_ROOT" pull --ff-only origin main; then
  echo "Error: git pull --ff-only failed. Resolve divergence manually and retry."
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 3 — Find new ticket files
# ---------------------------------------------------------------------------
cd "$REPO_ROOT"
NEW_FILES=()
while IFS= read -r line; do
  NEW_FILES+=("$line")
done < <(git ls-files --others --exclude-standard docs/TICKETS/TICKET-*.md 2>/dev/null || true)

if [ "${#NEW_FILES[@]}" -eq 0 ]; then
  echo "No new ticket files in docs/TICKETS/. Save .md files there and rerun."
  exit 0
fi

echo "Found ${#NEW_FILES[@]} new ticket file(s): ${NEW_FILES[*]}"

# ---------------------------------------------------------------------------
# Step 4 — Validate every ticket file before any side effects
# ---------------------------------------------------------------------------
declare -a VALID_FILES=()
declare -a VALID_IDS=()
declare -a VALID_TITLES=()
declare -a VALID_PRIORITIES=()
declare -a VALID_MILESTONES=()
validation_errors=0

for f in "${NEW_FILES[@]}"; do
  basename_f="$(basename "$f")"
  errors_for_file=()

  # Filename pattern check
  if ! [[ "$basename_f" =~ ^TICKET-[A-Z0-9-]+-[a-z0-9-]+\.md$ ]]; then
    errors_for_file+=("filename does not match TICKET-[A-Z0-9-]+-[a-z0-9-]+.md pattern")
  fi

  # Extract file-name prefix (e.g. TICKET-M5) — stop before first -lowercase segment
  filename_id="$(echo "$basename_f" | sed -nE 's/^(TICKET-[A-Z0-9-]+)-[a-z].*/\1/p')"
  if [ -z "$filename_id" ]; then
    errors_for_file+=("could not extract ticket ID from filename")
  fi

  # Read file content
  content="$(cat "$f")"

  # Heading check: first non-blank line must match
  first_line="$(echo "$content" | grep -m1 '.')"
  if ! [[ "$first_line" =~ ^#\ TICKET-([A-Z0-9-]+)\ —\ (.+)$ ]]; then
    errors_for_file+=("first non-blank line does not match '# TICKET-XXX — Title' format")
    heading_id=""
    heading_title=""
  else
    heading_id="${BASH_REMATCH[1]}"
    heading_title="${BASH_REMATCH[2]}"
  fi

  # ID consistency: heading ID must match filename prefix
  if [ -n "$filename_id" ] && [ -n "$heading_id" ] && [ "$filename_id" != "TICKET-$heading_id" ]; then
    errors_for_file+=("filename ID '$filename_id' does not match heading ID 'TICKET-$heading_id'")
  fi

  # Priority check — sed -nE works on both BSD and GNU
  priority="$(echo "$content" | sed -nE 's/.*\*\*Priority:\*\* (CRITICAL|HIGH|MEDIUM|LOW).*/\1/p' | head -1)"
  if [ -z "$priority" ]; then
    errors_for_file+=("missing or invalid **Priority:** field (must be CRITICAL|HIGH|MEDIUM|LOW)")
  fi

  # Milestone check
  milestone="$(echo "$content" | sed -nE 's/.*\*\*Milestone:\*\* (.+)$/\1/p' | head -1 | tr -d '\r')"
  if [ -z "$milestone" ]; then
    errors_for_file+=("missing **Milestone:** field")
  fi

  # Body size check (non-whitespace characters)
  nonws="$(echo "$content" | tr -d '[:space:]' | wc -c)"
  if [ "$nonws" -lt 500 ]; then
    errors_for_file+=("body has only $nonws non-whitespace characters (minimum 500; possible truncation)")
  fi

  if [ "${#errors_for_file[@]}" -gt 0 ]; then
    echo ""
    echo "Validation errors in $f:"
    for e in "${errors_for_file[@]}"; do
      echo "  - $e"
    done
    validation_errors=$((validation_errors + 1))
  else
    VALID_FILES+=("$f")
    VALID_IDS+=("TICKET-$heading_id")
    VALID_TITLES+=("$heading_title")
    VALID_PRIORITIES+=("$priority")
    VALID_MILESTONES+=("$milestone")
  fi
done

if [ "$validation_errors" -gt 0 ]; then
  echo ""
  echo "Aborting: $validation_errors file(s) failed validation. No GitHub or git side effects."
  exit 1
fi

echo ""
echo "All ${#VALID_FILES[@]} file(s) passed validation."

# ---------------------------------------------------------------------------
# Resolve board IDs via name lookup
# ---------------------------------------------------------------------------
echo "Resolving project board IDs..."
PROJECT_ID="$(gh project list --owner @me --format json | jq -r --argjson n "$PROJECT_NUMBER" '.projects[] | select(.number==$n) | .id')"
if [ -z "$PROJECT_ID" ]; then
  echo "Error: project #$PROJECT_NUMBER not found for @me. Check PROJECT_NUMBER in file.sh."
  exit 1
fi

STATUS_FIELD_ID="$(gh project field-list "$PROJECT_NUMBER" --owner @me --format json | jq -r '.fields[] | select(.name=="Status") | .id')"
BACKLOG_OPTION_ID="$(gh project field-list "$PROJECT_NUMBER" --owner @me --format json | jq -r '.fields[] | select(.name=="Status") | .options[] | select(.name=="Backlog") | .id')"

if [ -z "$STATUS_FIELD_ID" ] || [ -z "$BACKLOG_OPTION_ID" ]; then
  echo "Error: could not resolve Status field or Backlog option from board. Aborting."
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 5 — Create GitHub issues
# ---------------------------------------------------------------------------
declare -a CREATED_URLS=()
declare -a CREATED_NUMS=()
declare -a CREATED_IDS=()

echo ""
for i in "${!VALID_FILES[@]}"; do
  f="${VALID_FILES[$i]}"
  ticket_id="${VALID_IDS[$i]}"
  title="${VALID_TITLES[$i]}"
  # tr is POSIX; works on bash 3.2 (replaces bash-4+ ${var,,} case-conversion)
  priority_lower="$(echo "${VALID_PRIORITIES[$i]}" | tr '[:upper:]' '[:lower:]')"
  milestone="${VALID_MILESTONES[$i]}"

  echo "Creating issue for $ticket_id..."

  # Check if milestone exists (open or closed); auto-create if missing.
  # Use array to preserve multi-word milestone names like "Investment Panel".
  milestone_args=()
  ms_state="$(gh api 'repos/{owner}/{repo}/milestones?state=all' --jq ".[] | select(.title==\"$milestone\") | .state" 2>/dev/null | head -1 || true)"
  if [ "$ms_state" = "open" ]; then
    milestone_args=(--milestone "$milestone")
  elif [ "$ms_state" = "closed" ]; then
    echo "  Warning: milestone '$milestone' is closed. Filing without milestone."
  else
    # Doesn't exist — create it, then attach.
    echo "  Milestone '$milestone' not found. Creating it..."
    if gh api 'repos/{owner}/{repo}/milestones' -f title="$milestone" >/dev/null 2>&1; then
      echo "  Created milestone '$milestone'."
      milestone_args=(--milestone "$milestone")
    else
      echo "  Warning: failed to create milestone '$milestone'. Filing without milestone."
    fi
  fi

  issue_url="$(gh issue create \
    --title "$ticket_id — $title" \
    --body-file "$f" \
    --label "$priority_lower" \
    "${milestone_args[@]}")"

  # sed -nE works on both BSD and GNU grep (replaces grep -oP '\d+$')
  issue_num="$(echo "$issue_url" | sed -nE 's|.*/([0-9]+)$|\1|p')"
  echo "  Created: $issue_url (issue #$issue_num)"

  CREATED_URLS+=("$issue_url")
  CREATED_NUMS+=("$issue_num")
  CREATED_IDS+=("$ticket_id")
done

# ---------------------------------------------------------------------------
# Step 6 — Add each issue to the project board (Backlog)
# ---------------------------------------------------------------------------
declare -a ITEM_IDS=()
echo ""
for i in "${!CREATED_URLS[@]}"; do
  issue_url="${CREATED_URLS[$i]}"
  ticket_id="${CREATED_IDS[$i]}"
  issue_num="${CREATED_NUMS[$i]}"

  echo "Adding $ticket_id (issue #$issue_num) to board..."

  item_id="$(gh project item-add "$PROJECT_NUMBER" --owner @me --url "$issue_url" --format json | jq -r '.id')"
  if [ -z "$item_id" ]; then
    echo "  Warning: item-add failed for $issue_url. Add manually:"
    echo "    gh project item-add $PROJECT_NUMBER --owner @me --url $issue_url"
    ITEM_IDS+=("")
    continue
  fi

  gh project item-edit \
    --project-id "$PROJECT_ID" \
    --id "$item_id" \
    --field-id "$STATUS_FIELD_ID" \
    --single-select-option-id "$BACKLOG_OPTION_ID" \
    --format json > /dev/null

  echo "  Added to Backlog (item $item_id)"
  ITEM_IDS+=("$item_id")
done

# ---------------------------------------------------------------------------
# Step 7 — Priority-band ordering in Backlog (banded-prepend per ADR-010)
# ---------------------------------------------------------------------------
# Each new item is placed at the top of its priority band: after the last
# existing Backlog item of strictly higher priority (or at the very top of
# Backlog if no higher-priority item exists). The query is re-run before each
# insertion so the algorithm sees the post-state of earlier insertions in the
# same batch. Failures are non-fatal: a warning is printed and the item stays
# wherever gh project item-add placed it (Vivek can drag to fix).

_priority_rank() {
  case "$1" in
    CRITICAL) echo 4 ;;
    HIGH)     echo 3 ;;
    MEDIUM)   echo 2 ;;
    LOW)      echo 1 ;;
    *)        echo 0 ;;
  esac
}

# Shared GraphQL query: fetch all project items with Status + priority labels.
# shellcheck disable=SC2016
_BACKLOG_QUERY='query($projectId: ID!) {
  node(id: $projectId) {
    ... on ProjectV2 {
      items(first: 100) {
        nodes {
          id
          fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          content {
            ... on Issue {
              labels(first: 10) { nodes { name } }
            }
          }
        }
      }
    }
  }
}'

declare -a ITEM_BACKLOG_RANKS=()

echo ""
echo "Setting priority-band positions in Backlog..."
for i in "${!ITEM_IDS[@]}"; do
  item_id="${ITEM_IDS[$i]}"
  priority="${VALID_PRIORITIES[$i]}"
  ticket_id="${VALID_IDS[$i]}"

  if [ -z "$item_id" ]; then
    ITEM_BACKLOG_RANKS+=("?")
    echo "  $ticket_id: skipping reorder (item was not added to board)"
    continue
  fi

  new_rank="$(_priority_rank "$priority")"

  # Re-query current Backlog before each insertion.
  backlog_json="$(gh api graphql \
    -f query="$_BACKLOG_QUERY" \
    -f projectId="$PROJECT_ID" 2>/dev/null || true)"

  if [ -z "$backlog_json" ]; then
    ITEM_BACKLOG_RANKS+=("?")
    echo "  Warning: could not query board for $ticket_id — fix manually by dragging on the board."
    continue
  fi

  # Find the last Backlog item with strictly higher priority rank.
  # Exclude the new item itself (it is already in Backlog after Step 6).
  anchor_id="$(printf '%s' "$backlog_json" | jq -r \
    --argjson new_rank "$new_rank" \
    --arg item_id "$item_id" \
    '[
      .data.node.items.nodes[] |
      select(.fieldValueByName.name == "Backlog") |
      select(.id != $item_id) |
      {
        id: .id,
        rank: (
          [
            (.content.labels?.nodes // [])[] |
            .name | ascii_downcase |
            if . == "critical" then 4
            elif . == "high" then 3
            elif . == "medium" then 2
            elif . == "low" then 1
            else empty
            end
          ] | max // 0
        )
      } |
      select(.rank > $new_rank)
    ] | last | .id // empty')"

  if [ -z "$anchor_id" ]; then
    # No higher-priority item — place at top of Backlog.
    # shellcheck disable=SC2016
    if ! gh api graphql \
      -f query='mutation($projectId: ID!, $itemId: ID!) {
        updateProjectV2ItemPosition(input: { projectId: $projectId, itemId: $itemId }) {
          items(first: 1) { nodes { id } }
        }
      }' \
      -f projectId="$PROJECT_ID" \
      -f itemId="$item_id" > /dev/null 2>&1; then
      ITEM_BACKLOG_RANKS+=("?")
      echo "  Warning: could not reorder $ticket_id — fix manually by dragging on the board."
      continue
    fi
  else
    # Place directly after the last higher-priority item (top of this band).
    # shellcheck disable=SC2016
    if ! gh api graphql \
      -f query='mutation($projectId: ID!, $itemId: ID!, $afterId: ID!) {
        updateProjectV2ItemPosition(input: { projectId: $projectId, itemId: $itemId, afterId: $afterId }) {
          items(first: 1) { nodes { id } }
        }
      }' \
      -f projectId="$PROJECT_ID" \
      -f itemId="$item_id" \
      -f afterId="$anchor_id" > /dev/null 2>&1; then
      ITEM_BACKLOG_RANKS+=("?")
      echo "  Warning: could not reorder $ticket_id — fix manually by dragging on the board."
      continue
    fi
  fi

  echo "  Positioned $ticket_id at top of $priority band."
  ITEM_BACKLOG_RANKS+=("pending")
done

# Compute final 1-indexed Backlog ranks from a single post-mutation query.
final_backlog_json="$(gh api graphql \
  -f query="$_BACKLOG_QUERY" \
  -f projectId="$PROJECT_ID" 2>/dev/null || true)"

if [ -n "$final_backlog_json" ]; then
  for i in "${!ITEM_IDS[@]}"; do
    if [ "${ITEM_BACKLOG_RANKS[$i]:-}" = "pending" ]; then
      item_id="${ITEM_IDS[$i]}"
      rank="$(printf '%s' "$final_backlog_json" | jq -r \
        --arg iid "$item_id" \
        '[.data.node.items.nodes[] | select(.fieldValueByName.name == "Backlog") | .id] |
         (index($iid) // -1) |
         if . >= 0 then (. + 1 | tostring) else "?" end')"
      ITEM_BACKLOG_RANKS[i]="$rank"
    fi
  done
fi

# ---------------------------------------------------------------------------
# Step 8 — Strip decorative Status lines, commit, and push
# ---------------------------------------------------------------------------
echo ""
echo "Committing ticket files..."

# Strip any "**Status:** <value>" lines before committing.
# METHODOLOGY.md §ticket-lifecycle states there is no DRAFT/QUEUED status after filing.
# Use a temp-file swap for POSIX portability (BSD sed -i requires an extension arg).
for f in "${VALID_FILES[@]}"; do
  tmp_f="${f}.strip.tmp"
  sed '/^\*\*Status:\*\*/d' "$f" > "$tmp_f" && mv "$tmp_f" "$f"
done

# Build commit message: "docs: file TICKET-XXX[, TICKET-YYY, ...]"
ids_csv="$(IFS=', '; echo "${CREATED_IDS[*]}")"
commit_msg="docs: file $ids_csv"

git add docs/TICKETS/TICKET-*.md
git commit -m "$commit_msg"

echo "Pushing..."
if ! git push origin main; then
  echo ""
  echo "Warning: git push failed. Issues and board items were already created."
  echo "To recover:"
  echo "  git pull --rebase origin main && git push origin main"
  exit 1
fi

pushed_sha="$(git rev-parse HEAD)"

# ---------------------------------------------------------------------------
# Step 9 — Print summary
# ---------------------------------------------------------------------------
echo ""
echo "Filed ${#CREATED_IDS[@]} ticket(s):"
for i in "${!CREATED_IDS[@]}"; do
  title_short="${VALID_TITLES[$i]}"
  if [ "${#title_short}" -gt 50 ]; then
    title_short="${title_short:0:47}..."
  fi
  backlog_rank="${ITEM_BACKLOG_RANKS[$i]:-?}"
  priority="${VALID_PRIORITIES[$i]}"
  echo "  ${CREATED_IDS[$i]:-unknown}  — $title_short -> issue #${CREATED_NUMS[$i]}, Backlog #$backlog_rank ($priority)"
done
echo "Commit pushed: $pushed_sha"
