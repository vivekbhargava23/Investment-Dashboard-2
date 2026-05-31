#!/usr/bin/env bash
# Run a command inside a worktree with the investment-dashboard conda env active.
# Usage:   bash tools/run.sh <worktree-slug> <command...>
# Example: bash tools/run.sh c3 pytest tests/unit
set -e
slug="$1"; shift
repo_parent="$(cd "$(dirname "$0")/../.." && pwd)"
target="$repo_parent/Investment-Dashboard-2-$slug"
[ -d "$target" ] || { echo "No such worktree: $target" >&2; exit 1; }
cd "$target"
# shellcheck source=/dev/null
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate investment-dashboard
exec "$@"
