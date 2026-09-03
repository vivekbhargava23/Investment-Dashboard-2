#!/usr/bin/env bash
# Run the complete local gate in the project conda environment.

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if ! command -v conda >/dev/null 2>&1; then
  echo "Error: conda is not on PATH." >&2
  exit 1
fi

CONDA_BASE="$(conda info --base)"
# shellcheck source=/dev/null
. "$CONDA_BASE/etc/profile.d/conda.sh"

# Conda environments are installation-specific. Resolve the full prefix so this
# works when the active base is Miniforge but the project env belongs to Anaconda.
ENV_NAME="investment-dashboard"
ENV_PREFIX="$(conda env list | awk -v suffix="/$ENV_NAME" \
  '$NF ~ (suffix "$") { print $NF; exit }')"

if [ -z "$ENV_PREFIX" ]; then
  echo "Error: conda environment '$ENV_NAME' was not found." >&2
  echo "Run ./run_dashboard.command once to create it." >&2
  exit 1
fi

conda activate "$ENV_PREFIX"

run_check() {
  check_name="$1"
  shift
  echo "==> $check_name"
  if ! "$@"; then
    echo "Error: $check_name failed." >&2
    exit 1
  fi
}

run_check "pytest" pytest
run_check "ruff check ." ruff check .
run_check "mypy app/" mypy app/
run_check "lint-imports" lint-imports

echo "Gate passed."
