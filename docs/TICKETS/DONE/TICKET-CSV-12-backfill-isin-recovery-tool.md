# TICKET-CSV-12 — Productionize ISIN-from-CSV backfill recovery script

**Status:** IN_PROGRESS
**Priority:** MEDIUM
**Estimated session length:** 45 min
**Drafted by:** Vivek + Claude Chat (2026-05-16)
**Implemented by:** TBD
**Milestone:** Investment Panel

---

## Problem

On 2026-05-16, the CSV-8 migration v2→v3 ran on production data and produced zero ISIN backfills across 151 Scalable-CSV-sourced transactions (see CSV-11 for the underlying bug). Recovery was performed by a one-shot Python script pasted into the terminal that used each transaction's `csv_reference` to look up its ISIN from the original Scalable CSV file on disk. The script worked: 151 of 151 ISINs were restored, and the user verified Mappings-edit rewrites and delete-blocks then behaved correctly.

The recovery script lives only in a chat transcript. Next time something diverges between `portfolio.json` and the source CSV — whether from another migration bug, a manual edit, or a partial import — there is no on-repo tool to fix it. This ticket productionizes the recovery into `tools/backfill_isin_from_csv.py`.

## Solution

A standalone CLI script that idempotently backfills `isin` onto any transaction with `source == "scalable_csv"` and `isin is None`, using the transaction's `csv_reference` to look up the ISIN from a supplied CSV file. Refuses to modify transactions whose `isin` is already set, even if the CSV says something different.

### Decisions already made

- **Idempotent**: running twice produces no further changes after the first run. Safe to run defensively.
- **Read-only by default**: `--dry-run` is the default. The script prints what it *would* do but writes nothing. Mutation requires `--apply`.
- **Backup before mutation**: when `--apply` is given, the script writes `portfolio.json.backfill.bak.<timestamp>` before touching anything. Multiple runs accumulate backups; no rotation.
- **Atomic write**: tmp + rename + fsync, matching the existing repository's atomic-write pattern.
- **Never overwrites existing ISINs**: if a transaction already has `isin` set, the script reports it (in dry-run output) and skips it. There is no `--force` flag in this ticket; if someone needs to overwrite, they edit `portfolio.json` directly.
- **Only handles `source == "scalable_csv"`**: manual and other-source transactions are skipped silently.
- **Refuses to run on non-v3 portfolios**: if `portfolio.json` is v1 or v2, exits with an error pointing at `migrate_v2_to_v3` (or the equivalent for v1). The script's job is to fix incomplete v3 data, not to migrate.

---

## Execution

### Step 1: The script

**New file:** `tools/backfill_isin_from_csv.py`

CLI signature:

```
python3 tools/backfill_isin_from_csv.py \
    --portfolio data/portfolio.json \
    --csv path/to/ScalableCapital-Broker-Transactions.csv \
    [--dry-run | --apply]
```

Behaviour:

1. Validate args. Both paths must exist; if not, error out with a clear message.
2. Load `portfolio.json`. If `version != 3`, error out: `"This script only operates on schema v3. Found version N. Run the migration first."`
3. Parse the CSV via the existing parser (`app.adapters.scalable_csv.parser.parse_csv`) to get `ParsedCsvRow` objects. Build `{reference: isin}` from rows whose `reference` and `isin` fields are both present and non-empty.
   - **Important**: do NOT roll a fresh `csv.DictReader` — reuse the existing parser so the script benefits from any future column-name changes. If the parser is too heavy-weight (e.g. it does row filtering you don't want here), import the lowest-level helper that just turns a CSV row into a dict with `reference` and `isin` extracted.
4. Plan:
   - For each transaction in `portfolio["transactions"]` where `source == "scalable_csv"`:
     - if `isin is not None` → record as "already-set, skipping" (count this)
     - if `csv_reference is None` → record as "no csv_reference, cannot backfill" (count and warn)
     - if `csv_reference not in {reference: isin}` map → record as "reference not found in CSV" (count and warn — this can happen if the CSV file is older than the transaction or vice versa)
     - else → record as planned change `(tx_id, ticker, csv_reference, isin_to_set)`
5. Print plan summary:
   ```
   Backfill plan for data/portfolio.json:
     Planned changes:           N
     Already set (skipped):     N
     No csv_reference:          N
     Reference not found in CSV: N
   ```
   Followed by the first 5 planned changes as a preview, plus the first 5 "not found in CSV" entries if any.
6. If `--dry-run` (or neither flag): exit 0 without modifying anything.
7. If `--apply`:
   - Write timestamped backup: `data/portfolio.json.backfill.bak.<YYYYMMDD-HHMMSS>`.
   - Apply planned changes to the in-memory dict.
   - Atomic write back to `portfolio.json`.
   - Re-read and verify: count CSV transactions, count of those with ISIN. Print:
     ```
     Wrote data/portfolio.json
     Backfill complete: N of M CSV transactions now have ISIN.
     ```
   - Exit 0.

Use `argparse`. The script is standalone — no Streamlit, no app config imports beyond the parser. Imports limited to:
- stdlib (`argparse`, `json`, `shutil`, `pathlib`, `datetime`)
- `app.adapters.scalable_csv.parser` (or the lightest equivalent)

If `--dry-run` and `--apply` are both passed, error out. If neither is passed, default to `--dry-run` (safe-by-default).

### Step 2: Tests

**File:** `tests/unit/tools/test_backfill_isin_from_csv.py` (new — may need a new `tests/unit/tools/` directory).

Test cases:

- **Dry run plans correctly**: portfolio with 5 CSV transactions (3 unbackfilled, 2 already set) + a CSV fixture covering all 5 references. Run `--dry-run`. Assert exit 0, no file modification, planned-change count is 3, already-set count is 2.
- **Apply backfills correctly**: same fixture. Run `--apply`. Assert all 5 transactions now have correct ISIN, backup file exists with pre-apply content, returned exit 0.
- **Idempotent**: run `--apply` twice in a row. Second run plans 0 changes. No second backup is necessary, but it's acceptable if one is created (different timestamp).
- **Already-set ISIN is never overwritten**: portfolio with a transaction that has `isin="US0000000000"` (wrong but set). CSV's reference→ISIN map says it should be `"US1111111111"`. Run `--apply`. Assert the transaction's ISIN remains `"US0000000000"`. Skip count increments.
- **Missing csv_reference**: transaction with `csv_reference: None`. Skip silently for the unbackfilled-but-no-ref case. Plan summary reports it. No crash.
- **Reference not in CSV**: transaction with a `csv_reference` not present in the CSV file. Skip with warning. Plan summary reports it.
- **Wrong schema version**: portfolio is v2. Script exits with error message, no mutation.
- **Missing CSV file**: argparse exits with error.
- **Both --dry-run and --apply**: error out.

### Step 3: Documentation

Add an entry to `tools/README.md` (or create it if it does not exist) describing:
- What the script does
- When to use it ("only when CSV-imported transactions have `isin: None` and you have the original CSV on hand")
- Example invocation (dry run first, then apply)
- Where backups are written
- Mention CSV-11 as the upstream bug this works around

A 10-line section, not a manual. The script's `--help` text covers usage.

---

## Acceptance criteria

- [ ] `tools/backfill_isin_from_csv.py` exists, has a working `--help`, defaults to dry-run.
- [ ] Dry-run mode prints a plan and does not modify any file.
- [ ] Apply mode writes a timestamped backup and atomically updates `portfolio.json`.
- [ ] Idempotent: second run finds nothing to do.
- [ ] Never overwrites a transaction whose `isin` is already set.
- [ ] Refuses to run on non-v3 portfolios with a clear error.
- [ ] All Step 2 tests pass.
- [ ] `tools/README.md` (or equivalent) documents the script.
- [ ] `ruff check .`, `mypy app/`, `lint-imports` clean. (The script lives in `tools/` — confirm that location is covered by the linters; if not, file a separate ticket to extend coverage, do not bundle.)

### Manual smoke

The current `portfolio.json` has all 151 CSV transactions backfilled (via the one-shot script). The agent should:
1. Run `python3 tools/backfill_isin_from_csv.py --portfolio data/portfolio.json --csv /Users/vivekb2017/Downloads/2026-05-14_20-00-30_ScalableCapital-Broker-Transactions.csv --dry-run`.
2. Expect: "Planned changes: 0 · Already set (skipped): 151".
3. Confirm exit 0, no backup file created.

---

## Out of scope

- Auto-discovery of the CSV file path. User passes it explicitly.
- Backfill for non-`scalable_csv` sources.
- A `--force` flag to overwrite existing ISINs.
- Backup rotation. Old backups accumulate; the user prunes by hand.
- Integration into the Streamlit UI as a "Repair" button. Possible future improvement; not now.

---

## Notes / assumptions

- Depends on CSV-11 only conceptually (the bug CSV-12 mitigates). CSV-12 can be implemented and merged independently of CSV-11's progress.
- Assumes the Scalable CSV's reference column is named `reference` and the ISIN column is named `isin`. Confirm against the parser's column constants; if the parser uses different names internally, follow the parser's naming.
- Assumes `app.adapters.scalable_csv.parser` is importable from `tools/`. Python's import system should handle this if `tools/` is run from the repo root (`python3 tools/backfill_isin_from_csv.py ...`). If running from elsewhere breaks the import, document the working-directory requirement in `--help`.
- The Scalable CSV file at `/Users/vivekb2017/Downloads/2026-05-14_20-00-30_ScalableCapital-Broker-Transactions.csv` is the reference fixture for manual testing on this machine. **Do not hardcode that path** — it must be an arg.
