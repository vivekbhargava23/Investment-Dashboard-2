# TICKET-CSV-4 — CSV Import Workbench (visible, row-level import flow)

**Status:** QUEUED
**Priority:** HIGH
**Estimated session length:** 3-4 hr (largest single UI ticket to date)
**Drafted by:** Vivek + Claude (chat session 2026-05-15)
**Implemented by:** TBD
**Milestone:** UI core
**Depends on:** TICKET-CSV-1 (importer), TICKET-CSV-1-hotfix (sign fixes), TICKET-CSV-2 (mappings page)
**Blocks:** TICKET-CSV-5 (native-currency support, will plug into this UI), TICKET-CSV-6 (operational re-import)

## Problem

TICKET-CSV-1 ships a CLI importer. The CLI does the right thing mechanically but is invisible to the user:

- The user drops a CSV in `data/scalable_raw.csv`, runs `python tools/import_scalable_csv.py`, and reads a terminal summary.
- Counters like "Invalid mappings: 70" scroll past in the summary, get noticed too late, and dozens of real trades silently never enter the portfolio (see chat session 2026-05-15: 12 of 18 mapped tickers were dropped because they are USD/JPY, not EUR — counted as `invalid_mapping`, surfaced only as a subtotal).
- There is no preview. No per-row visibility. No way to fix things inline. No way to know what changed after Apply.
- Re-uploading a CSV that contains the full transaction history (Scalable exports are cumulative from account opening) is theoretically supported via idempotency, but the user has no way to *see* what's new vs already-present before committing.

The CLI also obscures a real design problem: the importer rejects every non-EUR ticker silently, and the user only finds out by inspecting `portfolio.json` and noticing trades are missing. A visible per-row UI makes this kind of issue impossible to hide; a CLI summary makes it easy to hide.

## Goal

A single-page Streamlit Import workbench that makes every step of the CSV import process visible, inspectable, and reversible. The user uploads a CSV, sees exactly what's in it, sees exactly what the system plans to do with each row, can fix anything that needs fixing, and only then hits Apply. Nothing touches `data/portfolio.json` before Apply.

The CLI continues to exist for power-user / scripting use, but the UI is the supported primary path.

## Non-goals (out of scope for this ticket)

- Native-currency support for USD/JPY/GBP tickers. The wizard will mark such rows with a status (`needs_currency_support`) but will not import them. **Deferred to TICKET-CSV-5**, which will plug into this UI by adding a new planned-action option to the same workbench.
- Distribution / Interest / Vorabpauschale / Corporate-action handling. **Deferred to TICKET-CSV-3** (already queued). These rows render in the workbench with status `out_of_scope_v1` and are not importable.
- Multi-broker support (Trade Republic, IBKR, etc.). Scalable only for now. The architecture should not preclude adding brokers later, but no abstraction for it in v1.
- Import history view, undo-in-UI, diff between imports. **Deferred to a later ticket.** The pre-Apply backup (see Safety section) is the v1 substitute for undo.
- Editing transactions from the workbench (changing fields). Edits go through the existing Manage Portfolio page. The workbench is import-only.

## Data model changes

Two new fields on `Transaction` (in `app/domain/models.py`):

### 1. `csv_reference: str | None`

The broker's transaction reference (e.g. `"SCALWs6zGYc5iX3"` for trades, `"WWUM 00596687933"` for security transfers from the broker migration). Used as the primary dedup key for CSV re-imports.

- Nullable. Manual entries have `csv_reference = None`.
- Indexed in-memory at load time (the importer builds `{ref: tx_id}` once per run; no schema-level index needed in the JSON file).
- Stable across CSV exports per Scalable's contract.

### 2. `source: Literal["scalable_csv", "manual", "switch", "unknown"]`

Tracks how each transaction entered the portfolio. Defaults to `"manual"` for new transactions added through the existing Manage Portfolio page. Set to `"scalable_csv"` by the workbench. The `"switch"` value is reserved for legacy IDs in the current `portfolio.json` that came from the pre-CSV-1 seed script (those have IDs prefixed `SWITCH-101-...`); the migration script (below) tags them. `"unknown"` is the fallback for transactions the migration cannot classify.

- Drives the conflict rule: a CSV row only counts as conflicting with an existing transaction if that existing transaction has `source != "scalable_csv"` (i.e. CSV does not collide with itself — the dedup-by-reference handles that — only with manual entries on the same trade).
- Surfaced in the workbench UI as a small badge per row.

### Migration (one-shot, runs on first launch after this ticket ships)

A migration script `app/scripts/migrate_portfolio_v1_to_v2.py` does the following on existing `portfolio.json`:

1. Loads the current portfolio file (schema version 1).
2. Loads `data/scalable_raw.csv` if present.
3. For each existing transaction:
   - If its `id` matches a Scalable CSV `reference` (exact string match): set `csv_reference = <reference>`, `source = "scalable_csv"`.
   - If its `id` starts with `SWITCH-101-`: set `csv_reference = <the id>` (these IDs *are* the WWUM-style transfer references in a wrapped form — the migration extracts the WWUM ID by splitting on `-`), `source = "switch"`.
   - If its `id` starts with `SCAL` but doesn't match any CSV reference: this is a Scalable trade that was imported by an old version of CSV-1 with a generated ID. Set `csv_reference = None`, `source = "scalable_csv"`. (These will dedup by content-hash on next import — see fallback below.)
   - Otherwise (UUID-shaped IDs, etc.): set `csv_reference = None`, `source = "manual"`.
4. Bumps schema version to 2.
5. Writes atomically.
6. Logs a summary: `"Migrated N transactions: X CSV-matched, Y switch-tagged, Z untagged-Scalable, W manual."`

The migration is idempotent (running it twice is a no-op since schema version is already 2 on the second run). It is invoked automatically by `JsonTransactionRepository.load()` on detection of schema version 1, before returning data to callers. A one-line backup of the v1 file is taken before migration: `portfolio.v1.pre-migration.json.bak`.

## Dedup logic (the robust part)

The workbench classifies every CSV row into exactly one of these states **before** the user sees the table:

| State | Test | What it means |
|---|---|---|
| `already_imported` | CSV row's reference matches an existing tx with `source="scalable_csv"` | No-op on apply. Most rows fall here on re-import. |
| `conflict_with_manual` | Content-hash matches an existing tx with `source="manual"` (within tolerance) | CSV wins by default with a per-row notice. User can opt to keep manual instead. |
| `new` | No reference match, no content match | Will be imported on apply. |
| `unmapped_isin` | ISIN not in `isin_map.json` or status `unmapped` | Cannot import. Inline mapper allows the user to resolve. |
| `needs_currency_support` | Mapped ticker is non-EUR (suffix not in EUR-exchange list, e.g. `.DE`, `.PA`, `.AS`, `.MI`, `.MC`, `.HE`, `.HM`, `.SW`, etc., AND ticker doesn't end in known EUR patterns) | Cannot import in v1. Status: deferred to TICKET-CSV-5. |
| `out_of_scope_v1` | Row type is Distribution / Interest / Taxes / Withdrawal / Deposit / Corporate action | Cannot import in v1. Deferred to TICKET-CSV-3. |
| `outgoing_transfer` | Security transfer with `shares < 0` | Filtered per CSV-1-hotfix. Shown for transparency, not importable. |
| `cancelled_or_expired` | Row status is Cancelled / Expired / Rejected | Shown for transparency, not importable. |
| `parse_error` | Row failed to parse (bad numeric format, missing required field) | Shown with the error message inline. |

**Primary dedup key:** `csv_reference` (exact string match).

**Content-hash fallback** (for the migration edge case where existing transactions have no `csv_reference`): `sha1(f"{type}|{ticker}|{trade_date}|{shares}|{price_native.amount}|{price_native.currency}")`. Computed lazily per row only if the reference lookup misses and `conflict_with_manual` detection needs to run. Tolerance for floating-point precision is 6 decimal places on `shares` and 4 on `price`.

**Why the broker reference is the right primary key:**
- Stable across CSV re-exports (Scalable contract).
- Unique per transaction by broker definition.
- Survives small content changes (price correction of €0.01 doesn't create a phantom new transaction).
- Content hashes alone false-positive on legitimate same-day savings-plan repeats.

## UI layout

One Streamlit page: `app/ui/pages/import_workbench.py`. New sidebar entry under **TOOLS** group (after Sell Simulator), label "Import CSV", icon `📥` or similar (match existing emoji style in `sidebar.py`).

The page is one vertical scroll, no tabs. Each section below renders at fixed height — tables are scroll-internal (15-row windows), not expand-the-page. This keeps every section the same vertical footprint regardless of CSV size.

### Section 1 — Upload + status strip (~6 inches tall)

- `st.file_uploader` accepting `.csv`, single file.
- When no file is uploaded: show last-import card — date, filename, count of transactions applied. Pulled from a small `data/import_log.json` (append-only log of successful applies; just for the "last import" display).
- When a file is uploaded: show parse status — "Parsed 301 rows from `scalable_raw.csv` · 18 in-scope · 13 already imported · 5 new · 0 conflicts · 12 blocked".
- A "Clear" button discards the uploaded file and returns to last-import view.

### Section 2 — Raw CSV preview (~5 inches tall, fixed)

- Heading: "Raw CSV — exactly as Scalable exported it"
- `st.dataframe`, scrollable, 15-row window. All 14 columns shown verbatim with no interpretation. No editing.
- Goal: user can confirm the file Streamlit parsed matches what they expect. If a column is empty in this view, it's empty in the file.
- A small caption: "Filename, byte size, MD5 hash, row count, detected delimiter, detected encoding."

### Section 3 — Planned changes (the workbench, ~6 inches tall, fixed)

This is the centerpiece. A scrollable 15-row table where every CSV row is a row, with the following columns:

| Column | Width | Content |
|---|---|---|
| Status | narrow | Badge (`already_imported`, `new`, `unmapped_isin`, etc.) with color from `dark.css` accent palette |
| Date | narrow | `trade_date` from CSV |
| Type | narrow | Buy / Sell / Savings plan / etc. |
| Ticker | narrow | Resolved ticker if mapped, else "—" |
| ISIN | medium | Raw ISIN |
| Description | wide | CSV `description`, truncated with tooltip |
| Shares | narrow | Parsed numeric |
| Price | narrow | Parsed numeric (native unit) |
| Amount EUR | narrow | Parsed numeric |
| Action | narrow | Per-row inline control (see below) |

**Filter bar above the table:** chips for each status type. Clicking a chip filters to that status. Default view: all rows. A counter on each chip shows the count (e.g. "new (5)", "already_imported (13)", "unmapped_isin (12)").

**Per-row Action control** depends on status:
- `new` → checkbox (checked by default) "include in apply"
- `conflict_with_manual` → radio: ⊙ Replace manual with CSV (default) / ⊙ Keep manual / ⊙ Skip
- `unmapped_isin` → "Map ISIN" button that opens a small inline form (ticker input, save → writes to `isin_map.json`, reruns)
- `already_imported` → no action (read-only display, slightly dimmed)
- `out_of_scope_v1` / `needs_currency_support` / `outgoing_transfer` / `cancelled_or_expired` → no action; tooltip on hover explains why and which ticket (if any) will address it
- `parse_error` → no action; error message shown inline as red text

### Section 4 — Inline ISIN mapping panel (collapsible-only-when-empty)

If any row has `unmapped_isin` status, this section auto-expands. Otherwise it's not rendered at all.

Heading: "ISINs needing mapping (N)"

A table of unmapped ISINs (deduplicated — one row per ISIN, not per CSV row), with:
- ISIN (monospace, read-only)
- Description (from CSV)
- Transactions in this import (count)
- Ticker input
- Save button (writes to `isin_map.json`, reruns the workbench, the previously-quarantined rows flip to `new` status)

This is the same data flow as TICKET-CSV-2's Mappings page, just embedded inline at the moment the user needs it. Both pages call the same `IsinMapRepository`.

### Section 5 — Apply bar (sticky at bottom of page)

- Summary: "N rows ready to import · M conflicts to confirm · K rows blocked"
- Big primary button: "Apply N changes to portfolio" (disabled until N > 0)
- Secondary button: "Cancel" (discards uploaded file, returns to last-import view)
- Small text below button: "A backup of portfolio.json will be saved to `data/backups/` before applying."

On click of Apply:
1. Write a timestamped backup: `data/backups/portfolio.{YYYY-MM-DD_HH-MM-SS}.json.bak`. Keep the 10 most recent backups; delete older ones.
2. Apply all changes in a single atomic write (load → modify in memory → atomic write via temp-file-and-rename).
3. Append an entry to `data/import_log.json`: timestamp, filename, MD5, applied count, conflict count.
4. Streamlit `st.success("Applied N changes. Backup at data/backups/...")` and rerun the page back to the empty-upload view.

## Safety

- **Pre-apply backup is mandatory and non-skippable.** Even if Apply fails midway (it shouldn't — the write is atomic — but defense in depth), the backup is on disk first.
- **10-backup rolling window** stored in `data/backups/`. Older ones auto-deleted. Total disk overhead bounded.
- **The Apply button is the only path that writes.** Every other interaction (mapping, choosing conflict resolution, filtering, etc.) is in-memory state on the Streamlit session. Reloading the page or hitting Cancel discards everything.
- **JsonTransactionRepository's existing atomic-write behavior is reused.** No new write path.
- **Schema migration runs once, with its own backup** (`portfolio.v1.pre-migration.json.bak`), independent of the per-apply backup.

## Acceptance criteria

- [ ] Sidebar shows new "Import CSV" entry under TOOLS, opens the new page.
- [ ] Uploading no file: shows last-import card with date / filename / count, or "No imports yet" if `data/import_log.json` is empty.
- [ ] Uploading `scalable_raw.csv` (the real 2026-05-14 export): parses without errors; Raw CSV section shows 301 rows.
- [ ] Status counts in Section 1 match the breakdown documented in this ticket (188 in-scope, 13 outgoing transfers, 95 out-of-scope, etc. — exact numbers depend on existing portfolio state).
- [ ] Planned changes table renders all 301 rows, scrollable at 15-row height.
- [ ] Filtering by status chip works (clicking "new" shows only new rows; counter on chip matches displayed count).
- [ ] Unmapped ISINs section auto-renders when there's at least one; mapping an ISIN inline flips its rows from `unmapped_isin` to `new` without page reload (via Streamlit rerun).
- [ ] Conflict row's radio control: choosing "Keep manual" excludes the row from the apply set; choosing "Replace manual with CSV" includes it.
- [ ] Apply button is disabled when 0 rows are ready to import.
- [ ] Clicking Apply writes a backup to `data/backups/portfolio.{timestamp}.json.bak`, updates `portfolio.json` atomically, appends to `data/import_log.json`, shows success message, returns to empty-upload state.
- [ ] After Apply: re-uploading the same CSV shows all previously-applied rows as `already_imported`, zero new rows.
- [ ] After Apply: the Live Overview page reflects the new transactions on next refresh.
- [ ] Schema migration: first launch after this ticket ships, on a portfolio with schema version 1, automatically migrates to version 2, writes backup `portfolio.v1.pre-migration.json.bak`, logs the migration summary, and the migrated portfolio loads correctly in the rest of the app.
- [ ] Second launch after migration: schema is version 2, migration is a no-op, no backup file overwritten.
- [ ] Re-importing the CSV after migration correctly identifies the previously-imported rows via either `csv_reference` (where matched) or content hash (for the untagged Scalable rows).
- [ ] Backup rolling window: after 11 applies, only the 10 most recent `.bak` files remain in `data/backups/`.
- [ ] Existing TICKET-CSV-1 CLI continues to work unchanged. Importing via CLI then opening the workbench shows the CLI-imported rows as `already_imported` (because both paths write the same `csv_reference`).
- [ ] Tests pass: see Test cases below.
- [ ] Lints pass: `ruff check . && mypy app/ && lint-imports`.

## Files likely touched

### New
- `app/ui/pages/import_workbench.py` — the page itself
- `app/ui/components/workbench_row.py` — per-row renderer (status badge + action control)
- `app/ui/components/import_filters.py` — status chip filter bar
- `app/services/csv_import_planner.py` — the row-classification logic (pure function, no I/O); takes parsed CSV + existing portfolio + isin_map, returns a list of `PlannedRow` objects with status and proposed action
- `app/domain/csv_import.py` — `PlannedRow`, `RowStatus` enum, `ImportPlan` aggregate
- `app/scripts/migrate_portfolio_v1_to_v2.py` — the one-shot migration
- `app/adapters/repo_json/migration.py` — migration trigger inside `JsonTransactionRepository.load()`
- `tests/unit/services/test_csv_import_planner.py` — classifier logic (heavy test surface)
- `tests/unit/ui/pages/test_import_workbench.py` — page smoke + action handler tests
- `tests/unit/scripts/test_migrate_v1_to_v2.py` — migration tests
- `tests/fixtures/portfolio_v1_*.json` — pre-migration fixtures

### Modified
- `app/domain/models.py` — add `csv_reference`, `source` fields to `Transaction`; bump schema version constant
- `app/adapters/scalable_csv/importer.py` — write `csv_reference` and `source="scalable_csv"` on every new transaction; reuse planner for dedup classification (importer becomes a thin wrapper around planner + writer)
- `app/adapters/repo_json/json_repo.py` — schema version detection + migration trigger on load
- `app/ui/components/sidebar.py` — add Import CSV entry, update NAV_ITEMS count
- `app/ui/components/topbar.py` — add page title for new route
- `app/ui/wiring.py` — `get_csv_import_planner()` getter
- `app/config.py` — `backups_dir` setting (default `data/backups/`), `import_log_json_path` setting
- `tests/unit/ui/test_components.py` — update NAV_ITEMS count
- `tests/unit/ui/test_sidebar_structure.py` — update count

## Test cases (detailed)

### Planner — classification

1. **CSV row matches existing tx by reference** → status `already_imported`, action `noop`.
2. **CSV row matches existing manual tx by content hash** → status `conflict_with_manual`, default action `replace`.
3. **CSV row's ISIN not in map** → status `unmapped_isin`.
4. **CSV row's ISIN maps to USD ticker (NVDA)** → status `needs_currency_support`.
5. **CSV row's type is Distribution** → status `out_of_scope_v1`.
6. **CSV row is Security transfer with shares=-17** → status `outgoing_transfer`.
7. **CSV row status is Cancelled** → status `cancelled_or_expired`.
8. **CSV row has malformed price ("abc")** → status `parse_error`, error message attached.
9. **CSV row matches by content but existing tx has source="scalable_csv" with no reference** (the migration edge case) → status `already_imported` via content-hash fallback, NOT `conflict_with_manual`.
10. **Empty portfolio + 5 valid CSV rows + 0 mappings issues** → 5 rows status `new`.

### Migration

11. Fixture: v1 portfolio with one CSAL-prefixed tx whose ID matches a CSV reference → migration sets `csv_reference` and `source="scalable_csv"`.
12. Fixture: v1 portfolio with one SWITCH-101-prefixed tx → migration tags `source="switch"` and extracts the WWUM reference.
13. Fixture: v1 portfolio with one UUID-prefixed tx → migration tags `source="manual"`, leaves `csv_reference=None`.
14. Fixture: v2 portfolio → migration is a no-op, no backup overwritten.
15. Migration writes `portfolio.v1.pre-migration.json.bak` exactly once, on first run only.

### Apply

16. Apply with 3 new rows + 1 conflict (user chose "Replace manual") → portfolio gains 3 + 1 = 4 transactions (1 replacing the manual), backup written, import_log appended.
17. Apply with 0 ready rows → button is disabled, cannot fire.
18. Apply on first run writes 1st backup; 10 successful applies later, 10 backup files exist; 11th apply deletes the oldest, total 10 files.
19. Apply with `portfolio.json` write failing mid-way (simulate by mocking) → backup is on disk, original `portfolio.json` is unchanged (atomic write rollback), error surfaced to user.

### Re-import idempotency

20. Apply once with the real `scalable_raw.csv`. Re-upload the same file. All rows show as `already_imported`. Apply button disabled.

### UI

21. Sidebar entry renders; clicking it loads the page.
22. With 0 unmapped ISINs, Section 4 (mapping panel) is not rendered.
23. Filter chip clicks update the table without page reload (uses `st.session_state`).
24. Cancel button discards in-memory state and returns to empty upload.

## Notes

### Ticket numbering & discoverability

CSV-3 already exists (tax events ticket). This ticket is **CSV-4**. Before drafting any new ticket in a chat session, scan `docs/TICKETS/` (or wherever tickets live in the repo) to confirm the next available number. The `tools/draft_ticket.sh` script does this for Claude Code sessions; chat sessions must do it manually. **This convention should be added to `AGENTS.md` or `METHODOLOGY.md` as a chat-session rule.** SESSION_LOG entries should also list "Tickets drafted: TICKET-X, TICKET-Y" explicitly so future chats can grep.

### Why the workbench, not a wizard

A wizard implies a guided linear flow: step 1 → step 2 → step 3 → done. That hides things. The workbench shows everything on one page and lets the user move between sections in any order. The point of this ticket isn't to make the user follow a path; it's to make every decision visible. Conventional "Import CSV" wizards (Plaid, Wise, brokerage UIs) are uniformly bad at this — they show a 5-row preview and a Confirm button. We're not building that. We're building the inspector.

### Why per-row, not summary-level

You will re-import this CSV many times over the years. Each re-import will be 99% "already imported" and 1% new. Summary-level UI (".... 3 new rows, apply?") gives you no idea what those 3 are or whether they're correct. Row-level UI lets you scan and confirm. The cost (a busier UI) is paid once; the benefit (knowing what changed) is recurring.

### Why CSV is input-only, JSON is storage

CSV is a great interchange format and a terrible storage format. No types, no schema, no atomic writes, no concurrency guarantees, hand-edits silently corrupt the file. JSON gives us Pydantic validation, atomic writes, schema versions, and a real migration path. The workbench respects the user's mental model (CSV is what Scalable gives me) while the system uses the right tool for storage.

### Why CSV-5 is separate

Currency support changes data model semantics (what does "native price" mean when source is EUR-denominated CSV) and pricing logic (yfinance calls, FX rate storage). It's a real ticket on its own. Folding it into this one would double the size and delay shipping the visibility win. CSV-4 ships first; you can use it the moment it merges (every USD/JPY row will show `needs_currency_support` — visible, not silent). CSV-5 then unlocks importing those rows.

### Why CSV-6 is operational, not a code ticket

After CSV-4 + CSV-5 ship, you re-import `scalable_raw.csv` through the workbench. The system identifies your existing transactions via reference or content hash, marks the USD/JPY rows as importable (CSV-5), and the rest as already-imported. You hit Apply once. Your portfolio is suddenly correct. There's no code to write for that step — only ops. The CSV-6 ticket exists to make that handoff explicit so it doesn't get forgotten.

### Streamlit session state hygiene

The page holds in-memory state for: uploaded file bytes, parsed rows, classification results, per-row user overrides (mapping decisions, conflict choices, include/exclude toggles). All of this lives in `st.session_state` keyed under `import_workbench.*` namespace to avoid collisions with other pages. Cleared on Apply success or Cancel.

### Real CSV bench-test expectations

Using the 2026-05-14 export and the current `isin_map.json` (18 mapped, 9 unmapped), the workbench should show approximately:

- ~13 `already_imported` (current portfolio's CSV-sourced rows, plus migration-back-filled rows)
- ~5 `new` for already-mapped tickers (e.g. RHM.DE 2026-03-30 update, IUES.DE sells, etc.)
- ~70 `needs_currency_support` (NVDA, DELL, NOW, MU, HXSCL, ASX, CIEN, 5631.T, KD, MRVL, AVGO, ANET — these will become importable in CSV-5)
- ~9 `unmapped_isin` (the 9 currently-unmapped ones; user maps inline, they flip to `needs_currency_support` if non-EUR or `new` if EUR)
- ~95 `out_of_scope_v1` (Distribution / Interest / Taxes / etc.)
- ~13 `outgoing_transfer`
- ~18 `cancelled_or_expired`

If the numbers come out very differently on first real run, that's a finding worth investigating before shipping.

### Anti-approximation

The status-classification logic is the heart of this ticket. It is a *pure function*: `(parsed_csv_rows, existing_portfolio, isin_map) → list[PlannedRow]`. No I/O, no side effects, no Streamlit dependency. The UI consumes its output but does not contain the logic. This is critical for testability and means the classifier can be exercised in isolation with 30+ unit tests without spinning up a Streamlit session. The UI tests then only verify rendering and action handlers, not classification correctness.
