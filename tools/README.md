# tools/

Helper scripts for the Investment Dashboard project workflow.
See `docs/METHODOLOGY.md` for why these scripts exist.

---

## Scripts

### `gate.sh`

Activates the `investment-dashboard` conda environment and runs the full local
gate: `pytest`, `ruff check .`, `mypy app/`, and `lint-imports`. It exits on the
first failure and names the failed check.

**Usage:**

```bash
bash tools/gate.sh
```

### `next.sh`

Prints the ranked Ready/Backlog ticket menu from the GitHub Projects board. The
menu includes priority, recommended model, dependency blockers, and unblock score.
Blocked tickets are shown, not hidden.

**Usage:**

```bash
bash tools/next.sh
```

### `start_ticket.sh`

Starts a ticket from `main`: reconciles closed `In review` board items to `Done`,
checks for a clean tree, pulls, creates or reuses the feature branch, marks the
ticket file `IN_PROGRESS`, and moves the board item to `In progress`.

**Usage:**

```bash
bash tools/start_ticket.sh TICKET-M9
```

### `finish_ticket.sh`

Finishes a ticket after the implementation and session-log commits exist. It
reruns `gate.sh`, pushes the current branch, moves the board item to `In review`,
and opens the PR with a `Closes #N` footer.

**Usage:**

```bash
bash tools/finish_ticket.sh TICKET-M9
```

### `doctor.sh`

Non-mutating diagnostics for local workflow state: dirty tree, current branch,
retired workflow files, board sanity, and dependency blockers.

**Usage:**

```bash
bash tools/doctor.sh
```

### `ticket_workflow.py`

Shared implementation behind `next.sh`, `start_ticket.sh`, `finish_ticket.sh`,
and `doctor.sh`. Keep CLI behavior behind the shell entry points; import pure
helpers in tests when dependency parsing or ranking changes.

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
| `python3` | 3.11+ | Used by `ticket_workflow.py`; the project conda env satisfies this |

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
