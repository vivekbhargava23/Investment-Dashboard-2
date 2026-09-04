#!/usr/bin/env bash
# Drag the project board card stack into the same order `next.sh` ranks.

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

python3 tools/ticket_workflow.py reorder "$@"
