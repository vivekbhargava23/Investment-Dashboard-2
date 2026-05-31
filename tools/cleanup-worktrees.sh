#!/usr/bin/env bash
# Removes local worktrees whose upstream branches no longer exist.
# Safe to run any time. Idempotent.
# WARNING: uses --force, which discards any uncommitted changes in the worktree.
# For merged tickets this is safe; a worktree with uncommitted changes should never happen.
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
