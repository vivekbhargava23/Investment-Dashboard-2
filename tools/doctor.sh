#!/usr/bin/env bash
# Non-mutating workflow diagnostics for local repo and project-board state.

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

python3 tools/ticket_workflow.py doctor "$@"
