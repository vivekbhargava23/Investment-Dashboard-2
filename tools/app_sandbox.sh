#!/usr/bin/env bash
# app_sandbox.sh — launch the Streamlit app against an ISOLATED throwaway data dir,
# so visual/manual verification never touches the user's real data/portfolio.json.
#
# Usage:
#   bash tools/app_sandbox.sh [PORT]
#
# Prints (to stderr) the sandbox data dir and the URL, then exec's streamlit in the
# foreground. The caller is expected to background it (e.g. run_in_background) and
# poll the URL. Stop it by killing the PID listening on PORT.
#
# Why a sandbox: the Import Workbench writes to isin_map.json on Ignore/Save and to
# portfolio.json on Apply. Pointing every settings path at a temp dir means a demo
# run can click freely without mutating real data. Every path below maps to a
# Settings field in app/config.py (pydantic-settings reads UPPERCASE env vars).
set -euo pipefail

PORT="${1:-8599}"

DATA_DIR="$(mktemp -d "${TMPDIR:-/tmp}/app_sandbox.XXXXXX")/data"
mkdir -p "$DATA_DIR/backups" "$DATA_DIR/fx_cache"
# Empty-but-valid seeds. portfolio.json is left ABSENT on purpose: the JSON repo
# returns [] for a missing file, but raises on an empty/zero-byte or version-less file.
printf '{"version": 2, "entries": {}}' > "$DATA_DIR/isin_map.json"
printf '[]' > "$DATA_DIR/import_log.json"

export PORTFOLIO_JSON_PATH="$DATA_DIR/portfolio.json"
export TAX_PROFILE_JSON_PATH="$DATA_DIR/tax_profile.json"
export TICKER_CACHE_JSON_PATH="$DATA_DIR/ticker_cache.json"
export NAV_SNAPSHOTS_JSON_PATH="$DATA_DIR/nav_snapshots.json"
export ISIN_MAP_JSON_PATH="$DATA_DIR/isin_map.json"
export THESIS_JSON_PATH="$DATA_DIR/thesis.json"
export BACKUPS_DIR="$DATA_DIR/backups"
export IMPORT_LOG_JSON_PATH="$DATA_DIR/import_log.json"
export FX_CACHE_DIR="$DATA_DIR/fx_cache"

echo "app_sandbox: DATA_DIR=$DATA_DIR" >&2
echo "app_sandbox: URL=http://localhost:$PORT/" >&2
echo "app_sandbox: navigate to a page with ?page=<module>, e.g. ?page=import_workbench" >&2

exec streamlit run app/ui/main.py \
  --server.port "$PORT" \
  --server.headless true \
  --browser.gatherUsageStats false
