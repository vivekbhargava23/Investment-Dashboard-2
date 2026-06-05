# TICKET-CSV-16 — Per-mapping control: Reset tax-kind, Unmap, and Remove-with-purge

**Priority:** HIGH
**Status:** IN_PROGRESS
**Estimated session length:** 2 hr
**Recommended model:** Opus — deletes transactions (money/FIFO), needs the orphan-ticker trap handled correctly.
**Drafted by:** Vivek + Claude Code (session 2026-06-05)
**Implemented by:** TBD
**Milestone:** Investment Panel

---

## Problem

The user has no fine-grained control over an individual ISIN mapping once it exists. On the
Mappings page (`app/ui/pages/mappings.py`) a mapped row offers only **Edit** (remap ticker,
rewrites transactions) and **Delete** — and Delete is **blocked whenever any transaction
references the ISIN** (`mappings.py:317-325`). So for a position the user actually holds but
wants gone (e.g. the three 21shares crypto ETPs, mapped to `CH….SG` with 6 transactions),
there is currently **no path** to remove it. The user also wants to reset a mis-assigned
tax-kind (Aktie vs Aktienfonds) without a full remap.

The underlying trap: the book of record is keyed by **ticker**, while tax classification
data lives on the **ISIN map**. Simply "unmapping" an ISIN that still has transactions
orphans those transactions' ticker and makes the Tax page raise (the TICKET-TAX-1 failure).
Any control action must respect that coupling.

## Solution

Give each mapped row a small set of explicit, safe actions:

1. **Change tax-kind** — inline kind selector + save. Sets `instrument_kind`; keeps ticker,
   transactions, everything else. The cheap fix for "I picked the wrong kind."
2. **Unmap** — mapped → `unmapped`, `ticker=None`, `instrument_kind=None`, keep `name`/
   `last_seen_in_csv`. **Enabled only when zero transactions reference the ISIN** (otherwise
   it would orphan them). When transactions exist, the button is disabled with a tooltip
   pointing to **Remove**.
3. **Remove (purge)** — delete every transaction for the ISIN **and** the map entry, in one
   confirmed action. This is the real "get this position out of my dashboard." Guarded with a
   confirmation that states the transaction count.

### Decisions already made — do not re-litigate

- Transaction deletion is by **ISIN**, not ticker (an ISIN may have been remapped across
  tickers over time; ISIN is the stable identity on the row — `Transaction.isin`).
- **Remove** purges transactions then deletes the map entry. It does **not** leave the entry
  behind as `ignored`; the user asked for it gone. (If they re-import, the ISIN reappears as
  a fresh `unmapped` row, which they can then Ignore — that's the intended re-entry path.)
- Deletion goes through a **service function**, not inline UI logic (ARCHITECTURE: UI calls
  services). FIFO recomputes on next load per the existing replay invariant.
- A backup of `portfolio.json` is written before any purge (reuse the workbench's
  backup helper or the repo's atomic-write + a `.bak`; pick one and document it).

### Execution

1. **Service:** add `delete_transactions_for_isin(tx_repo, isin) -> int` to
   `app/services/isin_remap.py` (sibling of the existing `count_transactions_for_isin` /
   `rewrite_ticker_for_isin`). Loads all, filters out `tx.isin == isin`, `save_all`, returns
   the count removed. Unit-test it.
2. **Mappings UI:** in `_render_mapped_section`, replace the single Delete with the three
   actions above (a compact layout — e.g. an "Edit" + a "Reset ▾"/"Remove" cluster). Wire:
   - Change tax-kind → `model_copy(update={"instrument_kind": kind})` + save.
   - Unmap → status/ticker/kind reset; disabled when `count_transactions_for_isin > 0`.
   - Remove → confirmation card showing the count, then
     `delete_transactions_for_isin(...)` + `_delete_mapping(...)`, with feedback.
3. **Keep existing Delete semantics** for the zero-transaction case folded into Unmap/Remove
   (no separate dead-ended Delete button).
4. **Tests** in `tests/unit/ui/test_mappings_page.py`: change-kind updates the entry; Unmap
   is blocked when transactions exist; Remove purges N transactions and deletes the entry.
5. **Gate.**

## Acceptance criteria

- [ ] `delete_transactions_for_isin` exists, is unit-tested, and returns the count removed.
- [ ] A mapped row can have its tax-kind changed in place without remapping.
- [ ] Unmap is available only when no transactions reference the ISIN.
- [ ] Remove purges the ISIN's transactions and the map entry, behind a count-stating confirm,
      with a `portfolio.json` backup first.
- [ ] The Tax page does not raise after a Remove (no orphaned tickers left behind).
- [ ] `pytest`, `ruff check .`, `mypy app/`, `lint-imports` clean.

## Files likely touched

- `app/services/isin_remap.py`, `app/ui/pages/mappings.py`
- `tests/unit/test_isin_remap.py` (new or extend), `tests/unit/ui/test_mappings_page.py`

## Out of scope

- Bulk multi-row purge. One ISIN at a time (the user has a handful).
- Full "erase everything" reset — TICKET-CSV-17.
- The importer consolidation — TICKET-CSV-15.

## Notes / assumptions

- Assumes `TransactionRepository.save_all` triggers the FIFO replay/recompute on next read
  (per ARCHITECTURE invariant 1). Confirm before relying on it for the purge path.
- Assumes `Transaction.isin` is populated for CSV-sourced rows (it is, set in the apply path).
  Manually-added transactions may have `isin=None`; those are unaffected by a purge and that
  is correct.
- The three 21shares ISINs (`CH0491507486`, `CH1109575535`, `CH1129538448`) are the canonical
  post-merge smoke target. Do not hardcode them.
