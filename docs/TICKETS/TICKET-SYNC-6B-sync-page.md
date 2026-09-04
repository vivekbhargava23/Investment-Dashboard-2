# TICKET-SYNC-6B — The Sync page (upload → analyse → safe changes applied → tasks → holdings)

**Priority:** CRITICAL
**Status:** IN_PROGRESS
**Milestone:** Investment Panel
**Recommended model:** Sonnet — rendering over SYNC-6A services; every state is specified in the design doc.
**Estimated session length:** 2 hr
**Drafted by:** Vivek + Claude (Cowork session 2026-09-03, revised after review)
**Depends on:** TICKET-SYNC-6A.
**Required reading:** `docs/DESIGN/SYNC-TAB.md` in full; the screen is specified there and not repeated here.

> **After this ticket merges:** sidebar page **Sync with Scalable** (`app/ui/pages/sync.py`, id `sync`) exists next to the old pages. Uploading a CSV analyses it, applies the safe rows, and shows the summary card, task list, holdings table, cash line, Details and All-instruments placeholder. Undo restores the previous state of both data files.

## Execution — one commit per step

### Step 1 — page skeleton and flow
`app/ui/pages/sync.py::render()`, session keys under `sync.*`. On new bytes:
`rows = parse_csv_bytes(bytes)` (`ParseError` → `st.error`, stop) → `session_id =
start_session(...)` → `analysis = analyse(...)` → `applied = apply_safe(...)` inside
`st.spinner("Syncing…")` → keep all three in Streamlit session state. Every later action on
the page passes the same `session_id`. First-ever sync: the card says "First sync — make sure
the export covers all time" instead of the holdings sentence.
Summary card text exactly as the design doc (holdings sentence only when not partial).
`Undo last sync` enabled only when the stored md5s equal `store.current_md5s()` (compare;
do not use try/except as a probe). Market-value line: `Market values are estimates from
yfinance as of <timestamp of the last price fetch, or "not fetched yet">`.

### Step 2 — tasks
`build_tasks(...)` from SYNC-6A; each in `st.container(border=True)`.
- `no_feed` / `feed_suspicious`: `render_isin_mapper_row(...)` + Save + Ignore + the
  `Same instrument (ISIN change)` checkbox from SYNC-2. Save → `change_feed_in_session` →
  `st.cache_data.clear()` → rerun (no re-import: the trades are already in the book; only the
  ticker changes).
- `possible_duplicate`: buttons **Replace with Scalable row** / **Keep both** →
  `resolve_conflict(...)` → rerun.
- `shares_differ`, `sell_exceeds`, `partial_file`: text only.

### Step 3 — holdings table, cash line, expanders
Holdings table per design doc; feed-check cell text `✓ within 1.2 %` or
`⚠ looks wrong · you €20.44 / feed €0.20` or `⚠ no feed` or `—`. Row select → action bar
with mapper row + Ignore. Cash line from the plan rows of this file. `Details` expander:
raw table, plan status table, last 5 log entries. `All instruments` expander: one line
`See ISIN Mappings page` until SYNC-7. State A (no file): last-sync line from the last log
entry + Undo if eligible. On every render call `check_consistency` (SYNC-2); if mismatches
exist show the warning + **Repair** button here and remove it from the Mappings page.

### Step 4 — sidebar
`app/ui/components/sidebar.py`: insert `{"id": "sync", "label": "Sync with Scalable",
"icon": "⇅", "badge": None}` before `manage`. Old pages stay.

### Step 5 — tests
`tests/unit/ui/test_sync_page.py` following the monkeypatch pattern of
`test_import_workbench.py`: state A smoke; state B with a fixture CSV (inserts N, summary
sentence present); one unmapped open ISIN → exactly one `no_feed` task; mapping it via the
fake resolver removes the task; a conflict fixture → `possible_duplicate` task and nothing
inserted for that row until a button is pressed.

### Step 6 — screenshots (mandatory): states A, B, C and the duplicate task, on the sandbox;
commit under `docs/screenshots/sync-tab/`.

### Step 7 — gate, commit, session log, PR.

## Acceptance criteria
- [ ] Healthy file: one click (choosing the file), rows imported, summary says holdings match.
- [ ] Conflict rows are applied only through the task buttons.
- [ ] Undo restores both data files byte-for-byte and is disabled after any later write.
- [ ] No status chips, apply button, conflict radios or exclude checkboxes on the page.
- [ ] Gate clean; screenshots in the PR.
