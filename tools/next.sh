#!/usr/bin/env bash
# Print the ranked next-ticket menu from GitHub Projects.

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

python3 tools/ticket_workflow.py next "$@"
