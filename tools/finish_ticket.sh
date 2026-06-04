#!/usr/bin/env bash
# Finish an implementation ticket: gate, push, move board In review, and open a PR.

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

bash tools/gate.sh
python3 tools/ticket_workflow.py finish "$@"
