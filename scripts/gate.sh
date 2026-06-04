#!/usr/bin/env bash
# gate.sh — the full pre-commit validation chain (ADR: single static entrypoint).
#
# Why this exists: the old chained command embedded `$(conda info --base)` command
# substitution and multiple `&&` steps. Claude's permission system flags command
# substitution / compound commands for manual approval regardless of the allow-list,
# so every gate run triggered a prompt. Collapsing the chain into one static script
# means sessions invoke `bash scripts/gate.sh`, which matches a single allow rule.
#
# Runs ALL checks (does not fail-fast) so you see every failure in one pass, then
# exits non-zero if any check failed. This is the Step 7 gate from AGENTS.md.
#
# Usage:  bash scripts/gate.sh
set -uo pipefail

ENV_NAME="investment-dashboard"

# --- activate conda env ---------------------------------------------------------
CONDA_BASE="$(conda info --base 2>/dev/null)"
if [ -z "${CONDA_BASE}" ]; then
  echo "✗ conda not found on PATH — cannot activate '${ENV_NAME}'." >&2
  exit 1
fi
# shellcheck disable=SC1091
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${ENV_NAME}" || { echo "✗ failed to activate conda env '${ENV_NAME}'." >&2; exit 1; }

# --- run each check, collecting failures ----------------------------------------
failed=()

run_check() {
  local name="$1"; shift
  echo ""
  echo "━━━ ${name} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  if "$@"; then
    echo "✓ ${name} passed"
  else
    echo "✗ ${name} FAILED"
    failed+=("${name}")
  fi
}

run_check "pytest"       pytest
run_check "ruff"         ruff check .
run_check "mypy"         mypy app/
run_check "lint-imports" lint-imports

# --- summary --------------------------------------------------------------------
echo ""
echo "════════════════════════════════════════════════════════"
if [ ${#failed[@]} -eq 0 ]; then
  echo "✓ GATE PASSED — all checks green."
  exit 0
else
  echo "✗ GATE FAILED — ${#failed[@]} check(s) failed: ${failed[*]}"
  echo "  Do not commit. See 'Stop conditions' in AGENTS.md."
  exit 1
fi
