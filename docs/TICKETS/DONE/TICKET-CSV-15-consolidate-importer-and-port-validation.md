# TICKET-CSV-15 — Consolidate the CSV importer: port validation to the live path, delete the dead `run_import`

**Priority:** HIGH
**Status:** IN_PROGRESS
**Estimated session length:** 2 hr
**Recommended model:** Opus — touches money/import correctness and deletes a module; needs careful test migration so no guard is lost.
**Drafted by:** Vivek + Claude Code (session 2026-06-05)
**Implemented by:** TBD
**Milestone:** Investment Panel

---

## Problem

There are **two** Scalable-CSV importers and they have diverged:

- `app/adapters/scalable_csv/importer.py` — `run_import()` / `ImportSummary`. **Dead in
  production:** the only non-test importers of it are `app/adapters/scalable_csv/__init__.py`
  (re-export) and `tests/unit/test_scalable_csv_importer.py`. No page or script calls it.
- `app/ui/pages/import_workbench.py` — the **live** path: `plan_import()` (planner.py) +
  the page's own `_build_transaction()` + apply logic. This is what runs when the user
  uploads a CSV.

The dead module is not free to delete, because it holds the **only** copy of three import
guards that the live path does **not** replicate:

- `_check_amount()` — `abs(amount) ≈ abs(shares × price)` within €0.01 (catches CSV format drift).
- `_check_sign()` — directional sign per row type (Buy/Savings negative, Sell positive).
- Non-EUR currency defense — `run_import` raises on any non-EUR row; the live
  `_build_transaction()` (`import_workbench.py:124`) **hardcodes `Currency.EUR`** and would
  silently mis-tag a non-EUR row as EUR.

So today the live import path can silently accept a malformed or non-EUR row. This is the
TICKET-009 "silent corruption" failure mode. Deleting `importer.py` without porting these
guards would remove the safety net and its ~430 lines of tests.

## Solution

Port the three guards into the **live** path as **per-row validation at plan time**, then
delete the dead module and migrate its still-relevant test cases.

### Decisions already made — do not re-litigate

- Validation runs at **plan time** (`plan_import`), not apply time. A row that fails a
  guard is classified as a new blocked status **`RowStatus.VALIDATION_ERROR`** with a
  populated `error_message`, surfaced like other blocked rows. It must **not** raise and
  abort the whole import the way `run_import` did — per-row visibility beats all-or-nothing.
- `VALIDATION_ERROR` is a blocked status (counts in `_count_blocked`, shown in the table and
  chips), **not** silent. It means "this row looks wrong, look at it."
- The EUR-only assumption stays (all Scalable rows are EUR). A non-EUR row becomes a
  `VALIDATION_ERROR`, never a silently-EUR transaction.
- `ImportSummary` is not resurrected anywhere; the workbench already has its own counts.

### Execution

1. **Add `RowStatus.VALIDATION_ERROR`** to `app/domain/csv_import.py`. Wire it into
   `import_workbench.py` `_STATUS_COLORS` (🔴), `_BLOCKED_STATUSES`, and the filter-chip list.
2. **Port the guards into `app/adapters/scalable_csv/planner.py`** as pure helpers
   (`_check_amount`, `_check_sign`, EUR check), reused/copied from `importer.py` verbatim so
   the Decimal tolerances match. In `plan_import`, after a row is otherwise NEW/INSERT, run
   the guards; on failure emit `_make(row, RowStatus.VALIDATION_ERROR, PlannedAction.SKIP,
   error_message=...)`. Apply must never build a Transaction for a `VALIDATION_ERROR` row.
3. **Add planner tests** in a new `tests/unit/adapters/scalable_csv/test_planner.py`
   covering: amount mismatch → VALIDATION_ERROR; wrong sign → VALIDATION_ERROR; non-EUR →
   VALIDATION_ERROR; and the behaviours the planner already owns but were only tested via
   `run_import` (Security-transfer skip, out-of-scope skip, already-imported no-op, content
   dedup). Reuse the fixtures in `tests/fixtures/scalable_csv/`.
4. **Delete the dead code:** `app/adapters/scalable_csv/importer.py`, remove `run_import`
   and `ImportSummary` from `app/adapters/scalable_csv/__init__.py` (and `__all__`), and
   delete `tests/unit/test_scalable_csv_importer.py` (every test in it targets `run_import`;
   the still-valuable cases were re-homed in step 3).
5. **Gate.** `pytest && ruff check . && mypy app/ && lint-imports`.

## Acceptance criteria

- [ ] Live import marks malformed rows (amount mismatch, wrong sign, non-EUR) as
      `VALIDATION_ERROR` and never imports them.
- [ ] `VALIDATION_ERROR` rows are surfaced (blocked count + chip + table), not silent.
- [ ] `app/adapters/scalable_csv/importer.py` is deleted; `run_import`/`ImportSummary` no
      longer exist anywhere in `app/`.
- [ ] New `test_planner.py` covers all ported guards and the pre-existing planner behaviours.
- [ ] `tests/unit/test_scalable_csv_importer.py` is deleted with no net loss of behavioural coverage.
- [ ] `ruff check .`, `mypy app/`, `lint-imports` clean.

## Files likely touched

- `app/domain/csv_import.py`, `app/adapters/scalable_csv/planner.py`,
  `app/adapters/scalable_csv/__init__.py`, `app/ui/pages/import_workbench.py`
- `tests/unit/adapters/scalable_csv/test_planner.py` (new), delete
  `app/adapters/scalable_csv/importer.py` and `tests/unit/test_scalable_csv_importer.py`

## Out of scope

- The Mappings-page control actions and reset features (TICKET-CSV-16 / TICKET-CSV-17).
- Any change to FX handling beyond "non-EUR → VALIDATION_ERROR". Multi-currency CSV is a
  separate design.
- The ticker↔ISIN classification seam (TICKET-TAX-1 / TICKET-H1 territory).

## Notes / assumptions

- **Sequence after PR #155 merges.** #155 (TICKET-CSV-14 review fix) edits
  `import_workbench.py` and added ignored-path tests to `tests/unit/test_scalable_csv_importer.py`.
  Branch this off updated `main` so those additions (which test the dead path) are deleted
  cleanly with the rest of the file.
- Confirm the live apply step does not call any `importer.py` symbol before deleting (it does
  not today — `import_workbench.py` has its own `_build_transaction`).
- `_check_amount` uses a €0.01 absolute tolerance; preserve it exactly to avoid false positives.
