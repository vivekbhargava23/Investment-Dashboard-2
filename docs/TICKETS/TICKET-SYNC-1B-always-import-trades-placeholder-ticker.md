# TICKET-SYNC-1B — Always import executed trades; placeholder ticker for unmapped ISINs; last-trade valuation

**Priority:** CRITICAL
**Milestone:** Investment Panel
**Recommended model:** Opus — changes the planner's import scope and adds a valuation fallback (money code).
**Estimated session length:** 1.5 hr
**Drafted by:** Vivek + Claude (Cowork session 2026-09-03, after second review)
**Depends on:** TICKET-SYNC-1.
**Required reading:** ADR-014 rules 7–8.

> **After this ticket merges:** uploading a CSV puts every executed Buy / Sell / Savings-plan row into the book regardless of ISIN mapping. Unmapped ISINs get the ISIN as ticker; the Overview values such positions at their last trade price and says so. Picking a feed later only changes the ticker (SYNC-2), never which trades exist.

## Execution — one commit per step

### Step 1 — planner
`app/adapters/scalable_csv/planner.py::plan_import`: remove the two branches that emit
`IGNORED_ISIN` and `UNMAPPED_ISIN` with `PlannedAction.SKIP`. New rule after the
already-imported check:
```python
mapping = isin_doc.entries.get(row.isin)
ticker = mapping.ticker if (mapping is not None and mapping.status == "mapped" and mapping.ticker) else row.isin.upper()
feed_state = "mapped" | "unmapped" | "ignored"   # display only; "unmapped" when no entry
```
Then content-hash / conflict / validation / NEW exactly as today with `ticker`. Rows with an
empty ISIN and an in-scope type → `VALIDATION_ERROR` ("row has no ISIN"). Add
`feed_state: Literal["mapped","unmapped","ignored"] | None = None` to `PlannedRow`
(`app/domain/csv_import.py`). Keep the `RowStatus` members for now (SYNC-7 removes the two
dead ones) but nothing may produce them; add a test asserting that.

Tests `tests/unit/test_scalable_csv_planner.py` (create if missing): unmapped ISIN → NEW
with `proposed_ticker == isin`, `feed_state == "unmapped"`; ignored → NEW with
`feed_state == "ignored"`; mapped → mapping ticker; missing ISIN → VALIDATION_ERROR.

### Step 2 — workbench display (interim, until SYNC-6B)
`app/ui/pages/import_workbench.py`: remove `UNMAPPED_ISIN`/`IGNORED_ISIN` from
`_BLOCKED_STATUSES`, `_SILENT_STATUSES`, the filter chips and `_STATUS_COLORS`; the
"Map ISINs manually" panel lists ISINs whose rows have `feed_state == "unmapped"`. After a
manual Save call `rewrite_ticker_for_isin` so placeholder rows pick up the ticker (SYNC-2
replaces this with `change_feed`). Ticker column shows the placeholder with a `(no feed)`
suffix.

### Step 3 — last-trade valuation fallback
`app/domain/positions.py::LivePosition`: add `price_source: Literal["live","last_trade"] = "live"`.
`app/services/valuation.py::compute_live_positions`: where a `PriceUnavailableError` (or a
missing entry from `get_current_prices`) currently leaves a position unpriced, use the latest
open lot's `price_native` with the lot's stored `fx_rate_eur` as the current price, set
`price_source="last_trade"`, and include it in totals. `app/ui/pages/overview.py`: such rows
show the price cell as `€x · last trade` (existing greyed style) and the summary footnote
gains `n position(s) valued at last trade price`. Tests in
`tests/unit/services/test_valuation*.py` with `FakePriceProvider` missing the ticker: value
equals shares × last lot price, `price_source == "last_trade"`, total includes it.

### Step 4 — gate, commit, session log, screenshots (Overview with one placeholder
position), PR.

## Acceptance criteria
- [ ] A CSV whose ISINs are all unmapped imports every executed trade; positions appear on
      the Overview valued at last trade price with the label.
- [ ] No code path produces `UNMAPPED_ISIN` or `IGNORED_ISIN` (test).
- [ ] Gate clean; screenshot in the PR.

## Out of scope
Replacing the mapping Save path (SYNC-2); the Sync page.
