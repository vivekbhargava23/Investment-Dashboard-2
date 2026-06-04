#!/usr/bin/env bash
# Start an implementation ticket: sync main, branch, and mark board In progress.

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

python3 tools/ticket_workflow.py start "$@"
