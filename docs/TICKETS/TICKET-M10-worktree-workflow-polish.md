# TICKET-M10 — Worktree workflow polish (shared data + auto-prune merged)

**Status:** QUEUED
**Priority:** HIGH
**Estimated session length:** 60 min
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Milestone:** Workflow
**Dependencies:** TICKET-M9 (worktree automation must merge first; this extends it).

---

## Problem

ADR-011 + TICKET-M9 automated worktree creation, but day-one usage on 2026-05-31 surfaced two papercuts:

### Papercut A — Worktrees don't share runtime data

Each worktree gets its own copy of `data/` — the runtime directory holding `portfolio.json`, `isin_map.json`, `tax_profile.json`, `nav_snapshots.json`, `ticker_cache.json`, `fx_cache/`, `companies/`, and the latest CSV. Observed:

- Main checkout's Streamlit upload writes to main's `data/portfolio.json`.
- A parallel C2 worktree's Streamlit shows zero stocks because it reads its own (stale, committed) `data/portfolio.json`.
- Vivek has to re-upload the CSV in every worktree.

For runtime user state (the portfolio, the tax profile, the ISIN map), there is one truth across all worktrees, not one per branch.

### Papercut B — Merged worktrees pile up on disk

`tools/cleanup-worktrees.sh` (from M9) only removes a worktree when its **upstream** branch is gone. GitHub merges leave the branch on origin by default, so the script never fires for the common case. Observed:

- `~/Desktop/Apps/Investment-Dashboard-2-c2/` (TICKET-C2 — merged via PR #117)
- `~/Desktop/Apps/Investment-Dashboard-2-r5/` (TICKET-R5 — merged via PR #118)

Both are marked `prunable` by git but still sit on disk. After a few weeks of tickets this becomes a Desktop full of `Investment-Dashboard-2-<ticket>/` directories all pointing at merged code.

## Solution

Both fixes live in the M9 ritual + the cleanup script. One ticket, one PR.

### Part A — Symlink `data/` (and `.env`) into every new worktree

Amend the worktree creation step (introduced in M9) so the agent's Step 5 grows two lines:

```bash
# After: git worktree add "$worktree_path" -b "$slug"
# And before: cd "$worktree_path"
main_data="$(git rev-parse --show-toplevel)/data"
ln -sfn "$main_data" "$worktree_path/data"

# Same for .env if present (gitignored secrets)
[ -f "$(git rev-parse --show-toplevel)/.env" ] && \
  ln -sfn "$(git rev-parse --show-toplevel)/.env" "$worktree_path/.env"
```

`docs/VIVEK.md` Section 3 gets one line appended:

> All worktrees share the main checkout's `data/` directory automatically (per ADR-011). Upload the CSV once in main; every worktree sees it. The agent handles the symlinking.

### Part B — Auto-prune worktrees whose branch is merged into main

Rewrite `tools/cleanup-worktrees.sh` so it removes a worktree if **any** of these hold:

1. The upstream branch is gone (existing behaviour — kept).
2. The branch is fully merged into `origin/main` (`git merge-base --is-ancestor`).
3. The branch's tip tree-hash appears in the recent history of `origin/main` (catches squash-merges, which GitHub does by default).

```bash
#!/usr/bin/env bash
set -euo pipefail
git fetch --prune origin

MAIN_REPO="$(git rev-parse --show-toplevel)"
MERGE_BASE_BRANCH="${1:-origin/main}"

git worktree list --porcelain \
  | awk '/^worktree / {wt=$2} /^branch / {br=$2; print wt"\t"br}' \
  | while IFS=$'\t' read -r wt br; do
      [ "$wt" = "$MAIN_REPO" ] && continue
      branch_name="${br#refs/heads/}"

      # Case 1: upstream gone
      if ! git show-ref --verify --quiet "refs/remotes/origin/$branch_name"; then
        echo "Removing $wt — origin/$branch_name is gone"
        git worktree remove --force "$wt"; continue
      fi

      # Case 2: branch fully merged (ancestor of main)
      if git merge-base --is-ancestor "refs/heads/$branch_name" "refs/remotes/$MERGE_BASE_BRANCH"; then
        echo "Removing $wt — $branch_name is merged into $MERGE_BASE_BRANCH"
        git worktree remove --force "$wt"
        git branch -D "$branch_name" 2>/dev/null || true
        continue
      fi

      # Case 3: squash-merged (tree-hash match in recent main)
      tip_tree="$(git rev-parse "$branch_name^{tree}")"
      if git log "$MERGE_BASE_BRANCH" --format='%T' -n 50 | grep -qx "$tip_tree"; then
        echo "Removing $wt — $branch_name appears squash-merged"
        git worktree remove --force "$wt"
        git branch -D "$branch_name" 2>/dev/null || true
        continue
      fi
    done

git worktree prune
```

### Part C — Wire cleanup into the agent ritual

In `AGENTS.md` (the step that creates the worktree), prepend:

```bash
bash tools/cleanup-worktrees.sh || true
```

So every new ticket sweeps out merged ones before adding a new folder. Manual `bash tools/cleanup-worktrees.sh` from Vivek's terminal still works.

### Part D — One-time fix-up for existing worktrees

Existing worktrees (`Investment-Dashboard-2-c2`, `Investment-Dashboard-2-r5`) won't have the `data/` symlink. Implementer's call:

- Easy path: document `rm -rf data && ln -s ../Investment-Dashboard-2/data data` in the session log.
- Nicer path: `tools/cleanup-worktrees.sh --fixup` walks every surviving worktree and creates missing symlinks. Skip if it pushes the ticket over 60 min.

(The c2 and r5 worktrees will be removed by Part B on first run, making fix-up moot for those two. Fix-up only matters for any future worktree that survives the prune.)

## Acceptance criteria

### Part A (shared data)
- [ ] Agent ritual (M9 step) creates a `data/` symlink from new worktree → main checkout's `data/`.
- [ ] Same treatment for `.env` if present.
- [ ] `docs/VIVEK.md` Section 3 includes the one-line note.
- [ ] Manual smoke: create a worktree → upload CSV in main → confirm worktree's Streamlit immediately shows the data without re-upload.

### Part B (auto-prune)
- [ ] `tools/cleanup-worktrees.sh` removes worktrees whose branch is fully merged into `origin/main`, including squash-merged.
- [ ] Script never touches the main checkout (existing guard preserved).
- [ ] Worktrees with unpushed commits not on main survive the run.
- [ ] Manual smoke: with current state (c2 + r5 worktrees, both merged), one run removes both folders. Main untouched.

### Part C (ritual integration)
- [ ] `AGENTS.md` calls `tools/cleanup-worktrees.sh` at the start of the worktree-creation step.

### Universal
- [ ] All tests pass; ruff / mypy / lint-imports clean.

## Out of scope

- Moving `data/` out of the repo entirely (e.g. `~/.investment-dashboard/data/`). Architectural question worth its own ADR.
- Making `data/portfolio.json` and other state files untracked. Same — separate ADR.
- A locking mechanism for concurrent writes from two Streamlits + an agent. Single-user setup makes contention rare; defer.
- Cross-machine sync of `data/`. Not in scope.
- A GUI / dashboard for managing worktrees. Bash is enough.
- Stale-worktree warnings (e.g. "branch not touched in 14 days"). Useful, but not now.

## Notes / assumptions

- macOS / Linux symlinks. Windows would need junction points; out of scope per M9.
- `git worktree remove --force` is safe for merged worktrees — the commits live on main now. The `--force` flag is required because git refuses to remove a worktree with uncommitted changes by default; for merged work there are no uncommitted changes worth keeping.
- Squash-merge tree-hash check covers GitHub's default. Rebase-and-merge is covered by `is-ancestor`.
- Per `LEARNING-GOALS.md` automation-first rule: this ticket exists because Vivek hit both papercuts manually once. The fix lives in the agent ritual; he won't see either again.
