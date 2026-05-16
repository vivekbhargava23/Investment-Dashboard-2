# TICKET-CSV-8 — ISIN on Transaction + remap-on-mapping-edit

**Status:** QUEUED
**Priority:** HIGH
**Estimated session length:** 2 hr
**Drafted by:** Vivek + Claude Chat (2026-05-16)
**Implemented by:** TBD
**Milestone:** Investment Panel

---

## Problem

`isin_map.json` is consulted only during CSV import. After that, every Transaction in `portfolio.json` carries a baked-in `ticker` string with no link back to its ISIN. Editing a mapping in the Mappings page updates `isin_map.json` but every existing transaction still references the old or null ticker. Result: greyed-out rows on the Live Overview that only "unstick" by deleting `portfolio.json` and re-importing the entire CSV.

Concrete current symptoms on main:
- SK Hynix (ISIN `US78392B1070`) was manually edited in `isin_map.json` from `HXSCL` to `HY9H` (and needs another edit to `HY9H.F` — verified to be the only Frankfurt symbol yfinance prices for that GDR). Neither edit propagated to `portfolio.json`. Row stays greyed.
- QDVE, ANAU, 5631.T, ETN: ISINs were manually re-mapped from `unmapped`/old tickers in `isin_map.json` (see commit immediately preceding this ticket). Transactions in `portfolio.json` still carry the pre-edit ticker. Rows stay greyed.

## Solution — Stage 1 of a two-stage refactor

Add `isin: str | None = None` to `Transaction`. Importer populates it from `ParsedCsvRow.isin`. A migration backfills existing transactions via reverse-lookup against the current `isin_map.json`. When the user edits or deletes a mapping in the Mappings UI, a new `isin_remap` service rewrites or blocks based on transactions that reference that ISIN.

**Stage 2** (resolve ticker at read time from ISIN; drop `Transaction.ticker` eventually) is **out of scope for this ticket**. Will be filed separately once Stage 1 is stable.

### Decisions already made — do not re-litigate

- Backfill via reverse-lookup against current ISIN map: build `{ticker: isin}` from `isin_map.json` where `status == "mapped"`. On collision (two ISINs → same ticker), abort migration with explicit error listing the colliding tickers. Do not silently set `isin = None`. **Pre-flight check on 2026-05-16 confirms zero collisions in current `isin_map.json` (20 mapped, 6 unmapped).**
- Manual-source transactions (`source == "manual"`) stay `isin = None` after migration. Out of scope to backfill these.
- Delete in Mappings page **hard-blocks** when transactions reference the ISIN. No override flag.
- The Mappings page's ticker input remains a plain `st.text_input` in this ticket. Fuzzy typeahead is **TICKET-CSV-9**.
- Live Overview name resolution and CCY/price hover cleanup is **TICKET-CSV-10**.

---

## Execution order — one commit per step, tests pass between

### Step 1: Add `isin` field to Transaction

**File:** `app/domain/models.py`

Add `isin: str | None = None` to `Transaction` between `notes` and `csv_reference` (alphabetical-ish grouping with the other CSV-related metadata fields is fine — match existing style). No validator. Field is purely informational at this stage.

Run existing tests; fix any positional `Transaction(...)` constructors in tests if the new field somehow breaks ordering (it shouldn't, since `Transaction` is constructed by keyword everywhere — verify by grep).

### Step 2: Importer populates ISIN

**File:** `app/adapters/scalable_csv/importer.py`

At the `Transaction(...)` construction site (search for `Transaction(`, there should be exactly one in this file), pass `isin=row.isin`. One-line change. `ParsedCsvRow` already carries the ISIN — verify in `parser.py` if unsure.

### Step 3: Migration v2 → v3

**File:** `app/adapters/repo_json/migration.py`

Add `migrate_v2_to_v3(path: Path) -> dict`:
- Read `portfolio.json`. If `version != 2`, raise.
- Write `portfolio.json.v2.bak` as a literal copy of the file **before any mutation**.
- Load `isin_map.json` from `data/isin_map.json` (use the existing path resolution — check how the v1→v2 migration locates files if it needs config access; mirror that pattern).
- Build `ticker_to_isin: dict[str, str]` from `isin_map.json` entries where `status == "mapped"` and `ticker is not None`.
- **Collision check:** if any ticker appears twice in the reverse map, raise `RuntimeError` listing the colliding `(ticker, [isins])` pairs. Migration aborts. Portfolio file is **unchanged** on collision (do the check before mutating anything in memory or on disk except the backup).
- For each tx dict in `transactions`:
  - If `source == "scalable_csv"` and `tx["ticker"] in ticker_to_isin`: set `tx["isin"] = ticker_to_isin[tx["ticker"]]`.
  - Otherwise: set `tx["isin"] = None` (covers `source == "manual"` and CSV transactions whose ticker no longer appears in the map).
- Bump version to 3.
- Write atomically (tmp + rename + fsync) matching the existing `migrate_v1_to_v2` pattern.
- Return a summary dict: `{"migrated_count": int, "manual_skipped_count": int, "scalable_unbackfilled_count": int}`.

**File:** `app/adapters/repo_json/json_repo.py`

- Bump `SCHEMA_VERSION` from 2 to 3.
- In `load_all()`, add a `v2 → v3` branch that mirrors the existing `v1 → v2` pattern: call `migrate_v2_to_v3`, log the returned summary, reload from disk after migration.

### Step 4: Remap service

**New file:** `app/services/isin_remap.py`

```python
from app.ports.repository import TransactionRepository


def rewrite_ticker_for_isin(
    tx_repo: TransactionRepository,
    isin: str,
    new_ticker: str,
) -> int:
    """Rewrite the ticker field on every transaction matching `isin`.

    Returns the count of transactions rewritten. Zero if none match.
    """
    txs = tx_repo.load_all()
    affected = [tx for tx in txs if tx.isin == isin]
    if not affected:
        return 0
    updated = [
        tx.model_copy(update={"ticker": new_ticker}) if tx.isin == isin else tx
        for tx in txs
    ]
    tx_repo.save_all(updated)
    return len(affected)


def count_transactions_for_isin(
    tx_repo: TransactionRepository,
    isin: str,
) -> int:
    """Count transactions referencing `isin`. Used to block deletes."""
    return sum(1 for tx in tx_repo.load_all() if tx.isin == isin)
```

Place under `app/services/` (not `app/adapters/`) — pure orchestration over the repo port.

### Step 5: Mappings page wiring

**File:** `app/ui/pages/mappings.py`

Add these imports near the top, alongside `get_isin_map_repo`:
```python
from app.services.isin_remap import (
    count_transactions_for_isin,
    rewrite_ticker_for_isin,
)
from app.ui.wiring import get_repository
```

In `_render_edit_row` save-button handler (current line ~187, the `if st.button("Save", ..., type="primary")` block, **after** `get_isin_map_repo().save(updated_doc)` succeeds and **before** the toast-message construction):

```python
n = rewrite_ticker_for_isin(get_repository(), isin, raw)
```

Then append the rewrite count to the success toast. Preserve the existing hint/warn branches; just extend the message:
- If `hint`: `f"Updated {isin} → {raw} ({hint}). Rewrote {n} transaction(s)."`
- If `warn`: `f"Updated {isin} → {raw}. Warning: {warn}. Rewrote {n} transaction(s)."`
- Plain: `f"Updated {isin} → {raw}. Rewrote {n} transaction(s)."`

In `_render_delete_confirmation` Yes-button handler (current line ~210, `if st.button("Yes", ..., type="primary")`), **before** calling `_delete_mapping`:

```python
n = count_transactions_for_isin(get_repository(), isin)
if n > 0:
    st.session_state.mappings_confirming_delete_isin = None
    st.session_state.mappings_feedback = (
        "error",
        f"Cannot delete {isin}: {n} transaction(s) still reference it. "
        "Delete those transactions first or remap to a different ticker.",
    )
    st.rerun()
```

If `n == 0`, the existing delete path runs unchanged.

**Leave the unmapped → mapped save path in `_render_unmapped_section` alone.** By definition no existing transactions reference an unmapped ISIN (the CSV importer skips unmapped rows), so no rewrite is needed there. Adding a no-op `rewrite_ticker_for_isin` call there is harmless but unnecessary.

### Step 6: Tests

**Unit tests for `app/services/isin_remap.py`** — new file `tests/unit/services/test_isin_remap.py`:
- `rewrite_ticker_for_isin`:
  - empty repo → returns 0, no save side-effect
  - no-match (ISIN not in any tx) → returns 0
  - single matching tx → returns 1, that tx's ticker is rewritten, others untouched
  - multi-match (3 tx with same ISIN, 2 with different ISIN) → returns 3, all 3 rewritten, the other 2 unchanged
  - rewritten tx preserves all other fields (shares, price_native, fx_rate_eur, source, csv_reference) — assert by field-by-field equality except ticker
- `count_transactions_for_isin`:
  - same fixture variants, asserts the count is correct

**Migration tests** in `tests/unit/adapters/test_migration.py` (or wherever the existing `migrate_v1_to_v2` tests live — match location):
- **Happy path:** v2 fixture with 3 `scalable_csv` tx + 1 `manual` tx + an `isin_map.json` fixture covering all 3 scalable tickers → after migrate, all 3 scalable get correct ISINs, manual stays `isin=None`, `portfolio.json.v2.bak` file exists with identical pre-migration content, summary dict reports `{migrated_count: 3, manual_skipped_count: 1, scalable_unbackfilled_count: 0}`.
- **Collision:** isin_map has two ISINs both mapping to ticker `"FOO"` + a tx with `ticker="FOO"` → `migrate_v2_to_v3` raises `RuntimeError` whose message names the colliding ticker and both ISINs. Portfolio file on disk is unchanged (still version 2). Backup file may or may not exist (acceptable either way; document which).
- **Unbackfillable:** scalable_csv tx with ticker not present in `isin_map.json` → migration succeeds, that tx has `isin=None`, summary reports `scalable_unbackfilled_count: 1`.
- **Version idempotence:** running `migrate_v2_to_v3` on a v3 portfolio raises (version != 2 check).

**Reconciliation test against the real fixture CSV** — extend the existing CSV-7 reconciliation test if one exists, otherwise add to the integration tests directory:
- Import the real Scalable CSV fixture (the same one used by the CSV-7 reconciliation test — check the fixture path in `tests/integration/` or `tests/fixtures/scalable_csv/`) into a fresh tmp repo + a fresh ISIN map.
- Assert every resulting transaction has `source == "scalable_csv"` and `tx.isin is not None`.
- Assert `tx.isin` matches the ISIN of the originating CSV row, keyed by `csv_reference`.

**Totals-preservation test** (belt-and-suspenders, requested by Vivek):
- Build a synthetic v2 portfolio fixture with 5–10 transactions across 3 tickers, plus a matching ISIN map.
- Load it via `json_repo.load_all()` (which will trigger migration to v3). Capture per-ticker share totals and per-ticker EUR cost basis via `compute_positions`.
- Load again (now v3 on disk). Assert all per-ticker share counts and cost-basis EUR amounts are byte-identical to pre-migration. The migration must touch only the `isin` field.

### Step 7: Mappings page tests

Extend `tests/unit/ui/test_mappings_page.py`:
- Edit-save now also rewrites transactions: mock `get_repository()` to return a repo with 2 transactions referencing the ISIN being edited. Assert `rewrite_ticker_for_isin` runs (or assert the repo's `save_all` was called with the correct ticker on the affected rows). Assert the toast text includes `"Rewrote 2 transaction(s)"`.
- Delete-block: when `count_transactions_for_isin` returns > 0, assert (a) `_delete_mapping` is not called, (b) `mappings_feedback` is set to an error with the count in it, (c) `mappings_confirming_delete_isin` is cleared.
- Delete-allow: when count is 0, existing delete path runs (test stays as-is).

---

## Acceptance criteria

- [ ] `Transaction.isin: str | None = None` added; all existing tests still pass.
- [ ] Importer populates `isin` on every Scalable CSV transaction.
- [ ] `migrate_v2_to_v3` exists, with backup, collision-safe abort, and atomic write.
- [ ] `json_repo.SCHEMA_VERSION == 3`; `load_all()` auto-migrates v2 → v3 on first read.
- [ ] `app/services/isin_remap.py` exists with both functions; full unit-test coverage.
- [ ] Mappings page edit-save rewrites transactions and includes count in toast.
- [ ] Mappings page delete is hard-blocked when transactions reference the ISIN.
- [ ] All new tests pass; all existing tests still pass.
- [ ] `ruff check .`, `mypy app/`, `lint-imports` all pass.
- [ ] **Totals-preservation test passes:** per-ticker shares and EUR cost basis are identical pre- and post-migration on the synthetic fixture.

### Manual smoke (post-merge, by Vivek)

- Open the running Streamlit app on `main` after merge.
- Mappings page → edit `US78392B1070` (SK Hynix) → change ticker from `HY9H` to `HY9H.F` → Save. Toast should say `"Rewrote N transaction(s)"` where N matches your SK Hynix transaction count.
- Live Overview → SK Hynix row should now show a live price (yfinance has data for `HY9H.F` — verified 2026-05-16).
- Mappings page → try to delete a mapping that has transactions (e.g. NVDA `US67066G1040`) → expect a blocked error toast with the count.
- Mappings page → delete a mapping with zero transactions (e.g. one of the unmapped-and-now-pruned crypto ETPs if any exist) → expect success.

---

## Out of scope (file as separate tickets)

- **TICKET-CSV-9** — Mappings page fuzzy typeahead via `render_ticker_searchbox`.
- **TICKET-CSV-10** — Live Overview name resolution via ISIN→isin_map lookup; drop hardcoded `_PLACEHOLDER_NAME`; drop CCY column; price hover tooltip showing native currency.
- **Stage 2** — Refactor reads to resolve ticker from ISIN at runtime; eventually drop `Transaction.ticker`. Will be filed when Stage 1 is stable in production use.
- **FIFO hardcoded leftovers** — known issue mentioned in chat; file when the failure mode bites.

---

## Notes / assumptions

- Assumes `Transaction` is constructed by keyword in every call site. If any positional construction exists in the codebase, the new field's position in the model may shift things — agent should grep for `Transaction(` to verify.
- Assumes `ParsedCsvRow` has an `isin` attribute on it already (per CSV-1). If the field is named differently (`isin_code`, `security_isin`, etc.), use the actual name.
- Assumes the v1→v2 migration pattern in `migration.py` includes atomic write with tmp + rename + fsync. If not, **do not** invent a new atomic-write pattern in v2→v3 — match the existing style exactly and file a follow-up ticket to harden both.
- Assumes `tests/unit/services/` exists or can be created. If services tests are colocated elsewhere, match the existing layout.
- The real Scalable CSV fixture path: check `tests/fixtures/scalable_csv/` for `full_export_2026_05_14.csv` or similar (per CSV-7 session log entry).
- Pre-flight collision check on `isin_map.json` was run 2026-05-16 in chat: 0 collisions, 20 mapped, 6 unmapped. If `isin_map.json` is edited between draft time and implementation, re-run the check before starting Step 3.
