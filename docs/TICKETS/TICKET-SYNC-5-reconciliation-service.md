# TICKET-SYNC-5 — Reconciliation: shares per ISIN in the CSV vs in the book, with a cause

**Priority:** HIGH
**Milestone:** Investment Panel
**Recommended model:** Sonnet — pure domain logic over existing plan rows and transactions.
**Estimated session length:** 1.5 hr
**Drafted by:** Vivek + Claude (Cowork session 2026-09-03)
**Depends on:** TICKET-SYNC-1, TICKET-SYNC-1B.
**Can run independently of:** TICKET-SYNC-2, TICKET-SYNC-3, and TICKET-SYNC-4.

> **After this ticket merges:** one pure function answers "does the dashboard hold what Scalable holds?" per ISIN, and if not, why — in a sentence a new user understands.

## Rules (fixed, from docs/DESIGN/SYNC-TAB.md)
- Expected shares from the CSV, per ISIN, over `PlannedRow`s whose original CSV status was
  Executed (the planner already marks non-executed rows `cancelled_or_expired`; exclude those):
  `Buy`, `Savings plan` → `+shares`; `Sell` → `−shares`; `Security transfer` → `+shares` as
  signed in the file. Rows with `shares None` contribute 0.
- Book shares per ISIN = Σ buy shares − Σ sell shares over transactions with that `isin`.
- `diff = shares_csv − shares_book`, compared with `abs(diff) < Decimal("0.000001")`.
- Cause, first match wins:
  1. any plan row for the ISIN with status `validation_error` → `"N rows failed validation — see Details"`
  2. (guard, not a cause) expected shares use Executed rows only — test that a cancelled row changes nothing
  3. (reserved) unmapped/ignored ISINs are imported since SYNC-1B and are never a cause
  4. net Security-transfer shares for the ISIN ≠ 0 → `"transfer imbalance: net ±x shares"`
  5. any transaction whose `id` equals a CSV reference for this ISIN but `source != "scalable_csv"` → `"edited manually on the Manage page"`
  6. any plan row for the ISIN with `csv_type == "Corporate action"` → `"corporate action on <date> — not imported"`
  7. any `source == "manual"` transaction whose ticker equals this ISIN's mapped ticker → `"includes a manual entry for the same instrument (n shares)"`
  8. any plan row for the ISIN with status `conflict_with_manual` → `"possible duplicate of a manual entry — decide on the Sync tab"`
  9. else → `"unknown — check Details"` (must be rare; the verification checklist treats it as a failure to investigate)
- `reconcile(..., partial: bool = False)`: when True return [] (the caller shows the partial-file task instead).
- Name = description of the latest plan row for the ISIN.

## Execution — one commit per step

### Step 1 — domain
New file `app/domain/reconcile.py`:
```python
class ReconcileRow(BaseModel):  # frozen
    isin: str; name: str; shares_csv: Decimal; shares_book: Decimal; diff: Decimal
    matches: bool; cause: str | None; last_trade_price_eur: Decimal | None

def reconcile(plan_rows: Sequence[PlannedRow], transactions: Sequence[Transaction]) -> list[ReconcileRow]
```
`last_trade_price_eur` = price of the latest Buy/Sell/Savings plan plan row for the ISIN
(used by the UI to rank tasks by € impact). Output sorted by `abs(diff) × (last price or 1)`
descending, then ISIN.

Tests `tests/unit/domain/test_reconcile.py`, one per cause plus the all-match case and the
transfer-pair-nets-to-zero case. Build `PlannedRow`s with the domain constructor directly;
no CSV parsing in these tests.

### Step 2 — service wrapper (thin)
`app/services/reconcile.py::reconcile_book(plan, tx_repo) -> list[ReconcileRow]` — loads
transactions from the port and calls the domain function. One test with an in-memory fake
repository (add `tests/fakes/repository.py` if none exists: `FakeTransactionRepository`
holding a list).

### Step 3 — gate, commit, session log, PR.

## Acceptance criteria
- [ ] Every cause string above (1–9) is produced by exactly one test; `partial=True` returns [].
- [ ] Domain file imports nothing outside stdlib/pydantic/app.domain.
- [ ] Gate clean.

## Out of scope
Rendering; the FIFO "sell exceeds shares" detection (SYNC-6B catches
`SellExceedsOpenSharesError` per ISIN at render time).
