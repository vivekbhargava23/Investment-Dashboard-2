# TICKET-SYNC-3 — Manage Portfolio: Scalable rows are read-only except Notes

**Priority:** HIGH
**Status:** IN_PROGRESS
**Milestone:** Investment Panel
**Recommended model:** Sonnet — one page, one pure helper, clear tests.
**Estimated session length:** 1 hr
**Drafted by:** Vivek + Claude (Cowork session 2026-09-03)
**Depends on:** TICKET-SYNC-2.

> **After this ticket merges:** a transaction with `source == "scalable_csv"` can no longer have its ticker, type, date, shares, total or fees changed on the Manage page. Only Notes is editable. The form says where to change the ticker instead.

## Problem
`_handle_edit_submit` rebuilds the transaction via `build_transaction` and copies back only
`id` and `notes`. Editing a Scalable row turns it into `source: manual`, drops
`csv_reference`, `isin` and `fees_native`, and re-rounds the price. Dedupe on the next
import then depends on a content hash and can produce duplicates. Per ADR-014 and the Sync
design, broker rows are the book and are not edited in the app.

## Execution — one commit per step

### Step 1 — pure helper
File `app/services/trading.py`, add:
```python
def is_broker_row(tx: Transaction) -> bool:
    """True for transactions that came from a broker file and must not be edited (ADR-014)."""
    return tx.source == "scalable_csv"

def with_notes(tx: Transaction, notes: str | None) -> Transaction:
    """Return a copy with only `notes` changed. Everything else, including provenance, is preserved."""
    return tx.model_copy(update={"notes": notes})
```
Tests in `tests/unit/ui/test_manage_form_pipeline.py`: `is_broker_row` true/false;
`with_notes` preserves `source`, `isin`, `csv_reference`, `fees_native`, `price_native`,
`id`, and changes `notes`.

### Step 2 — edit form branches once
File `app/ui/pages/manage.py`, `_render_edit_form`: at the top, `if is_broker_row(tx):`
render `_render_broker_notes_form(tx)` and return. The new function shows a caption
`Imported from Scalable Capital · <ticker> · <isin or '—'>. Ticker, shares and amounts come
from the CSV. To change the ticker, change the ISIN mapping on the Sync tab.` (until
SYNC-6B ships say "ISIN Mappings page"), a read-only summary line (type, date, shares, cost),
one `st.text_input("Notes", value=tx.notes or "")` inside a form, and Save/Cancel. Save
calls `get_repository().update(with_notes(tx, notes or None))`, clears `st.cache_data`,
sets `manage_feedback` and reruns. The existing form is unchanged for manual rows.

### Step 3 — broker rows cannot be deleted one by one
In `_render_transactions_table`, if any selected row `is_broker_row`, disable the Delete
button with help text `Scalable rows are the book — they would come back on the next sync.
Use the Danger zone to erase imported data.` The Danger zone is unchanged.

### Step 4 — tests
`tests/unit/ui/test_manage_page.py`: a render test (existing monkeypatch pattern) that for a
scalable tx the edit surface contains the caption text and no searchbox call; for a manual tx
the searchbox is rendered.

### Step 5 — gate, commit, session log, screenshots (before/after of the edit form for a
Scalable row), PR.

## Acceptance criteria
- [ ] Editing a Scalable row can only change Notes; the saved JSON keeps `source`,
      `csv_reference`, `isin`, `fees_native`, `price_native` byte-for-byte (test via
      `with_notes`).
- [ ] Manual rows keep the current edit form; Delete is disabled when a Scalable row is selected.
- [ ] Gate clean; screenshots in PR.

## Out of scope
The Sync tab itself.
