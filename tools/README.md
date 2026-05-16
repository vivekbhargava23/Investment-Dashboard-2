# tools/

Helper scripts for the Investment Dashboard project workflow.
See `docs/METHODOLOGY.md` for why these scripts exist.

---

## Scripts

### `file.sh`

Files one or more `docs/TICKETS/TICKET-*.md` drafts as GitHub issues and
adds them to the project board (Backlog). Commit and push included.

**Usage:**

```bash
bash tools/file.sh
```

### `setup_github.sh`

Idempotent setup of GitHub labels and milestones. Run once per fresh repo clone.

**Usage:**

```bash
bash tools/setup_github.sh
```

### `regen_context.py`

Regenerates `docs/CONTEXT.md` from the live repo state. Run automatically by
the `update-context.yml` GitHub Action on every merge to main.

**Usage:**

```bash
python tools/regen_context.py
```

### `backfill_isin_from_csv.py`

Idempotently backfills the `isin` field onto `scalable_csv` transactions
whose `isin` is `null`, using each transaction's `csv_reference` to look
up the ISIN from the original Scalable Capital CSV export.

**When to use:** only when CSV-imported transactions have `isin: null` and
you have the original CSV on hand. This arises from the CSV-11 migration bug
where `isin_map.json` was absent at the time `migrate_v2_to_v3` ran.
The portfolio must already be at schema v3.

**Usage (always dry-run first):**

```bash
# Preview what would change — safe, writes nothing
python3 tools/backfill_isin_from_csv.py \
    --portfolio data/portfolio.json \
    --csv path/to/ScalableCapital-Broker-Transactions.csv

# Write changes (creates a timestamped backup first)
python3 tools/backfill_isin_from_csv.py \
    --portfolio data/portfolio.json \
    --csv path/to/ScalableCapital-Broker-Transactions.csv \
    --apply
```

**Backups:** written alongside `portfolio.json` as
`portfolio.json.backfill.bak.<YYYYMMDD-HHMMSS>`. Multiple runs accumulate
backups; prune by hand when no longer needed.

**Safety guarantees:** never overwrites a transaction whose `isin` is already
set; skips manual/switch transactions; refuses to run on non-v3 portfolios.

---

## Toolchain requirements

### `file.sh` and `setup_github.sh`

These scripts are written to be **POSIX-portable** (bash 3.2+, BSD grep, POSIX sed).
No GNU-only constructs (`mapfile`, `grep -P`, `${var,,}`, `declare -A`, etc.) are used.

| Tool | Minimum version | Notes |
|---|---|---|
| `bash` | 3.2+ | Stock macOS bash 3.2.57 is sufficient |
| `grep` | any | BSD grep (macOS default) is sufficient; no `-P` flag used |
| `sed` | POSIX | BSD sed (macOS default) is sufficient |
| `git` | any recent | Must be authenticated to the repo |
| `gh` | any recent | Must be authenticated (`gh auth login`) |
| `jq` | 1.6+ | `brew install jq` if missing |

### macOS invocation

```bash
bash tools/file.sh
```

No `brew install bash` or GNU grep required. The scripts run on stock macOS.

### Linux invocation

```bash
bash tools/file.sh
```

Identical — no distro-specific packages needed beyond `git`, `gh`, and `jq`.

---

## Forbidden constructs (future contributors)

To keep scripts portable, do **not** introduce:

- `mapfile` / `readarray` — bash 4+ only. Use `while IFS= read -r` loop instead.
- `grep -P` / `grep -oP` — GNU-only. Use `sed -nE` with capture groups instead.
- `${var,,}` / `${var^^}` — bash 4+ case conversion. Use `tr '[:upper:]' '[:lower:]'` instead.
- `declare -A` — associative arrays are bash 4+. Use parallel indexed arrays instead.
- `sed -i 's/foo/bar/' file` — GNU form. BSD requires `sed -i '' 's/foo/bar/' file`.
  Use a temp file (`sed 's/foo/bar/' file > file.tmp && mv file.tmp file`) for portability.
- `date -d <string>` — GNU-only. BSD form is `date -j -f '%Y-%m-%d' "$str" +%s`.

These restrictions are enforced by `shellcheck` in CI (`.github/workflows/ci.yml`).
