# TICKET-SYNC-1 — Stamp ISIN on every imported transaction + repair the backfill tool

**Priority:** CRITICAL
**Milestone:** Investment Panel
**Recommended model:** Sonnet — two small, fully specified changes with tests.
**Estimated session length:** 45 min
**Drafted by:** Vivek + Claude (Cowork session 2026-09-03)
**Depends on:** nothing. Blocks SYNC-2..7.

> **After this ticket merges:** every transaction created by the CSV import carries its ISIN, and `tools/backfill_isin_from_csv.py` can heal the 71 existing rows with `isin: null` plus the 3 rows whose provenance was stripped by a Manage-page edit.

## Problem

`app/ui/pages/import_workbench.py::_build_transaction` constructs `Transaction(...)` without
`isin=row.isin`. The line existed in `importer.py` (TICKET-CSV-8) and was lost when
TICKET-CSV-15 deleted that file (commit `bf598ab`). Data on 2026-09-03: 71 of 213
`scalable_csv` transactions have `isin: null`. `rewrite_ticker_for_isin` therefore misses them.

Three rows (`SCALJs8xHVx7kmM`, `SCALfUhudR6CoyD`, `SCALs4ptGWj8u9P`) were edited on the
Manage page and now have `source: manual`, `csv_reference: null`, `isin: null`. The backfill
tool matches on `csv_reference` only, so it cannot repair them.

## Execution — one commit per step

### Step 1 — importer stamps ISIN
File `app/ui/pages/import_workbench.py`, function `_build_transaction`. In the
`Transaction(...)` call add the keyword `isin=row.isin or None,` directly after
`notes=notes,`. No other change.

Test, file `tests/unit/ui/test_import_workbench.py`, next to `test_build_transaction_buy`:
```python
def test_build_transaction_stamps_isin() -> None:
    row = _make_row(isin="KYG0535Q1331")   # use the module's existing row factory; if none exists, copy the row literal from test_build_transaction_buy and set isin
    tx = _build_transaction(row)
    assert tx is not None and tx.isin == "KYG0535Q1331"
```
Also assert in the existing sell test that `tx.isin == row.isin`.

### Step 2 — backfill tool matches by `id` too and restores provenance
File `tools/backfill_isin_from_csv.py`, function `_plan`. Current rule: for each tx with
`source == "scalable_csv"` and `isin is None`, look up `csv_reference` in the CSV
reference→ISIN map. New rule, applied in this order per transaction:
1. If `csv_reference` is not None and is in the map → set `isin` (existing behaviour).
2. Else if `tx["id"]` is in the map → set `isin`, set `csv_reference = id`, set
   `source = "scalable_csv"`. Count these separately as `repaired_provenance`.
3. Else leave untouched; count as `unmatched`.
Rule 2 must apply regardless of the current `source` value (the three damaged rows say
`manual`). `_print_plan` prints the three counts and lists every rule-2 row (id, ticker,
date). `_apply_plan` unchanged apart from writing the extra fields.

Tests, file `tests/unit/tools/test_backfill_isin_from_csv.py`: add
`test_plan_repairs_provenance_when_matched_by_id` (a tx with `source: manual`,
`csv_reference: None`, id present in CSV → planned with isin, csv_reference = id, source =
scalable_csv) and `test_plan_leaves_unmatched_untouched`.

### Step 3 — gate, commit, session log, PR (standard ritual).

## Operational step for Vivek (after merge, real data — the agent does NOT run this)
```
python tools/backfill_isin_from_csv.py --portfolio data/portfolio.json --csv "<path to 2026-09-03 Scalable CSV>" --dry-run
python tools/backfill_isin_from_csv.py --portfolio data/portfolio.json --csv "<same csv>" --apply
```
Expected dry-run: 71 backfilled by reference, 3 repaired by id, 0 unmatched. If unmatched > 0,
stop and paste the list into the next session before applying.

## Acceptance criteria
- [ ] `_build_transaction` sets `isin` for buy and sell rows (tests).
- [ ] Backfill dry-run on a fixture with the three damaged shapes reports 1 by-reference,
      1 by-id-repaired, 1 unmatched (tests).
- [ ] `pytest`, `ruff check .`, `mypy app/`, `lint-imports` clean.

## Out of scope
Any UI change; read-time ticker derivation (SYNC-2).
