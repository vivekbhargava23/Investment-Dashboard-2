#!/usr/bin/env bash
# Move ticket specs the board marks Done into docs/TICKETS/DONE/.

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

python3 tools/ticket_workflow.py archive "$@"
