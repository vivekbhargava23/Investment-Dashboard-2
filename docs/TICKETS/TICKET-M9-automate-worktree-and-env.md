# TICKET-M9 — Automate worktree creation and conda env activation in the agent ritual

**Status:** QUEUED
**Priority:** MEDIUM
**Estimated session length:** 1 hr
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Milestone:** Workflow
**Dependencies:** None — independent.

---

## Problem

Per ADR-011: parallel agent workflows require git worktrees + per-shell conda env activation. Today both are manual. Vivek's mental load on starting a session is:

1. `cd ~/Desktop/Apps/Investment-Dashboard-2`
2. `git worktree add ../Investment-Dashboard-2-h1 -b ticket-h1-classification`
3. `cd ../Investment-Dashboard-2-h1`
4. `conda activate investment-dashboard`
5. `claude` → `implement TICKET-H1`

The target is:

1. `cd ~/Desktop/Apps/Investment-Dashboard-2`
2. `claude` → `implement TICKET-H1`

The four omitted steps move into the agent's `AGENTS.md` Step 5 ritual.

## Solution

### Step 1 — Amend `AGENTS.md` Step 5

Replace the current Step 5 ("Branch and mark in-progress") with a worktree-aware version:

```markdown
### Step 5 — Worktree, branch, and mark in-progress

If the current working directory is the **main checkout** (i.e. `git rev-parse --abbrev-ref HEAD` is `main`):

```bash
slug="ticket-$(echo TICKET-XXX | tr '[:upper:]' '[:lower:]' | sed -E 's/ticket-//')-short-name"
worktree_path="../$(basename $(git rev-parse --show-toplevel))-$(echo TICKET-XXX | tr '[:upper:]' '[:lower:]')"
git worktree add "$worktree_path" -b "$slug"
cd "$worktree_path"
```

If already inside a worktree (HEAD != main), reuse it — just confirm branch name matches the ticket, no creation needed.

Then, as today: update ticket file Status decoratively and move the board item to `In progress` via the API call shown below.
```

The board-API call stays unchanged.

### Step 2 — Env activation pattern in AGENTS.md

Add a short subsection under Step 7 (Gate check):

```markdown
### Conda env activation

All shell calls that require Python (pytest, ruff, mypy, lint-imports, streamlit) prefix with:

```bash
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate investment-dashboard && <command>
```

Equivalent on systems with mamba: substitute `mamba` for `conda`.

The agent never relies on the outer shell having conda activated.
```

### Step 3 — Cleanup script

`tools/cleanup-worktrees.sh`:

```bash
#!/usr/bin/env bash
# Removes local worktrees whose upstream branches no longer exist.
# Safe to run any time. Idempotent.
set -euo pipefail
git fetch --prune origin
git worktree list --porcelain | awk '/^worktree / {wt=$2} /^branch / {br=$2; print wt"\t"br}' | \
  while IFS=$'\t' read -r wt br; do
    [ "$wt" = "$(git rev-parse --show-toplevel)" ] && continue  # never touch main checkout
    branch_name="${br#refs/heads/}"
    if ! git show-ref --verify --quiet "refs/remotes/origin/$branch_name"; then
      echo "Removing worktree $wt (branch $branch_name gone upstream)"
      git worktree remove --force "$wt"
    fi
  done
git worktree prune
```

Mark executable. Document in `tools/README.md` (one line).

### Step 4 — Update `docs/VIVEK.md`

Replace Section 3 ("Implementing a ticket") with the new minimal flow:

```markdown
## Section 3 — Implementing a ticket

1. `cd ~/Desktop/Apps/Investment-Dashboard-2`  (or any existing ticket worktree)
2. `claude` (or `codex`, `aider`, `gemini`)
3. Say `next` to see the menu, or `implement TICKET-XXX` to jump in.
4. PR shows up. Review and merge.

You no longer create worktrees or activate conda by hand — the agent does both. To clean up local worktrees of merged tickets: `bash tools/cleanup-worktrees.sh` (safe to run any time; safe to run never).

To start three tickets in parallel: open three terminals, run steps 1–3 in each, pick different ticket IDs in each. Three PRs come back.
```

### Step 5 — Flip ADR-011 to Accepted in the same PR

Update `docs/DECISIONS/ADR-011-parallel-agent-workflow.md` Status from `Proposed` to `Accepted` with today's date.

## Acceptance criteria

- [ ] `AGENTS.md` Step 5 updated with worktree-aware branching.
- [ ] `AGENTS.md` Step 7 updated with the conda env activation pattern.
- [ ] `tools/cleanup-worktrees.sh` exists, is executable, removes orphaned worktrees, never touches the main checkout.
- [ ] `tools/README.md` mentions the cleanup script in one line.
- [ ] `docs/VIVEK.md` Section 3 reflects the new two-step flow.
- [ ] ADR-011 Status is `Accepted`.
- [ ] All tests pass; ruff / mypy / lint-imports clean (Python code is unaffected).
- [ ] No regressions in existing ritual: running `implement TICKET-XXX` from a non-main worktree still works (reuses the worktree).

### Manual smoke

1. From the main checkout, start `claude` and say `implement TICKET-R1`. Confirm:
   - A new worktree `../Investment-Dashboard-2-r1` is created.
   - Branch `ticket-r1-...` is checked out there.
   - `pytest` runs with conda env activated, no manual `conda activate` from Vivek.
2. From the new worktree, say `address PR review comments on TICKET-R1`. Confirm: no new worktree is created; agent works in place.
3. Run `bash tools/cleanup-worktrees.sh` after the PR merges. Confirm: the merged ticket's worktree is removed; main checkout is untouched.
4. Open three terminals from the main checkout. Start `claude` in each with three different ticket IDs (H1, C2, M8). Confirm: three worktrees, three branches, three PRs.

## Out of scope

- direnv integration for auto-activating env on `cd`. Considered; rejected as adding a dependency. Per-shell-call activation is fine.
- A wrapper command like `ticket h1` that combines `claude` + ticket pick. Not needed if the in-agent `implement TICKET-H1` handles the rest.
- Race protection on `next` when two agents call it simultaneously. Flagged in ADR-011 as a follow-up; addressed separately if it bites.
- Changes to `tools/file.sh`. Worktree automation is implementation-side, not filing-side.
- Cross-platform support beyond macOS. Vivek's setup is macOS-only.

## Notes / assumptions

- Assumes `git` 2.5+ (worktree support — ships with macOS by default).
- Assumes `conda` is installed and `investment-dashboard` env exists (it does — per README setup).
- Assumes the agent CLI can `cd` and persist the change for subsequent shell calls within the same session. Claude Code, Codex, and Aider all support this. Verify per CLI; if any CLI loses cwd between calls, document the workaround in `docs/LEARNING-GOALS.md`.
- The worktree-naming convention (`<repo>-<ticket-id-lower>`) is opinionated; if Vivek prefers a different shape, the helper recipe in Step 1 is one regex change.
- The cleanup script uses `--force` because branches gone upstream are by definition not needed locally. If a worktree has uncommitted changes, `--force` would discard them — that should never happen for a merged ticket, but document this risk in `tools/README.md`.
- Per `LEARNING-GOALS.md`'s "automation-first" rule, any new manual step that surfaces during implementation should be flagged for further automation rather than silently absorbed.
