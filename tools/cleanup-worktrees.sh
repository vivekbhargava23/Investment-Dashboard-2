#!/usr/bin/env bash
# Removes local worktrees whose branch is:
#   1. Gone upstream AND was tracking a remote (merged + branch deleted by GitHub)
#   2. Fully merged into origin/main (standard merge or rebase-and-merge)
#   3. Squash-merged into origin/main (tree-hash match in recent main history)
# Never touches the main checkout.
# Preserves worktrees whose branch has never been pushed (no upstream tracking config).
# Safe to run any time. Idempotent.
# WARNING: uses --force, which discards uncommitted changes in the worktree.
# For merged tickets this is safe; worktrees with unmerged work survive untouched.
set -euo pipefail

MERGE_BASE_BRANCH="${1:-origin/main}"

git fetch --prune origin

# The shared .git directory lives in the primary checkout; go one level up to find it.
# This resolves correctly whether called from the main checkout or from a worktree.
MAIN_REPO="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"

git worktree list --porcelain \
  | awk '/^worktree / {wt=$2} /^branch / {br=$2; print wt"\t"br}' \
  | while IFS=$'\t' read -r wt br; do
      [ "$wt" = "$MAIN_REPO" ] && continue

      branch_name="${br#refs/heads/}"

      # Case 1: upstream is gone — only remove if the branch was previously tracking a
      # remote (i.e. it was pushed). A brand-new branch with no upstream config is kept.
      if ! git show-ref --verify --quiet "refs/remotes/origin/$branch_name"; then
        if ! git config --get "branch.$branch_name.remote" > /dev/null 2>&1; then
          echo "Keeping $wt — $branch_name has no upstream (new branch, never pushed)"
          continue
        fi
        echo "Removing $wt — origin/$branch_name is gone (was merged and deleted)"
        git worktree remove --force "$wt"
        git branch -D "$branch_name" 2>/dev/null || true
        continue
      fi

      # Case 2: branch tip is an ancestor of main (standard merge / rebase-and-merge)
      if git merge-base --is-ancestor "refs/heads/$branch_name" "refs/remotes/$MERGE_BASE_BRANCH" 2>/dev/null; then
        echo "Removing $wt — $branch_name is merged into $MERGE_BASE_BRANCH"
        git worktree remove --force "$wt"
        git branch -D "$branch_name" 2>/dev/null || true
        continue
      fi

      # Case 3: squash-merged — branch tip tree-hash appears in recent main history
      tip_tree="$(git rev-parse "${branch_name}^{tree}" 2>/dev/null)" || continue
      if git log "$MERGE_BASE_BRANCH" --format='%T' -n 50 | grep -qx "$tip_tree"; then
        echo "Removing $wt — $branch_name appears squash-merged into $MERGE_BASE_BRANCH"
        git worktree remove --force "$wt"
        git branch -D "$branch_name" 2>/dev/null || true
        continue
      fi

      echo "Keeping $wt — $branch_name not yet merged"
    done

git worktree prune
echo "Worktree cleanup complete."
