#!/usr/bin/env bash
# Idempotent GitHub label + milestone setup for this repo.
# Run once (or re-run safely) to create all expected labels and milestones.
# Uses `gh` CLI — must be authenticated before running.
set -euo pipefail

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
echo "Setting up GitHub labels and milestones for: $REPO"

# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------
create_label() {
  local name="$1" color="$2" description="$3"
  gh label create "$name" --color "$color" --description "$description" --force 2>/dev/null || true
}

echo "Creating lifecycle labels..."
create_label "queued"      "0075ca" "Spec complete; waiting to be picked up"
create_label "in-progress" "e4e669" "Branch open, work happening"

echo "Creating priority labels..."
create_label "critical" "d93f0b" "Data correctness, security, or blocks active work"
create_label "high"     "e99695" "Core feature for the current Milestone"
create_label "medium"   "fbca04" "Polish or quality-of-life on shipped work"
create_label "low"      "c5def5" "Speculative or contingent on a design decision"

echo "Creating coordination labels..."
create_label "next-up"    "0e8a16" "Exactly one issue carries this at a time — next to implement"
create_label "blocked"    "b60205" "Blocked by an external dependency or decision"
create_label "superseded" "cccccc" "Replaced by a later ticket"

echo "Labels done."

# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------
create_milestone() {
  local title="$1" state="$2" description="$3"
  # gh api creates if not exists; safe to re-run (409 Conflict = already exists)
  existing=$(gh api "repos/$REPO/milestones?state=all" --jq ".[] | select(.title == \"$title\") | .number" 2>/dev/null || true)
  if [ -z "$existing" ]; then
    number=$(gh api "repos/$REPO/milestones" \
      --method POST \
      --field title="$title" \
      --field description="$description" \
      --field state=open \
      --jq '.number')
    echo "  Created milestone '$title' (#$number)"
    if [ "$state" = "closed" ]; then
      gh api "repos/$REPO/milestones/$number" --method PATCH --field state=closed > /dev/null
      echo "  Closed milestone '$title'"
    fi
  else
    echo "  Milestone '$title' already exists (#$existing) — skipping"
  fi
}

echo "Creating milestones..."
create_milestone "Foundation"       "closed" "Data model, FIFO, repository"
create_milestone "UI core"          "closed" "Shell, Live Overview, Manage Portfolio"
create_milestone "Tax engine"       "closed" "Engine, dashboard, simulator"
create_milestone "Charts & research" "closed" "Chart service, Research page"
create_milestone "Analytics & Risk" "closed" "Analytics page tabs"
create_milestone "UI polish"        "closed" "Visual polish"
create_milestone "Workflow & tooling" "open" "Workflow vocabulary, GitHub Issues integration, tooling scripts"
create_milestone "Investment Panel" "open"   "Schema-first panel framework (pending design)"

echo "Milestones done."

echo ""
echo "Verification:"
echo "  gh label list"
echo "  gh api repos/$REPO/milestones?state=all --jq '.[].title'"
