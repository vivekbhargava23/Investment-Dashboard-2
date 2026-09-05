# TICKET-SYNC-7 — Close the loop on the Sync tab: corporate actions, write-off, one instrument card, session-safe undo, retire the old pages

**Priority:** HIGH
**Status:** IN_PROGRESS
**Milestone:** Investment Panel
**Recommended model:** Opus — touches FIFO-relevant import scope, reconciliation, undo correctness and a page deletion in one PR; every step has a real-data check.
**Estimated session length:** 4–5 hr. One PR, one commit per step so each step reads on its own.
**Drafted by:** Vivek + Claude (Cowork session 2026-09-03; rewritten 2026-09-05 after Vivek's review of the first real import)
**Depends on:** TICKET-SYNC-6B (PR #225) merged.
**Required reading:** `docs/DESIGN/SYNC-TAB.md` in full, ADR-014 in full, `app/ui/pages/sync.py`, `app/services/sync.py`, `app/domain/reconcile.py`, `app/ui/pages/mappings.py`, and the 2026-09-04 SYNC-6B session-log entries (three follow-ups). The findings below come from those; do not re-derive them.

> **After this ticket merges:** there is one door for broker data — the Sync tab. A knocked-out
> certificate that Scalable booked as a corporate action closes itself on upload. A holding the
> broker never closed can be written off to €0 with its history kept. Every instrument is edited
> on one card with three independent controls (feed, tax kind, remove) and plain-word states.
> Every write made while an export is open — including Ignore, Repair, tax kind and write-off —
> belongs to the sync session, so **Undo last sync** stays available. The Import CSV workbench and
> ISIN Mappings pages, their sidebar entries, tests and screenshots are gone.

## Why this ticket is bigger than "retire two pages"

Vivek reviewed the Sync tab after the first real import (2026-09-05). Verdict: the core
(drop → import → tasks → undo) works, but the door cannot be closed behind it yet:

1. **Ignore and Repair disable Undo.** `sync.py::_ignore` and the Repair button write
   `isin_map.json` / `portfolio.json` directly, without a session log entry. `undo_enabled`
   compares the last log entry's md5s to the files, so the first Ignore click greys out
   "Undo last sync" with "your data changed after the last sync". The design says every action
   while the file is open belongs to the session.
2. **A holding without a feed cannot be given a tax kind.** The mapper's Save is disabled
   until a ticker match exists, so the two feedless holdings (HSBC Apple turbo, CoinShares
   Algorand ETP) had their kind set by migration. That is what took the Tax Dashboard down.
   Feed, tax kind and ignore are three decisions welded into one row.
3. **Corporate actions are never imported, so a knock-out never closes.** Real data:
   `data/scalable_raw.csv` rows 141–142 (reference `WWUM 00477772743`) are a Corporate action
   pair for DE000HT41XN9 — Security leg `-26` shares at `0,001`, Cash leg `+0,03`. The book
   still holds 26 shares valued at the last trade (€3.00 → €78 of phantom value) and
   `reconcile._shares_csv` skips the row on the CSV side too, so 26 = 26 "matches". The
   design's "corporate actions are never imported" was an assumption; the data falsifies it.
4. **No honest way to remove a dead holding.** Remove-with-purge deletes the history (and
   the realised loss). Manage cannot delete broker rows (SYNC-3, correct). Nothing else exists.
5. **"Ignore" reads as "hide".** It means "no feed — value at last trade price, stop asking";
   the label should say so.
6. **The first render after an upload looks frozen** — feed checks fetch closes for every
   open holding with no spinner.
7. **All instruments is a stub** ("See ISIN Mappings page").

Each of these is a step below. The original "two real syncs before starting" gate is replaced
by Step 9's verification on the real export inside the sandbox — Vivek chose one ticket over
two, and Undo + `git revert` are the fallback if the merged result misbehaves.

## Execution — one commit per step, in this order

### Step 0 — amend the design doc so the rules stay fixed
`docs/DESIGN/SYNC-TAB.md`, section "Thresholds and rules":
- **Import scope** gains: *and every `Corporate action` row with `assetType == Security`,
  status Executed and `shares ≠ 0` — negative shares import as a Sell, positive as a Buy, at
  the row's `price`. The Cash leg of the same reference is information (shown on the cash
  line as "corporate actions") and never imported.*
- **Reconcile** gains: *Corporate action Security legs count with their sign. Write-off
  transactions (`source == "write_off"`) are subtracted from the CSV side, so a written-off
  holding matches at 0.*
- **Sync session** gains: *Ignore / "Use last trade price", tax-kind change, Repair and
  Write-off made while a file is open log the same `session_id`.*
- Replace the word "Ignore" in the task table with **Use last trade price** (status stays
  `ignored` in `isin_map.json`; only the label changes).
- Remove "corporate actions are never imported" from `reconcile._cause` rule 6 in the doc and
  in the code (Step 1).
Commit: `docs: amend SYNC-TAB rules for corporate actions, write-off and session writes`.

### Step 1 — import corporate-action security legs
- `app/adapters/scalable_csv/planner.py::plan_import`: a row with `type == "Corporate action"`,
  `assetType == "Security"`, status Executed and `shares` non-zero is importable; `tx_type_str`
  is `"sell"` for negative shares, `"buy"` for positive; `shares` is stored as its absolute
  value. The Cash leg (`assetType == "Cash"`) stays `OUT_OF_SCOPE_V1`. The duplicate-reference
  guard in `parser.py` already fires only between two importable rows, so the shared reference
  is fine — assert that in a test using the real pair verbatim.
- `app/services/sync.py::build_transaction`: `TransactionType.SELL` when the planned row is a
  negative corporate-action leg; `notes` gets `"corporate action: "` + description.
- `app/domain/reconcile.py`: `_shares_csv` adds the signed shares of Security corporate-action
  legs; delete cause rule 6 ("corporate action — not imported"); `_last_trade_price_eur` and
  `_name` may ignore corporate-action rows (a knock-out at 0,001 is not a trade price).
- `sync.py::cash_line` / `_CASH_TYPES`: add the Cash leg total as "corporate actions".
- Tests: planner (the real pair → one NEW sell of 26 at 0.001 and one out-of-scope cash row),
  reconcile (26 bought, −26 corporate action → `shares_csv == 0`), `build_transaction`,
  `cash_line`. Fixture: copy rows 141, 142, 147, 155 of `data/scalable_raw.csv` into
  `tests/fixtures/scalable_knockout.csv` (they contain no balances).
Commit: `feat: import corporate-action security legs so knock-outs close the position`.

### Step 2 — every write while a file is open goes through the session
`app/services/sync.py`: add `ignore_in_session(isin, name, session_id, isin_repo, store)`,
`set_kind_in_session(isin, kind, session_id, isin_repo, store)`,
`repair_in_session(session_id, isin_repo, tx_repo, store)` — each performs the existing write
(`mappings._ignore_isin` logic, `_set_instrument_kind` logic, `isin_remap.repair`) and then
`_log(...)` with a new event name (`EVENT_IGNORE = "ignore"`, `EVENT_KIND = "kind_change"`,
`EVENT_REPAIR = "repair"`). `sync.py` (page) calls these when `_KEY_SESSION_ID` is set. When no
file is open (All instruments, idle state) the plain services are used and Undo is correctly
disabled by the md5 check — no special case.
Test in `tests/unit/services/test_sync.py`: start session → apply → ignore_in_session →
`undo_enabled(...)` is True → `undo_last` restores both files. Same for kind and repair.
Commit: `fix: ignore, tax kind and repair belong to the sync session so undo stays possible`.

### Step 3 — one instrument card, three independent controls
New `app/ui/components/instrument_card.py::render_instrument_card(isin, name, doc, *,
session_id, key_prefix, context)` replacing `render_isin_mapper_row` everywhere on the Sync
page (tasks, selected holding, All instruments). Layout, top to bottom:

    **<Name>** · <ISIN> · <n shares open | closed>
    Price feed   current state in words: "AMD (Aktie)" | "none — valued at last trade price" | "not set"
                 [ticker searchbox] [ ] same instrument (ISIN change)   [Save feed]
                 [Use last trade price]   ← shown when a feed is set or the state is "not set"
    Tax kind     [selectbox]  — saves on change, no button, allowed with or without a feed
    [Write off remaining <n> shares…]     ← open positions only (Step 4)
    [Remove instrument and its <k> transactions…]  ← context == "all_instruments" only, with
                                                     the existing confirmation + backup

Rules: each control writes on its own; no control disables another; the Save feed button is the
only one that needs a ticker match; the shared-ticker guard and message are unchanged; the
"Use last trade price" button performs what "Ignore" did. The kind selectbox's on-change goes
through `set_kind_in_session` when a file is open. `KIND_LABEL` and `suggest_kind` move into the
new component; `isin_mapper.py` is deleted once nothing imports it (Step 7 removes the last
users).
Tests: `tests/unit/ui/test_instrument_card.py` for the state sentence and for "kind can be saved
with no feed" (pure helper, no Streamlit).
Commit: `feat: one instrument card with independent feed, tax kind and remove controls`.

### Step 4 — write off a holding the broker never closed
- `app/domain/models.py`: `source` literal gains `"write_off"`; it is treated like a broker row
  for ADR-005 currency inference (no inference; EUR-native, `fx_rate_eur = 1`).
- `app/services/sync.py::write_off_in_session(isin, shares, on_date, session_id, tx_repo,
  isin_repo, store)`: appends `Transaction(id=f"writeoff-{isin}-{on_date}", type=SELL,
  ticker=<the ISIN's current ticker or the ISIN placeholder>, trade_date=on_date, shares=shares,
  price_native=Money(0, EUR), fees_native=None, fx_rate_eur=1, notes="write-off: <name>",
  isin=isin, csv_reference=None, source="write_off")`, after a FIFO pre-check that `shares` ≤
  open shares for that ISIN; logs `EVENT_WRITE_OFF`. Provide `write_off(...)` without session
  for the idle state.
- `app/domain/reconcile.py`: subtract `write_off` shares from the CSV side; cause rule 7
  ("includes a manual entry") ignores `source == "write_off"`.
- `app/ui/pages/manage.py`: `write_off` rows render like broker rows (read-only except Notes,
  SYNC-3) **but remain deletable** — deleting the row is how a write-off is reversed. Label the
  source column "write-off".
- Card (Step 3): the button opens a two-field confirm — date (default today) and shares
  (default all open) — then "Write off". Feedback line: "Wrote off <n> <name> at €0 on <date>.
  The loss shows on the Tax Dashboard under <kind>."
- Tax: nothing new — a €0 sell realises the loss under the instrument's tax kind through the
  existing engine. Vivek judges the kind.
Tests: service (pre-check refuses more than open; transaction shape), reconcile (26 bought,
26 written off → 0, matches, no cause), Manage helper (write_off deletable, not editable).
Commit: `feat: write off a holding to zero, history kept, reversible from Manage`.

### Step 5 — spinner on the feed check
`sync.py::render`: wrap `_cached_feed_checks(...)` in
`st.spinner("Checking price feeds against your trades…")`. One line; no test.
Commit: `fix: show a spinner while feed checks run after an upload`.

### Step 6 — All instruments, for real
Replace the stub expander. Content, collapsed by default:
- **Mapped** — `build_mapped_dataframe` (moved from `mappings.py`) with single-row select;
  selecting a row renders the instrument card with `context="all_instruments"`.
- **Closed, no feed** — unmapped ISINs with `shares_csv == 0` (open ones are tasks already),
  each with the card.
- **Valued at last trade price** (the `ignored` list) with **Restore**.
Move the pure helpers (`_save_feed`, `_delete_mapping`, `_ignore_isin`, `_restore_isin`,
`_unmap_isin`, `_set_instrument_kind`, `_backup_portfolio_before_purge`, `_validate_ticker`)
to `app/services/isin_admin.py` and their tests to `tests/unit/services/test_isin_admin.py`.
Keep the SYNC-2 cache clears. The Refresh button is not moved (the page reloads on every
action already).
Commit: `feat: All instruments expander replaces the Mappings page`.

### Step 7 — delete the old doors
Delete `app/ui/pages/import_workbench.py`, `app/ui/pages/mappings.py`,
`app/ui/components/isin_mapper.py`, `tests/unit/ui/test_import_workbench.py`,
`tests/unit/ui/test_mappings_page.py` (move any still-relevant test to `test_sync_page.py` /
`test_sync.py` / `test_isin_admin.py` first), sidebar + topbar entries `import_workbench` and
`mappings`, and the references in `test_sidebar_structure.py` and `test_main_router.py`.
Remove the dead `RowStatus` values `UNMAPPED_ISIN`, `IGNORED_ISIN` and every branch that
handled them. `grep -rn "import_workbench\|pages.mappings\|isin_mapper\|UNMAPPED_ISIN\|IGNORED_ISIN" app tests docs/ARCHITECTURE.md README.md` must return nothing; list the resolved hits in the PR.
Commit: `refactor: retire the Import CSV workbench and ISIN Mappings pages`.

### Step 8 — archive and docs
`git mv docs/screenshots/<old page folders>` to `docs/screenshots/_archive/`; leave ticket
files and session-log entries untouched. `docs/ARCHITECTURE.md` file layout: the two pages →
`sync.py`, add `instrument_card.py`, `isin_admin.py`. `README.md` "Import" paragraph → three
sentences on the Sync tab (drop, tasks, undo). Mark ADR-014 **Accepted**.
Commit: `docs: archive old page screenshots, update layout and README, accept ADR-014`.

### Step 9 — verification on the real export (sandbox), gate, log, PR
Use the `screenshot-app` skill with `tools/app_sandbox.sh`; copy the real `data/portfolio.json`,
`data/isin_map.json` and `data/scalable_raw.csv` into the sandbox data dir (never the real
`data/`). Then, in order, each with a screenshot kept under `docs/screenshots/ticket-sync-7/`:
1. Upload `scalable_raw.csv` → card shows the corporate-action sell imported, holdings match
   N/N, no `unknown` cause, DE000HT41XN9 absent from the Holdings table's open rows.
2. Live Overview: no Apple turbo row; Tax Dashboard renders and shows the knock-out loss in 2025.
3. Upload the same file again → 0 new, N/N match.
4. Click "Use last trade price" on any holding → **Undo last sync** is still enabled → click
   it → both files restored (md5 equal to the session_start snapshot).
5. Write off a holding (pick the Algorand ETP if it still shows shares, else any) → card
   feedback → Undo → restored.
6. All instruments: select a mapped row, change only the tax kind, no feed change required.
7. Sidebar shows Sync with Scalable and Manage Portfolio only.
Then `bash tools/gate.sh`, session-log entry, `bash tools/finish_ticket.sh TICKET-SYNC-7`.

## Acceptance criteria
- [ ] The corporate-action Security leg for DE000HT41XN9 imports as a sell of 26 at €0.001; the
      position is closed on the Overview and reconciled at 0 with no cause.
- [ ] A holding can be written off to €0 with a date and share count; the row is visible and
      deletable on Manage; reconciliation matches afterwards.
- [ ] Ignore / Use last trade price, tax-kind change, Repair and Write-off made while a file is
      open leave **Undo last sync** enabled, and Undo restores both files.
- [ ] Tax kind can be set for an instrument with no feed, on the task card and in All
      instruments, without touching the feed.
- [ ] The word "Ignore" no longer appears on the Sync tab; the state reads "valued at last
      trade price".
- [ ] A spinner is visible while feed checks run.
- [ ] Every action the Mappings page offered is reachable from All instruments.
- [ ] Sidebar: Sync with Scalable, Manage Portfolio — no Import CSV, no ISIN Mappings.
- [ ] The grep in Step 7 returns nothing.
- [ ] Step 9 screenshots are committed and embedded in the PR body.
- [ ] Gate clean.

## Out of scope (say so in the PR, do not do)
- Streamlit 1.57 + pandas 3 rendering `None` in empty numeric cells (needs its own ticket:
  pin `pandas<3` or wait).
- A guard against committing a sandbox-generated `data/isin_map.json`.
- Feed column currency (design says "ticker · ccy"; the map stores no currency).
- FIFO keyed by ISIN; multi-signal feed confidence (deferred in the design doc).
