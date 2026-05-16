# TICKET-CSV-11 — Fix migration v2→v3 ISIN backfill (zero-result bug)

**Status:** QUEUED
**Priority:** HIGH
**Estimated session length:** 2 hr
**Drafted by:** Vivek + Claude Chat (2026-05-16)
**Implemented by:** TBD
**Milestone:** Investment Panel

---

## Problem

The `migrate_v2_to_v3` migration introduced in CSV-8 ran successfully on production data (no crash, schema bumped to v3, summary returned) but **produced zero ISIN backfills** on 151 Scalable-CSV-sourced transactions.

Concrete observation on 2026-05-16, after CSV-8 was merged and the user opened the app:
- `data/portfolio.json` schema_version = 3 (migration ran).
- 151 transactions with `source == "scalable_csv"`.
- 0 of 151 had `isin` populated. All 151 had `isin: None`.
- `data/isin_map.json` at the time contained 20 mapped entries covering every ticker in the portfolio (verified by manual inspection — every ticker in `portfolio.json` had a corresponding `mapped` entry in `isin_map.json`).
- Pre-flight collision check on the same `isin_map.json` reported zero collisions earlier the same day.

So the migration's reverse-lookup `{ticker: isin}` should have matched every transaction's ticker. It matched none. Root cause unknown. The user destroyed `portfolio.json.v2.bak` before the bug was diagnosed, so we cannot directly autopsy the pre-migration state — but recovery has already been performed via a `csv_reference`-based one-shot script (see CSV-12), and the current portfolio is correct.

Downstream impact while the bug was live:
- `rewrite_ticker_for_isin` returned 0 on every mapping edit (no transactions matched the ISIN being remapped, because no transactions had any ISIN at all).
- `count_transactions_for_isin` returned 0 on every delete attempt, so the "Cannot delete: N transactions still reference it" guard never fired. The user deleted a mapping (NVDA) without warning, orphaning 20 transactions. The mapping was manually restored.

This ticket exists to:
1. Diagnose why the migration produced zero results.
2. Fix the migration so it works correctly when re-run on a v2 portfolio.
3. Add a regression test that reproduces the failure mode (whatever it is) and asserts the fix.
4. Add observable signal so a future zero-result migration doesn't slip silently into production.

## Solution

### Investigation first, fix second

The agent must **not** write a fix and a test in the same step. The required order is:

1. **Reproduce.** Construct a synthetic v2 portfolio fixture that mirrors the production shape: 151 transactions, `source: "scalable_csv"`, tickers covering the set listed in the Notes section, plus a matching `isin_map.json` with all 20 entries `status: "mapped"`. Run `migrate_v2_to_v3` against it. **If the fixture produces non-zero backfills, the fixture does not match production conditions — iterate on the fixture until it does.** The agent's first deliverable is a fixture + a failing test asserting `backfilled_count == 151`.

2. **Diagnose.** With a reliably-failing test, instrument the migration (temporary log statements or pytest -s prints — to be removed before commit) to identify the exact line where the reverse-lookup-and-backfill loop deviates from expectation. Document the root cause in this ticket's Notes section as a PR comment before writing the fix.

3. **Fix.** Apply the minimal change that turns the failing test green. Remove instrumentation. The fix should preserve the existing collision check, the existing backup-before-mutation behaviour, and the existing atomic-write pattern.

4. **Harden.** Add observable signal: the migration's returned summary dict already has `migrated_count`, `manual_skipped_count`, `scalable_unbackfilled_count`. Add a **WARNING log** at the end of `load_all()` (the call site) when `scalable_unbackfilled_count > 0 and migrated_count == 0`. Message: `"v2→v3 migration produced zero ISIN backfills across N scalable_csv transactions — likely a logic bug, investigate before relying on isin-aware features."` This is the canary that would have caught today's bug at startup.

### Hypotheses to test (in order)

The agent should investigate these in order; first match wins. None has been confirmed.

**H1: isin_map.json path resolution.** The migration loads `isin_map.json` from a hardcoded `data/isin_map.json` path or via config. If the working directory or config path resolves to a non-existent or empty file, the reverse-lookup is `{}` and every transaction falls through to `isin = None`. Verify: check what path is actually opened during the migration, and what's in it at that moment. The fixture should be able to reproduce this by pointing the migration at a missing or empty map.

**H2: Status filter wrong.** The spec says `status == "mapped"`. If the loaded data uses a different status value (`"resolved"`, `"ok"`, `True`, etc.) — or if the field is missing entirely on some entries — the filter excludes everything. Verify: print the unique status values seen during reverse-map construction.

**H3: Ticker case mismatch.** Reverse map is keyed by ticker as it appears in `isin_map.json`. Transactions key by ticker as it appears in `portfolio.json`. If one is uppercase and the other isn't, the dict lookup misses. Verify: print a sample of both before the lookup loop.

**H4: Source field shape.** The check is `tx["source"] == "scalable_csv"`. If the v2 portfolio's transactions had a different source value (e.g. older imports stored it as `"scalable"` or `"csv"` or nothing at all) the branch never enters. Verify: print unique source values in the v2 portfolio before migration.

**H5: Dict iteration mutation.** If the loop mutates the dict it iterates over (e.g. modifies `entries` while iterating `entries.items()`), behaviour is undefined. Verify by code reading — if the existing migration does this, fix it independently of the root-cause hypothesis above.

**H6: Type coercion.** `isin_map.json`'s entries have a `ticker` field that may be `None` for unmapped entries. If the migration's reverse-map builder doesn't filter `None` out, the dict ends up with a `None: <isin>` entry and real ticker lookups miss. Verify by inspecting the constructed reverse map's keys.

These are not exclusive — multiple may apply. Find whichever explains today's observation.

---

## Execution

### Step 1: Reproduction fixture and failing test

**File:** `tests/fixtures/migration/portfolio_v2_production_shape.json` (new) — synthetic v2 portfolio matching production: 151 transactions across the 20 tickers listed in Notes, `source: "scalable_csv"` on each, plausible shares/prices, no `isin` field.

**File:** `tests/fixtures/migration/isin_map_v1_production_shape.json` (new) — synthetic ISIN map matching production: 20 entries `status: "mapped"`, all tickers covered, plus 6 entries `status: "unmapped"`.

**File:** `tests/unit/adapters/test_migration.py` (extend existing) — new test `test_migrate_v2_to_v3_backfills_production_shape`:
- Load both fixtures into a tmp dir.
- Run `migrate_v2_to_v3(tmp_portfolio_path)`.
- Assert returned summary: `migrated_count == 151`, `scalable_unbackfilled_count == 0`.
- Assert every transaction in the post-migration file has `isin` set and matches the expected ISIN for its ticker (build expected map from the fixture isin_map).

**Acceptance for Step 1:** test exists and fails as written, with an error message that clearly shows the divergence (e.g. `AssertionError: expected migrated_count=151, got 0`).

### Step 2: Diagnose and document root cause

With the test failing, instrument enough to identify which hypothesis matches. **Document the finding in this ticket as a PR comment** (or in the PR description if simpler) **before writing the fix**. Acceptable forms:

> Root cause: H4 — the v2 portfolio's `source` field was stored as `"scalable"` (without `_csv` suffix). The migration's filter `if tx["source"] == "scalable_csv"` excluded all rows. Fix: accept both `"scalable"` and `"scalable_csv"`.

This documentation is the deliverable for Step 2; the agent should not silently fix without recording the cause.

### Step 3: Fix the migration

Apply the minimum change required to make the Step 1 test pass. **Files limited to:**
- `app/adapters/repo_json/migration.py`
- `app/adapters/repo_json/json_repo.py` (only if the bug is in the call site, not the migration function itself)

Do **not** modify anywhere else. If the root cause turns out to require changes outside these files, **stop** and report — this is scope expansion that needs Vivek's call.

The fix must preserve all existing behaviour from CSV-8:
- Backup written before any mutation
- Collision check still aborts before mutation
- Atomic write (tmp + rename + fsync)
- Returned summary dict structure unchanged (`migrated_count`, `manual_skipped_count`, `scalable_unbackfilled_count`)

### Step 4: Hardening — zero-backfill warning

**File:** `app/adapters/repo_json/json_repo.py`

In `load_all()`, after the v2→v3 migration branch runs and returns its summary, add:

```python
import logging
if summary["scalable_unbackfilled_count"] > 0 and summary["migrated_count"] == 0:
    logging.warning(
        "v2→v3 migration produced zero ISIN backfills across "
        f"{summary['scalable_unbackfilled_count']} scalable_csv transactions. "
        "This is likely a logic bug — investigate before relying on isin-aware features."
    )
```

Same warning emits even after the bug is fixed, because it's a canary against future regressions. The condition is "we found CSV transactions but couldn't backfill any" — a state that should never occur if the map covers any of them.

### Step 5: Regression test for the fix

The Step 1 test (now passing) serves as the regression test. Verify it would fail again if the fix is reverted: temporarily revert the fix locally, confirm the test fails, restore the fix.

### Step 6: Test the warning

Extend `tests/unit/adapters/test_migration.py`:
- `test_zero_backfill_logs_warning`: construct a v2 portfolio with scalable_csv transactions whose tickers are NOT in the isin_map. Run migration. Assert the warning log fires with the expected message and the correct count.

### Step 7: Edge cases

Extend the migration test suite with the cases the CSV-8 spec listed but did not necessarily catch this failure mode:
- Empty `isin_map.json` (no entries). Expectation: migration completes, all transactions get `isin=None`, summary reflects 0/N backfilled, warning fires.
- `isin_map.json` with all entries `status: "unmapped"`. Same expectation as above.
- A transaction whose `ticker` field is missing entirely (defensive). Expectation: that tx gets `isin=None`, migration does not crash.
- A portfolio with `source` field present on some transactions but missing on others. Expectation: missing-source transactions are treated as manual (isin=None), source-present transactions process normally.

---

## Acceptance criteria

- [ ] Synthetic v2 fixture matching production shape exists at `tests/fixtures/migration/portfolio_v2_production_shape.json`.
- [ ] Test `test_migrate_v2_to_v3_backfills_production_shape` exists, asserts 151/151 backfill, passes after fix.
- [ ] Root cause documented in PR comment or description before the fix commit.
- [ ] Fix is limited to `app/adapters/repo_json/migration.py` and possibly `json_repo.py`. No other files modified.
- [ ] Existing CSV-8 migration tests still pass.
- [ ] Zero-backfill warning fires from `load_all()` when the canary condition is met; covered by a test.
- [ ] All edge-case tests pass.
- [ ] `ruff check .`, `mypy app/`, `lint-imports` clean.

### Manual smoke (post-merge, by Vivek)

The current `portfolio.json` is already v3 with all ISINs populated (via the recovery script). To smoke-test the fix, the agent should provide a one-line snippet in the PR description that lets Vivek temporarily downgrade a copy of `portfolio.json` to v2 (strip `isin` field, set version=2), run the app, and observe that the migration correctly backfills all 151 ISINs and produces no warning. Then restore the original.

---

## Out of scope

- The recovery script for already-broken portfolio.json files. That is CSV-12.
- Refactoring the migration to use `csv_reference` as the source of truth instead of ticker reverse-lookup. The recovery script already does that out-of-band; whether the migration should adopt the same approach is a separate design discussion. **Do not change the migration's strategy here** — fix the bug in the existing strategy first.
- Backup file retention policy. Today CSV-8 creates `portfolio.json.v2.bak` and never deletes it. The user destroyed theirs manually. Hardening backup management is a separate concern.

---

## Notes / assumptions

- The 20 tickers seen in production at the time of the bug: VUAA.DE (21), NVDA (20), DELL (17), QDVE (13), ANAU (13), HY9H.F (10), IUES.DE (10), XNAS.DE (9), ASX (7), PARRO.PA (7), CIEN (4), 5631.T (4), MU (3), APD (3), MRVL (3), KD (2), ETN (2), RHM.DE (1), AVGO (1), ANET (1). Total: 151.
- The user destroyed the v2 backup before the bug was investigated, so direct autopsy is not possible. The reproduction must be from first principles based on what we know about the v2 schema.
- The CSV-8 ticket pre-flight collision check on `isin_map.json` was done by a separate Python one-liner in chat, not by the migration code itself. If the migration loads `isin_map.json` via a different path or with different parsing, that's a candidate root cause.
- Assumes the existing test file `tests/unit/adapters/test_migration.py` exists from CSV-8. If migration tests are colocated elsewhere, use the existing location.
- Assumes the existing v1→v2 migration is not affected by this bug. Verify by reading its code; if the v1→v2 has the same pattern that breaks v2→v3, consider whether to fix both. **If the v1→v2 has an equivalent bug, file a separate ticket — do not bundle.**
