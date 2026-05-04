# TICKET-009 — Manage Portfolio page (add / edit / delete transactions)

**Status:** IN_REVIEW
**Priority:** P1
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-03)
**Implemented by:** _pending_
**Depends on:** TICKETs 001 (domain), 002 (FIFO), 003 (repo), 004-005 (yfinance for FX auto-fill), 006 (valuation service), 007 (UI shell), 008 (Live Overview wiring + cache discipline)

> **After this ticket merges, the app is fully self-sufficient.** No more seed scripts, no more hand-editing JSON. You can add a new buy via the UI, edit any existing transaction, delete one, and the Live Overview reflects the change immediately.

---

## Problem

We have a working dashboard (TICKET-008) but the only way to mutate the portfolio is the seed script (one-off) or hand-editing `data/portfolio.json` (painful, error-prone, no validation). This ticket builds the **CRUD UI**: add, edit, delete transactions, with FIFO-aware pre-trade validation and FX auto-fill.

After this ticket lands, the app's core daily-use loop works end-to-end without touching the filesystem or the terminal.

---

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-03:

1. **Single-page layout, two sections.** Top = Add Transaction form. Bottom = All Transactions table with per-row edit/delete actions. No tabs, no nested pages — keeps the affordances obvious.

2. **FX rate auto-fill on currency + date selection.** When the user picks USD + a trade date, the form calls `fx_provider.get_historical_rate(USD, EUR, date)` and pre-fills the FX field. EUR auto-fills `1.0` and disables the field. Failures show a yellow warning and leave the field editable.

3. **Pre-trade sell validation (FIFO guard) at the form boundary.** SELLs are validated against current open shares BEFORE writing. The FIFO engine (TICKET-002) raises `SellExceedsOpenSharesError` on invalid input — we catch it at the form, never let it propagate to storage. This is exactly where the "engine assumes valid input" contract is enforced.

4. **Cache invalidation is explicit and asymmetric.** Every CRUD operation clears `st.cache_data` (so Live Overview recomputes). ADD also clears adapter caches (new ticker may need a fresh price fetch). EDIT and DELETE on existing tickers skip the adapter cache clear (prices haven't changed). This pattern is documented and reused by TICKET-015 (Lot Ledger edit-in-place).

5. **Edit mode uses `st.session_state` to track the in-flight transaction id.** Streamlit's render-on-rerun model means we can't use Python local variables to persist UI state across clicks. The convention: `st.session_state.editing_tx_id: str | None`. When `None`, no edit dialog is open. When set, the edit form is rendered pre-filled with that transaction's values.

6. **Delete uses a confirmation step, not a one-click destructive action.** Click trash → row collapses to "Are you sure? [Confirm Delete] [Cancel]" inline → confirm performs the delete. Prevents accidental data loss. The confirmation state lives in `st.session_state.deleting_tx_id`.

7. **The Add and Edit forms share components but not state.** Two separate `st.form` containers, each with its own submit handler. Sharing a single form across "add" and "edit" modes leads to ambiguous form state on submit. Two forms = two clear code paths.

8. **No "preview tax impact" in this ticket.** The pre-trade sell simulator with full tax-impact breakdown is TICKET-012, a richer feature with its own UI. TICKET-009 only enforces the "is this sell valid at all?" check. A future enhancement could add a "Preview tax impact →" button on the form that links to TICKET-012's simulator.

---

## Acceptance criteria

### `app/ui/pages/manage.py` — replaces TICKET-007 placeholder

#### Module-level state initialization

- [ ] At the top of `render()`:
  ```python
  if "editing_tx_id" not in st.session_state:
      st.session_state.editing_tx_id = None
  if "deleting_tx_id" not in st.session_state:
      st.session_state.deleting_tx_id = None
  if "form_feedback" not in st.session_state:
      st.session_state.form_feedback = None  # tuple[Literal["success","error","warning"], str] | None
  ```
- [ ] At the top of `render()`, after state init: render any pending `form_feedback` via `st.success`/`st.error`/`st.warning`, then clear it. This ensures feedback survives one rerun (the rerun after a successful submit) but doesn't persist further.

#### Top section — Add Transaction form

- [ ] Section header: `<h2>Add Transaction</h2>`.
- [ ] Wrapped in `st.form(key="add_tx_form", clear_on_submit=True)`.
- [ ] Field layout: 3-column row 1 (Ticker, Type, Trade Date), 3-column row 2 (Shares, Price Native, Currency), 3-column row 3 (FX Rate, Fees, Notes spans columns 2-3).

##### Field-by-field specification

- [ ] **Ticker** — `st.text_input("Ticker")`. On blur, normalize to uppercase. Placeholder: `"e.g. NVDA, RHM.DE"`.
- [ ] **Type** — `st.radio("Type", ["Buy", "Sell"], horizontal=True)`. Default: `"Buy"`.
- [ ] **Trade Date** — `st.date_input("Trade date")`. Default: today. Max value: today (no future dates allowed). Min value: `date(2000, 1, 1)` (sane lower bound).
- [ ] **Shares** — `st.number_input("Shares", min_value=0.0001, step=0.0001, format="%.4f")`. Default: `1.0`.
- [ ] **Price Native** — `st.number_input("Price (per share)", min_value=0.01, step=0.01, format="%.4f")`. Default: `0.01`. Label updates dynamically based on currency: `"Price (per share, USD)"` or `"Price (per share, EUR)"`. Implementation: build the label string from the selected currency before rendering.
- [ ] **Currency** — `st.selectbox("Currency", ["EUR", "USD"], index=0)`. The selectbox does NOT auto-infer from ticker — that's a nice-to-have we skip. The user picks explicitly. (Future enhancement: pre-select based on ticker suffix.)
- [ ] **FX Rate** — `st.number_input("FX rate (EUR per 1 native)", min_value=0.0001, step=0.0001, format="%.6f")`. Disabled when Currency=EUR (auto-set to `1.0`). For USD: pre-filled via FX adapter on form render — see "FX auto-fill flow" below.
- [ ] **Fees** — `st.number_input("Fees (optional)", min_value=0.0, step=0.01, format="%.4f")`. Default: `0.0`. Currency matches Price Native.
- [ ] **Notes** — `st.text_input("Notes (optional)")`. Default: empty.

##### FX auto-fill flow

- [ ] **The challenge:** Streamlit forms don't update fields based on other field changes within the same form. Field values are only read on submit. So we can't truly "auto-fill on date change" inside `st.form`.
- [ ] **The pragmatic approach:** Render the FX rate field with the **current** auto-fill value as the default. The default is computed BEFORE the form is rendered, based on:
  - The trade date currently in `st.session_state.add_form_trade_date` (or today if not set)
  - The currency currently in `st.session_state.add_form_currency` (or EUR if not set)
- [ ] When the user changes date or currency *and clicks submit*, the form re-renders with new defaults on the next interaction.
- [ ] **Alternative if the above feels janky:** Move the FX field OUTSIDE the `st.form` (as a standalone `st.number_input`), so it can react to date/currency changes immediately. Submit reads its current value via `st.session_state`. This gives true auto-fill at the cost of breaking the "all-in-one-form" pattern.
- [ ] **Decision:** start with the in-form approach (simpler). If the UX is bad in practice, switch to the alternative in a follow-up ticket. Document the choice with a comment in `manage.py`.
- [ ] On FX adapter failure: catch `FxRateUnavailableError`, set the default to `0.92` (a reasonable USD/EUR placeholder), and prepend a warning to the form: `"⚠ Could not auto-fill FX rate from yfinance — please verify"`.

##### Submit handler

- [ ] On submit:
  1. Read all field values.
  2. Validate ticker format (non-empty, uppercase). On failure: set `form_feedback = ("error", "...")` and rerun.
  3. Validate that EUR currency has FX rate exactly 1.0. If user manually changed it, set `fx_rate = 1.0` and ignore.
  4. Build a `Money` for `price_native` and (if non-zero) `fees_native`.
  5. Build a `Transaction` via Pydantic. On `ValidationError`: surface a friendly error message.
  6. **If type is SELL: pre-trade FIFO validation.** See "FIFO sell validation" below.
  7. Call `repository.add(transaction)`.
  8. Set `form_feedback = ("success", f"Added {type} of {shares} {ticker}")`.
  9. Clear caches: `st.cache_data.clear()` AND (because it's an add) `clear_caches(get_price_provider(), get_fx_provider())`.
  10. `st.rerun()`.

##### FIFO sell validation

- [ ] When type=SELL, before `repository.add()`:
  ```python
  existing_transactions = repository.load_all()
  proposed_transactions = [*existing_transactions, new_transaction]
  try:
      compute_positions(proposed_transactions)
  except SellExceedsOpenSharesError as e:
      # Compute current open shares for the helpful message
      current_positions = compute_positions(existing_transactions)
      open_shares = current_positions.get(ticker).open_shares if ticker in current_positions else Decimal("0")
      st.session_state.form_feedback = ("error",
          f"Cannot sell {shares} of {ticker} — you only have {open_shares} open shares.")
      st.rerun()
      return
  ```
- [ ] Handle the case where the ticker has no prior transactions (open_shares = 0).
- [ ] The validation runs the FIFO engine over the proposed full set. If it raises, the new transaction is rejected without being persisted.

#### Bottom section — All Transactions table with per-row actions

- [ ] Section header: `<h2>All Transactions</h2>` with subtitle showing the count: `f"{len(transactions)} total · sorted by trade date (newest first)"`.
- [ ] **Filter row** (above table): `st.text_input("Filter by ticker (substring match)")`. Empty = show all. Filter is case-insensitive substring match against `tx.ticker`.
- [ ] Table columns: Date, Ticker, Type, Shares, Price, Currency, Cost (€), FX Rate, Notes, Actions.
- [ ] **Cost (€)** column = `tx.cost_eur` (the helper property from TICKET-001). Computed, read-only.
- [ ] **Actions** column has two icon buttons per row: ✏️ (edit) and 🗑️ (delete). Clicking each sets the corresponding session_state and reruns.
- [ ] Sort: by `trade_date` descending, ties broken by `id` ascending.
- [ ] Implemented as a hand-built HTML table (same approach as TICKET-008's positions table) because Streamlit's native dataframe doesn't support inline action buttons. The buttons are rendered as `st.button(key=f"edit_{tx.id}")` in a Streamlit column adjacent to the markdown table — see "Action button placement" below.

##### Action button placement

- [ ] **The constraint:** an HTML `<table>` rendered via `st.markdown` cannot embed Streamlit widgets. Streamlit widgets must live in Streamlit containers.
- [ ] **The solution:** render two parallel structures:
  1. The visual table as HTML markdown (data only, no buttons).
  2. A list of compact rows below or to the side, where each row has just the ticker + date + edit/delete buttons.
- [ ] **Better solution (preferred):** use `st.columns` per row. For each transaction, render a row with N data columns + 2 button columns. Drop the HTML table approach for this page only (positions table stays HTML because it has no actions).
  ```python
  for tx in transactions:
      cols = st.columns([2, 1.5, 1, 1, 1.5, 1, 1.5, 1, 2, 0.5, 0.5])
      cols[0].write(format_date(tx.trade_date))
      cols[1].write(tx.ticker)
      # ... etc
      if cols[9].button("✏️", key=f"edit_{tx.id}"):
          st.session_state.editing_tx_id = tx.id
          st.rerun()
      if cols[10].button("🗑️", key=f"delete_{tx.id}"):
          st.session_state.deleting_tx_id = tx.id
          st.rerun()
  ```
- [ ] CSS in `dark.css` adjusts column padding/alignment so the layout doesn't look like a generic Streamlit form. New CSS class `.tx-row` for the row container.
- [ ] **Header row** is rendered the same way (one `st.columns` call with bold labels via markdown).

#### Edit mode — when `st.session_state.editing_tx_id is not None`

- [ ] Render an `st.form(key="edit_tx_form")` ABOVE the All Transactions table (or in an `st.expander("Editing transaction X", expanded=True)`).
- [ ] All same fields as the Add form, pre-populated from the existing transaction.
- [ ] **The transaction id is preserved on edit.** Internally: `update()` replaces the transaction by id (TICKET-003 already supports this).
- [ ] Two submit buttons: "Save changes" and "Cancel."
- [ ] On Save:
  1. Validate as for Add.
  2. If type=SELL: re-run FIFO validation (with the edit applied) — the same logic as Add but the proposed list excludes the original transaction and includes the edited one.
  3. Build the new `Transaction` (same id, new fields).
  4. `repository.update(new_transaction)`.
  5. Clear `st.cache_data` (NOT adapter cache — same ticker, prices unchanged).
  6. Set `editing_tx_id = None`. Set success feedback.
  7. Rerun.
- [ ] On Cancel: set `editing_tx_id = None`, rerun.
- [ ] **Edge case: editing a transaction that other transactions depend on.** Example: editing an old buy that has subsequent sells consuming from it. Editing the buy's shares may invalidate those sells. The FIFO engine catches this — `compute_positions()` raises if the proposed list is internally inconsistent. Show the error and refuse the edit.

#### Delete mode — when `st.session_state.deleting_tx_id is not None`

- [ ] Render a confirmation banner ABOVE the All Transactions table:
  ```
  ⚠ Delete transaction ABC123 (BUY 10 NVDA on 2025-05-12)?
  [Confirm Delete] [Cancel]
  ```
- [ ] On Confirm Delete:
  1. **FIFO validity check:** if deleting this transaction breaks the FIFO chain (e.g., deleting an old buy that subsequent sells depend on), the deletion would create an inconsistent state. Run `compute_positions(transactions_without_this_one)`. If it raises, refuse with a clear message: `"Cannot delete — subsequent sells depend on this buy. Delete or edit those first."`
  2. If valid: `repository.delete(tx_id)`.
  3. Clear `st.cache_data` (NOT adapter cache).
  4. Set `deleting_tx_id = None`. Set success feedback.
  5. Rerun.
- [ ] On Cancel: set `deleting_tx_id = None`, rerun.

### `app/ui/wiring.py` — small extension

- [ ] Already exists from TICKET-008. No changes needed in this ticket. The page imports `get_repository`, `get_price_provider`, `get_fx_provider` directly.

### Tests

#### `tests/integration/test_manage_crud.py`

These tests do not run Streamlit — they test the pure-data flow that the page calls into. The Streamlit rendering itself is verified manually.

- [ ] **Add a buy → repository persists it**: construct a fresh repo, add a Transaction via `repository.add()`, reload, find it.
- [ ] **Add a sell that exceeds open shares → FIFO validation rejects**: prime repo with 5 shares of NVDA, attempt to add a sell of 10. Build `[*existing, new_sell]` and call `compute_positions` — assert `SellExceedsOpenSharesError`.
- [ ] **Add a valid partial sell → FIFO validation passes**: prime repo with 10 shares NVDA, add sell of 4, `compute_positions` succeeds.
- [ ] **Edit a buy preserves id**: add a buy, retrieve it, build a modified copy with same id but different shares, `repository.update()` it, reload, confirm same id and new shares.
- [ ] **Edit a buy that breaks FIFO → caught by validation**: add buy of 10 NVDA, add sell of 8. Now edit the buy down to 5 shares. `compute_positions` over the proposed full list should raise — confirm we catch it.
- [ ] **Delete a transaction**: add 3 transactions, delete the middle one, reload, confirm 2 remain in correct order.
- [ ] **Delete a buy that subsequent sells depend on → caught**: add buy of 10 NVDA, add sell of 4. Try to compute_positions on `[sell]` (without the buy). Confirm `SellExceedsOpenSharesError`.

#### `tests/unit/ui/test_manage_page.py`

- [ ] **Helper function `_propose_transactions_for_validation(existing, new)` returns a list with new appended**: smoke test (this helper, if extracted, should exist in manage.py).
- [ ] **Helper function `_propose_transactions_for_edit(existing, edited_tx)` replaces by id**: smoke test.
- [ ] **Helper function `_filter_by_ticker_substring(transactions, query)` works case-insensitively**: smoke test.

#### Manual review checklist (in PR description)

- [ ] Add a new transaction via the form — appears in the table immediately
- [ ] FX field pre-fills for USD currencies; equals 1.0 for EUR
- [ ] Submitting an over-sized SELL shows an error with current open shares
- [ ] Edit a transaction — saved changes persist and the table updates
- [ ] Delete confirmation appears; cancel works; confirm works
- [ ] Live Overview page shows updated values after add/edit/delete (cache cleared correctly)
- [ ] Filter by ticker substring works
- [ ] Form clears on successful submit; error messages appear and clear correctly
- [ ] Currency=EUR disables the FX rate field

### Lints / quality
- [ ] `pytest` — all tests pass; integration tests skipped by default unless `--run-integration`
- [ ] `ruff check .` — passes
- [ ] `mypy app/` — passes; UI standard mode
- [ ] `lint-imports` — passes; `app.ui.pages.manage` imports from `app.services.*`, `app.domain.*`, `app.ui.*`. NOT from `app.adapters.*` (only via wiring.py).

### State updates (per CLAUDE.md session-end ritual)
- [ ] `docs/SESSION_LOG.md` appended
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-009 → IN_REVIEW)
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-009 row → IN_REVIEW)
- [ ] Ticket file `Status: IN_REVIEW`
- [ ] PR opened via `gh pr create --fill --base main`

---

## Files created

```
tests/integration/test_manage_crud.py
tests/unit/ui/test_manage_page.py
```

## Files modified

```
app/ui/pages/manage.py          ← replaces TICKET-007 placeholder with full CRUD
app/ui/styles/dark.css          ← add .tx-row class for table rows; refine button styles
docs/TICKETS/BACKLOG.md         ← TICKET-009 → IN_REVIEW
README.md                       ← optional: note that the seed script is no longer needed for daily use
```

---

## Out of scope

- **Pre-trade tax impact preview** — TICKET-012, separate page. The form here only enforces "is this sell legal under FIFO?", not "what's the tax bill?"
- **Bulk import from broker CSV** — future ticket. Right now: seed CSV (TICKET-008) + manual UI entry.
- **Transaction history audit log** — beyond what git already gives via `data/portfolio.json` history. No app-level audit trail.
- **Undo button after delete** — git history of `data/portfolio.json` is the recovery mechanism. If you delete by mistake: `git checkout HEAD -- data/portfolio.json`.
- **Drag-to-reorder transactions** — order is determined by date+id in the FIFO engine; no manual reordering.
- **Bulk delete** — one at a time. If you need bulk: hand-edit JSON or write a one-off script.
- **Add transaction types beyond BUY and SELL** (DIVIDEND, SPLIT, FEE) — out of scope until those types exist in the domain (none yet).
- **Currency support beyond EUR/USD** — same as TICKET-008.

---

## Notes (architectural and methodological — for future AI sessions)

### Why two separate `st.form` containers (Add and Edit)

The naive approach is one form that handles both modes via a session_state flag. In practice:
- Pre-population logic gets messy (which fields read from session_state vs from a transaction object?)
- Submit handler has two completely different paths (add() vs update()) that share no logic
- Field defaults differ: Add resets after submit; Edit shouldn't

Two forms, two clear code paths, ~60 lines of duplication that a future refactor could DRY up if it became painful (it won't).

### Why FIFO validation runs at the form, not in the repository

The repository is a thin persistence wrapper. It accepts any valid `Transaction` model. Adding business rules ("you can't sell more than you have") into the repository:
- Tightly couples persistence to domain logic
- Makes the repository hard to swap (a SQLite repo would re-implement the same check)
- Violates the "FIFO engine is the authority on what's a valid transaction sequence" architecture

The form runs `compute_positions` on the proposed sequence. If it raises, the form rejects the input. The repository never sees invalid state.

### Why edit and delete on existing tickers don't clear adapter caches

Adapter cache holds prices and FX rates. Those don't change when the user edits a transaction's shares or notes. Clearing the adapter cache would force a refetch from yfinance — slower, with no benefit.

The exception is ADD: if the user adds a transaction for a brand-new ticker (not previously held), we *do* want to fetch its price ASAP. Conservative approach: clear adapter cache on every Add. (More precise: only clear if the ticker is new. We don't bother — Add is rare.)

### Why the deletion check uses `compute_positions` and not a simple count

A naive "do any sells reference this buy?" check would require knowing which buy each sell consumed from — which is exactly what FIFO computes. Re-using the FIFO engine for the validity check means there's exactly one source of truth for "is this transaction sequence consistent?"

### Why the edit and delete actions live in `st.columns`, not native dataframes

Streamlit's `st.dataframe` and `st.data_editor` don't support inline action buttons. `st.data_editor` allows row deletion via a checkbox + delete button at the table level, which is functional but feels generic — the mockup wants per-row controls.

`st.columns` per row gives full control. Cost: 30+ Streamlit elements per row × N rows = potential rerender slowdown for very large portfolios. Not a problem at <100 transactions; we'll address later if it becomes one.

### How TICKET-015 (Lot Ledger edit-in-place) extends this pattern

TICKET-015 will let the user click a row in the Lot Ledger table to edit a *lot* (which is really an underlying buy transaction). The pattern is:
1. Click row → set `st.session_state.editing_lot_id`
2. Render edit form
3. On save: same FIFO validation, same cache invalidation
4. On cancel: clear session state

The form fields are different (lots have their own view) but the state-management pattern is identical. TICKET-015 references this ticket rather than re-deriving the pattern.

### Why no "preview tax impact" button here

The pre-trade sell simulator (TICKET-012) is its own ticket because it does more than validate FIFO — it shows:
- Which lots will be consumed (FIFO breakdown)
- Realised gain in EUR per lot
- Sparerpauschbetrag impact (how much of the €1,000 allowance is consumed)
- Whether the sell pushes you over the allowance into Abgeltungsteuer territory
- Loss-harvesting opportunities (if a position is at a loss, what's the offset?)

That's a richer page-level feature. TICKET-009 is the daily-use CRUD; TICKET-012 is the planning tool. Mixing them would scope-creep TICKET-009 by ~3x.

### Methodology note (for future AI sessions)

This is the second UI ticket using the patterns established in TICKETs 007 and 008:
- Page in `app/ui/pages/<name>.py` with `render()` function
- Wiring via `app/ui/wiring.py` singletons
- Cache discipline: `st.cache_data.clear()` after mutations; adapter cache cleared selectively
- `st.session_state` for in-flight UI state (which row is being edited)
- Manual review checklist in the PR for things automated tests can't verify

TICKETs 011 (Tax Dashboard), 014 (Performance), 015 (Lot Ledger), 017 (Decision Gates), 018 (Behavioural Ledger) all follow this template. Each subsequent UI ticket should be 30-40% shorter than this one because the patterns are now well-documented.
