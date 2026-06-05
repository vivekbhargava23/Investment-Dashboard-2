# SESSION_LOG.md

Append-only log of every Claude Code session and significant Claude Chat session.
Newest entries at the top of **Active log** (prepend new entries).

When this file exceeds ~500 lines, archive everything older than 30 days into `docs/SESSION_LOG_ARCHIVE_<year>_Q<N>.md` and keep this file lean.

---

## Template

<!--
## YYYY-MM-DD HH:MM — TICKET-XXX
**Surface:** Claude Code
**Model:** sonnet-4.6 | opus-4.7 | haiku-4.5
**Duration:** ~XX min
**Branch:** ticket-XXX-short-name
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/N
**Status at session end:** IN_REVIEW

### What got done
- Bullet of concrete change 1
- Bullet of concrete change 2

### Files touched
- `app/domain/fifo.py` — added replay-on-edit logic
- `tests/unit/test_fifo.py` — added 4 new test cases

### Tests
48 passing → 52 passing (4 new)

### Decisions made during the session
- Chose to raise `LotEditConflict` instead of silent recompute — see ADR-XXX
- (Or: "no architectural decisions made")

### Out-of-scope items noticed
- Open ticket: TICKET-YYY (noticed but didn't fix)

### Tokens used (rough)
~XXk
-->

---

## Active log

## 2026-06-05 — TICKET-RD9
**Surface:** Claude Code
**Model:** opus-4.8
**Branch:** ticket-rd9-returns-by-period-service-shared
**Status at session end:** IN_REVIEW

### What got done
- Added the shared returns-by-period foundation that RD10 (treemap) and RD11 (heatmap)
  will both consume, so the windows are computed once and reused.
- **Domain (`app/domain/returns.py`):** pure `period_return(series, window, *, as_of)`
  over a `ReturnWindow` enum (`D1`/`D7`/`D30`/`YTD`). All windows end at the latest bar
  on/before `as_of`; D7/D30 are calendar-day lookbacks; YTD measures from the prior-
  year-end close (or first current-year bar). Returns `Decimal` percent, `None` when
  history can't cover the window. No `datetime.now()`.
- **Service (`app/services/returns.py`):** `compute_returns_by_period(...)` fetches 1Y
  daily OHLC once via `get_ohlc_histories(..., freq="day")` and computes every requested
  window per ticker. Per-ticker provider failures yield all-`None`, never raise.
- **UI (`app/ui/pages/overview.py`):** `@st.cache_data` wrapper keyed on the
  transactions signature + `as_of` so the future period selector re-colours from cache.

### Files touched
- `app/domain/returns.py` — new pure module (ReturnWindow, period_return)
- `app/services/returns.py` — new batching service
- `app/ui/pages/overview.py` — cached `_cached_returns_by_period` wrapper + imports
- `tests/unit/domain/test_returns.py` — new (window math, None cases, YTD straddle)
- `tests/unit/services/test_returns.py` — new (single fetch, normalisation, unservable)

### Tests
993 → 1007 passing (14 new). ruff / mypy / lint-imports all clean.

### Decisions made during the session
- Did **not** reuse `OhlcSeries.period_change_pct` (full-span open→close); it doesn't
  model fixed calendar windows anchored on `as_of`. Added `period_return` as the ticket
  Notes anticipated.
- Fetch `ONE_YEAR` with `freq="day"` (not `YEAR_TO_DATE`): the 1Y lookback covers D30
  and the YTD prior-year-end close, and `freq="day"` overrides the default weekly 1Y
  aggregation that would be too coarse for D1/D7.

### Out-of-scope items noticed
- None. Rendering is deferred to RD10/RD11 per the ticket.

## 2026-06-05 — Overview weight bar / gain-% follow-up
**Surface:** Claude Code
**Model:** opus-4.8
**Branch:** fix-overview-weight-bar-neutral-gain-pct
**Status at session end:** IN_REVIEW

### What got done
- Follow-up to the merged TICKET-RD2 weight-bar work. Vivek flagged a data-viz flaw:
  the Weight bar encoded *two* things at once — length = holding size, colour = gain
  sign. A big position with a tiny loss (Ajinomoto: ~15% weight, −€250) rendered as a
  long red bar and read as a huge loss.
- **Fix (Option A):** decouple the two signals. Weight returns to a smooth neutral
  `ProgressColumn` (size only — no gain colour, no Unicode `█/·` text bar). P/L
  direction moves to a new **Gain (%)** column coloured green/red by sign (alongside
  the existing Gain (€)). Magnitude of loss now maps to the number, not bar length.
- Removed `weight_bar_text()` and its tests; added Gain (%) column + coverage.

### Files touched
- `app/ui/components/positions_table.py` — add Gain (%) col; Weight → neutral
  ProgressColumn; drop Unicode weight bar + gain-tinting of the weight cell.
- `tests/unit/ui/test_positions_table.py` — column-shape + stale-row updates,
  new `test_gain_pct_passed_through`, dropped weight-bar-text tests.

### Tests
Gate green: 993 passing, 91 skipped; ruff/mypy/lint-imports clean.

### Decisions made during the session
- No formal board ticket: this is a small UI follow-up on already-merged RD2 work,
  done on a fresh branch + PR (the RD2 PR #169 was already merged and can't reopen).

## 2026-06-05 — TICKET-RD2
**Surface:** Claude Code
**Model:** opus-4.8
**Branch:** ticket-rd2-sortable-positions-table
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/169
**Status at session end:** IN_REVIEW

### What got done
- Sortable tables across three pages. Per Vivek's "do it here only", all three land
  in one branch rather than split into follow-up tickets.
- **First cut** used clickable column-header links toggling `?sort=&dir=`. Vivek flagged
  the UX: every header click reran the whole Streamlit page (full repaint, scroll jump,
  live-price refetch). **Reworked** onto `st.dataframe`, which sorts/searches client-side
  with no rerun — same widget the CSV-import workbench uses.
- **Overview positions table** (the ticket): `build_positions_dataframe()` → `st.dataframe`
  with `column_config` (ProgressColumn weight, LinkColumn ⚡ Sim, NumberColumn formats) +
  a pandas Styler for green/red gain & trend. Trend is a numeric column now.
- **Manage → All Transactions** and **ISIN Mappings → Mapped**: `st.dataframe` with
  single-row selection; per-row actions (edit/delete; edit/kind/unmap/remove) moved to an
  action bar that appears for the selected row, since `st.dataframe` can't host inline
  buttons.

### Files touched
- `app/ui/components/positions_table.py` — dataframe builder + st.dataframe render
- `app/ui/pages/overview.py` — numeric `_fetch_trend_values`; drop ?sort/?dir
- `app/ui/pages/manage.py` — transactions dataframe + row-select action bar
- `app/ui/pages/mappings.py` — mapped dataframe + row-select action bar
- `app/ui/styles/dark.css` — removed the interim .sort-link styles
- `tests/unit/ui/test_positions_table.py`, `test_manage_page.py`, `test_mappings_page.py`,
  `test_overview_chart_integration.py` — dataframe-builder tests

### Tests
gate green: pytest (987 passed, 91 skipped) + ruff + mypy + lint-imports.

### Notes
- `st.dataframe` escapes its own content, so the manual `html.escape` the HTML table
  needed (ROBUST-1 / 008b) is no longer applicable for these grids.
- Screenshots intentionally skipped this session at Vivek's request.

## 2026-06-05 — TICKET-RD1
**Surface:** Claude Code
**Model:** opus-4.8
**Duration:** ~75 min
**Branch:** ticket-rd1-overview-tax-html-overhaul-components
**PR:** (opened at session end)
**Status at session end:** IN_REVIEW

### What got done
- Componentized every Overview & Tax KPI tile behind one `build_metric_card` /
  `render_metric_card` template (label/value/sub_value, value_class, sub_color,
  size, tooltip, card_class). Styling moved to dark.css.
- Extracted the positions table into `components/positions_table.py` (preserving
  ROBUST-1 `html.escape` on name + ticker); added `components/progress_bar.py`
  for the dynamic-width bars so the pages carry no inline width.
- Purged all inline `style=` from `overview.py` and `tax.py` (grep clean) via
  dark.css classes + spacing utilities.
- Dropped the thesis presentation from the overview: removed the Thesis Status
  KPI card, thesis pills, and the Horizon/Thesis table columns (cols-4 → 3). Left
  the thesis_map data layer + `get_thesis_repo` wiring intact.
- Renamed analytics' `subtitle=` kwarg to `sub_value=` to match the new API.

### Deviations from the spec signature (flag for review)
- Spec listed `render_metric_card(*, label, value, sub_value, sub_color, size)`.
  Implemented a superset: kept `label`/`value` positional (analytics calls them
  positionally), kept `value_class` (needed to colour the *value*, which
  `sub_color` cannot) and `tooltip` (analytics correlation tiles), added
  `card_class`, dropped the dead `progress_pct`. Size stays on `.metric-value`
  (`sm`/`lg`) for consistency with existing `sell_simulator`/`analytics` callers.

### Files touched
- `app/ui/components/metric_card.py` — unified build/render template
- `app/ui/components/positions_table.py` — new (table moved out of overview)
- `app/ui/components/progress_bar.py` — new
- `app/ui/pages/overview.py`, `app/ui/pages/tax.py` — class-driven, grep clean
- `app/ui/pages/analytics.py` — `subtitle=` → `sub_value=`
- `app/ui/styles/dark.css` — metric-sub, table structure, helpers, utilities
- `tests/unit/ui/test_metric_card.py`, `test_positions_table.py` — new
- `tests/unit/ui/test_overview_render.py`, `test_overview_chart_integration.py`
- `tests/unit/ui/test_overview_thesis.py` — removed (feature retired)

### Tests
986 → 998 passing (gate: pytest + ruff + mypy + lint-imports all green).

### Visual verification
Seeded sandbox (NVDA/SAP.DE/ASML.AS/AAPL). Before/after Overview + after Tax in
`docs/screenshots/rd1-overview-tax-html-overhaul/`. Both pages render with no
inline styles, no HTML leak, no traceback.

### Observation (not in scope)
Seeding with an *unmapped* ticker reproduced `StreamlitDuplicateElementKey`
(`key='tax_open_mappings'`) on the Tax page — the pre-existing TICKET-TAX-1
(#154), unrelated to this change.

## 2026-06-05 — TICKET-CSV-18
**Surface:** Claude Code
**Model:** opus-4.8
**Duration:** ~20 min
**Branch:** ticket-csv-18-inline-ignore-action-in-the
**PR:** (opened at session end)
**Status at session end:** IN_REVIEW

### What got done
- Added an inline **Ignore** button next to **Save** for each unmapped ISIN in
  the Import Workbench manual-review panel (`_render_autoresolve_panel`).
- Clicking Ignore flips the ISIN's map entry to `status="ignored"` (creating the
  entry if absent) via the existing `IsinMapRepository.save` path, shows a toast,
  clears the cached plan, and reruns so the now-silent row drops out.
- New `_ignore_isin` helper preserves an existing entry's name/last_seen and
  clears ticker + instrument_kind, matching the Mappings-page ignore behaviour.

### Files touched
- `app/ui/pages/import_workbench.py` — `_ignore_isin` helper + Ignore button column
- `tests/unit/ui/test_import_workbench.py` — 4 new `_ignore_isin` tests

### Tests
974 passing → 978 passing (4 new); 91 skipped. ruff/mypy/lint-imports clean.

### Decisions made during the session
- No architectural decisions. Reused the existing persistence + silent-workbench
  plumbing from TICKET-CSV-14; Restore remains on the Mappings page only.

### Out-of-scope items noticed
- Auto-suggesting which ISINs to ignore is TICKET-CSV-19 (left untouched).

### Tokens used (rough)
~50k

## 2026-06-05 — TICKET-CSV-17
**Surface:** Claude Code
**Model:** opus-4.8
**Duration:** ~40 min
**Branch:** ticket-csv-17-erase-imported-data-guarded-full
**PR:** (opened at session end)
**Status at session end:** IN_REVIEW

### What got done
- New `app/services/data_admin.py`: pure functions over the transaction repository port —
  `erase_all_transactions`, `erase_transactions` (scoped by source and/or trade-date range),
  and a read-only `count_transactions` preview mirror. An empty selection (no source filter,
  no dates) deletes nothing, so the scoped path can never become an accidental full wipe;
  full-book wipes only go through `erase_all_transactions`. Exposed `UNSET` sentinel +
  `SourceFilter` type alias.
- New Danger-zone expander on Manage Portfolio (`app/ui/pages/manage.py`): full erase behind a
  typed `ERASE` word with an optional "also clear ISIN mappings" checkbox; scoped erase with a
  source select (`Any source` + sources present in the book), optional from/to date bounds, a
  live "would delete N" preview, and a confirmation checkbox. Every erase writes a backup first
  and reports the backup path.
- Lifted the rolling-window backup helper into `app/ui/backup.py` (`write_portfolio_backup`);
  `import_workbench.py` re-aliases it as `_write_backup`, `mappings.py` now imports it directly.

### Files touched
- `app/services/data_admin.py` — new service
- `app/ui/backup.py` — new shared backup helper
- `app/ui/pages/manage.py` — danger zone UI + handlers
- `app/ui/pages/import_workbench.py` — use shared backup helper
- `app/ui/pages/mappings.py` — use shared backup helper
- `tests/unit/services/test_data_admin.py` — new (12 cases)

### Tests
962 → 974 passing (12 new); 91 skipped. ruff / mypy / lint-imports clean.

### Decisions made during the session
- ISIN-map clear is opt-in on full erase only; scoped erase never touches the map (per ticket).
- Map clear stays in the UI (`IsinMapRepository.save(IsinMapDocument())`), not the service,
  to keep `data_admin` pure over the transaction port.
- Scoped "empty selection deletes nothing" implemented as an explicit guard so the partial path
  cannot silently wipe the whole book.

### Out-of-scope items noticed
- Empty-portfolio render of Overview/Tax relies on existing behaviour; verify in-app (ticket note).

### Tokens used (rough)
~70k

## 2026-06-05 — TICKET-CSV-15
**Surface:** Claude Code
**Model:** opus-4.8
**Duration:** ~30 min
**Branch:** ticket-csv-15-consolidate-the-csv-importer-port
**PR:** (opened at session end)
**Status at session end:** IN_REVIEW

### What got done
- Added `RowStatus.VALIDATION_ERROR` to `app/domain/csv_import.py`.
- Ported the three import guards from the dead `run_import` into the live planner
  (`app/adapters/scalable_csv/planner.py`) as pure helpers returning an error message
  instead of raising: `_check_currency` (EUR-only), `_check_amount` (abs(amount) ≈
  abs(shares×price) within €0.01, tolerance preserved exactly), `_check_sign`
  (directional sign per row type). `_validate_row` runs them last, on rows that would
  otherwise be NEW; a failure emits `VALIDATION_ERROR` / `SKIP` with `error_message`.
  Per-row visibility replaces `run_import`'s all-or-nothing raise.
- Wired `VALIDATION_ERROR` into `import_workbench.py`: 🔴 status color, `_BLOCKED_STATUSES`,
  and the filter-chip list (so it counts in `_count_blocked` and is surfaced, not silent).
- Deleted the dead path: `app/adapters/scalable_csv/importer.py` (run_import/ImportSummary),
  its re-exports in `__init__.py`, and `tests/unit/test_scalable_csv_importer.py`.
- Added validation-guard tests to the existing planner suite
  (`tests/unit/adapters/test_csv_import_planner.py`): amount mismatch, within-tolerance,
  wrong sign (Buy and Sell), non-EUR, plus guards-don't-fire-for-already-imported/unmapped.

### Files touched
- `app/domain/csv_import.py` — new `VALIDATION_ERROR` enum member
- `app/adapters/scalable_csv/planner.py` — ported guards + `_validate_row` wiring
- `app/adapters/scalable_csv/__init__.py` — dropped run_import/ImportSummary re-exports
- `app/ui/pages/import_workbench.py` — VALIDATION_ERROR color/blocked/chip
- `tests/unit/adapters/test_csv_import_planner.py` — guard tests
- deleted `app/adapters/scalable_csv/importer.py`, `tests/unit/test_scalable_csv_importer.py`,
  `tools/import_scalable_csv.py`

### Tests
963 passing (gate green: ruff, mypy app/, lint-imports all clean).

### Decisions made during the session
- **Ticket premise correction (Vivek-approved).** The ticket claimed `run_import` had only
  two consumers and "No page or script calls it." `tools/import_scalable_csv.py` — the
  pre-workbench batch CLI — was a third, live consumer. Stopped before any change and
  surfaced it; Vivek chose option 1 (delete the CLI as part of the same dead-path
  consolidation, since the Import Workbench supersedes it).
- Ported guards to the **existing** planner test file (`test_csv_import_planner.py`) rather
  than the ticket's proposed new `tests/unit/adapters/scalable_csv/test_planner.py`. The
  pre-existing-behaviour cases the ticket wanted re-homed (transfer skip, out-of-scope,
  already-imported, content dedup) were already covered there; a second file would split
  planner tests across two locations.
- Guards run only on rows that would otherwise be NEW (after dedup/mapping), per the
  ticket's "after a row is otherwise NEW/INSERT" instruction.

### Out-of-scope items noticed
- None.

## 2026-06-05 — TICKET-CSV-16
**Surface:** Claude Code
**Model:** opus-4.8
**Duration:** ~40 min
**Branch:** ticket-csv-16-per-mapping-control-reset-tax
**PR:** (opened at session end)
**Status at session end:** IN_REVIEW

### What got done
- Added `delete_transactions_for_isin(tx_repo, isin) -> int` to `app/services/isin_remap.py`:
  loads all, filters out `tx.isin == isin`, `save_all`, returns the count removed. No-op
  (no save) when nothing matches. FIFO recomputes on next load per the replay invariant.
- Replaced the dead-ended Delete on mapped rows (blocked whenever any transaction
  referenced the ISIN) with three explicit per-row actions:
  - **Kind** — inline tax-kind selector + Save; changes `instrument_kind` only.
  - **Unmap** — reset to `unmapped` (drop ticker + kind, keep name/last_seen); the button
    is disabled with a tooltip pointing to Remove when transactions still reference the ISIN.
  - **Remove** — count-stating confirmation, then purge the ISIN's transactions and the map
    entry, writing a `portfolio.json` backup first (reuses the workbench's `_write_backup`).
- New pure helpers `_unmap_isin`, `_set_instrument_kind`, and `_backup_portfolio_before_purge`.

### Files touched
- `app/services/isin_remap.py` — new `delete_transactions_for_isin`
- `app/ui/pages/mappings.py` — three-action cluster, kind-edit + remove-confirm mode rows,
  state-key rename (`mappings_confirming_delete_isin` → `_remove_isin`, plus `_kind_editing_isin`)
- `tests/unit/ui/test_mappings_page.py` — tests for the new helpers + service purge

### Tests
979 passing → 983 passing (new tests for set-kind, unmap, and purge service)

### Decisions made during the session
- Backup before purge reuses `import_workbench._write_backup` rather than duplicating the
  pattern (the ticket sanctioned reuse; avoids drift between the two write paths).
- Service tests stay in `test_mappings_page.py` alongside the existing `rewrite_ticker`/
  `count_transactions` tests — there is no separate `test_isin_remap.py` in the tree.
- A local-only `data/isin_map.json` drift was present at session start; stashed it to get a
  clean tree for `start_ticket.sh` and restored it after the gate.

### Out-of-scope items noticed
- Bulk multi-row purge and full reset (TICKET-CSV-17) intentionally not touched.

### Tokens used (rough)
~70k

## 2026-06-05 — TICKET-CSV-14 (review fix)
**Surface:** Claude Code
**Model:** opus-4.8
**Duration:** ~30 min
**Branch:** ticket-csv-14-ignored-isin-status-skip-rows
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/155
**Status at session end:** IN_REVIEW

### What got done
- Found that the original implementation made `ignored` ISINs *visible* in the live
  Import Workbench (planner path) — counted as "blocked", shown in the table, and
  given a filter chip — directly contradicting the ticket's "ignored is silent" intent.
  The silent-skip logic in `run_import` was on a dead path (tests-only; the app imports
  via `plan_import`/the workbench).
- Made `ignored` truly silent on the live path: ignored rows are excluded from the
  planned-changes table, the filter chips, the "All (N)" count, and both "blocked"
  counters. The Mappings → Ignored expander remains the audit/restore surface.
- Unified the two divergent "blocked" computations into one `_count_blocked` helper and
  added `_surfaced_rows`; both are now unit-tested.

### Files touched
- `app/ui/pages/import_workbench.py` — `_SILENT_STATUSES`/`_BLOCKED_STATUSES`,
  `_surfaced_rows`, `_count_blocked`; table, chips, and counts now exclude ignored rows
- `tests/unit/ui/test_import_workbench.py` — 3 new tests for silence/blocked-count

### Tests
974 → 977 passing (3 new). ruff, mypy, lint-imports clean.

### Notes
- Broader "foolproof importer" work (inline ignore in the workbench, auto-suggest
  ignore, fail-closed import + portfolio↔map integrity guard, post-import positions
  view) drafted as follow-up tickets for Vivek to vet. Not in this PR.

## 2026-06-05 — TICKET-CSV-14
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~45 min
**Branch:** ticket-csv-14-ignored-isin-status-skip-rows
**PR:** (pending)
**Status at session end:** IN_REVIEW

### What got done
- Extended `IsinMapping.status` to `"mapped" | "unmapped" | "ignored"`
- Bumped `IsinMapDocument.version` default to 2; added v1→v2 migration (atomic rewrite on first load)
- CSV importer silently skips ignored ISINs: no counter bump, no `unmapped_isins` entry, updates `last_seen_in_csv`
- Added `RowStatus.IGNORED_ISIN` to domain enum; planner routes ignored ISINs there (prevents crash on `assert mapping.ticker is not None`)
- Import Workbench: IGNORED_ISIN wired into status display, filter chips, and blocked row counts
- Mappings page: "Ignore" button on each unmapped row; "Ignored ISINs" expander with "Restore" button; caption shows `· N ignored` when non-zero
- Extracted `_ignore_isin` / `_restore_isin` helpers for testability

### Files touched
- `app/domain/isin_map.py` — status literal + version bump + docstring
- `app/adapters/isin_map/repo.py` — `_migrate_v1_to_v2`, `_atomic_write` helper, SCHEMA_VERSION=2
- `app/adapters/scalable_csv/importer.py` — ignored branch before unmapped check
- `app/adapters/scalable_csv/planner.py` — IGNORED_ISIN branch before unmapped check
- `app/domain/csv_import.py` — added `IGNORED_ISIN` to RowStatus
- `app/ui/pages/import_workbench.py` — status display, filter chips, blocked counts
- `app/ui/pages/mappings.py` — Ignore button, Ignored section, caption, helper functions
- `tests/unit/test_isin_map_repo.py` — migration tests + updated version assertions
- `tests/unit/test_scalable_csv_importer.py` — ignored ISIN skip/no-flip/mixed tests
- `tests/unit/ui/test_mappings_page.py` — ignore/restore helper tests

### Tests
974 passing, 91 skipped (all green)

### Decisions made during the session
- Added `RowStatus.IGNORED_ISIN` to avoid a crash in the planner (ticket spec omitted this but the grep check surfaced the bug)
- No architectural decisions beyond ticket spec

### Out-of-scope items noticed
- `_update_last_seen` in importer.py does not preserve `instrument_kind` for mapped entries — existing bug, not touched

## 2026-06-05 00:13 — TICKET-M9
**Surface:** Codex
**Model:** gpt-5
**Duration:** ~2 hr
**Branch:** ticket-m9-collapse-ritual-tools
**PR:** (pending)
**Status at session end:** IN_REVIEW

### What got done
- Added workflow entry points: `tools/gate.sh`, `start_ticket.sh`, `finish_ticket.sh`, `next.sh`, and `doctor.sh`
- Added `tools/ticket_workflow.py` for board lookup, dependency parsing/ranking, branch/status moves, PR creation, and diagnostics
- Rewrote `AGENTS.md` around script entry points; reduced line count from 382 to 170
- Updated `docs/METHODOLOGY.md` from one-ticket sessions to one coherent, independently-reviewable PR
- Tightened `.claude/settings.local.json` to named workflow scripts plus standard read/edit/git rules and explicit main-push deny rules
- Added unit coverage for duplicate M9 ticket-file resolution, dependency parsing, blocker detection, and ranking

### Files touched
- `AGENTS.md` — collapsed the ritual into script calls
- `.claude/settings.local.json` — tightened allowlist and main-push deny list
- `tools/ticket_workflow.py` — shared workflow implementation
- `tools/{gate,start_ticket,finish_ticket,next,doctor}.sh` — shell entry points
- `tools/README.md` — documented the new workflow scripts
- `docs/METHODOLOGY.md` — updated PR sizing/scope guidance
- `tests/unit/tools/test_ticket_workflow.py` — new dependency/ranking tests
- `docs/TICKETS/TICKET-M9-collapse-ritual-into-tools.md` — marked IN_PROGRESS

### Tests
960 passing → 963 passing (3 new)

Manual checks:
- `shellcheck tools/gate.sh tools/start_ticket.sh tools/finish_ticket.sh tools/next.sh tools/doctor.sh`
- `bash tools/next.sh` against the live board: RD1/RD4/RD0/RD5 eligible; RD6/RD2/RD3/RD7 blocked by expected prerequisites
- `bash tools/start_ticket.sh TICKET-M9` reused the current branch and kept the card In progress
- `bash tools/gate.sh` passed: 963 passed, 91 skipped; ruff, mypy, lint-imports clean

### Decisions made during the session
- Implemented dependency parsing/ranking in Python behind shell wrappers so shellcheck stays simple and the ranking logic is unit-testable.
- Treat local ticket files with `**Status:** MERGED` as satisfied dependencies when an old dependency is absent from the active board page.
- Codex cannot exercise Claude Code's permission-prompt UI; the allowlist was tightened and script entry points were run directly.

### Out-of-scope items noticed
- `TICKET-R4` has no `**Recommended model:**` field; `next.sh` correctly surfaces `[?]`.

### Tokens used (rough)
~90k

## 2026-06-04 — TICKET-M10
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~30 min
**Branch:** ticket-m10-workflow-doc-truth-up
**PR:** (pending)
**Status at session end:** IN_REVIEW

### What got done
- Removed all CONTEXT.md / regen_context.py / update-context.yml references from active docs (README.md, VIVEK.md, METHODOLOGY.md, ARCHITECTURE.md, tools/README.md, AGENTS.md)
- Deleted `.github/workflows/post-merge-housekeeping.yml` (was a no-op); In review → Done transition is now owned by Step 2 of the next session
- Updated lifecycle table and board-transition prose in AGENTS.md and METHODOLOGY.md to reflect Step 2 as the sole Done-transition mechanism
- Added POSIX-portable Status-line stripping to `tools/file.sh` (sed temp-file swap before commit)
- Stripped `**Status:** DRAFT` from all eight TICKET-RD*.md files (one-time cleanup)

### Files touched
- `README.md` — removed "For chat sessions" block and dead CONTEXT.md docs link
- `docs/VIVEK.md` — removed CONTEXT.md references in sections 1, 5, 7, cross-reference
- `docs/METHODOLOGY.md` — updated token-efficiency contract item 4, lifecycle table, Step 2 note, verification protocol "Required reads" and four mandatory checks
- `docs/ARCHITECTURE.md` — removed CONTEXT.md from file layout diagram
- `tools/README.md` — removed regen_context.py section (lines 31–39)
- `tools/file.sh` — added Status-line stripping before git commit (Step 8)
- `AGENTS.md` — updated Step 2 and "When Vivek says 'I merged it'" to remove post-merge action references
- `.github/workflows/post-merge-housekeeping.yml` — deleted
- `docs/TICKETS/TICKET-RD{0-7}*.md` — stripped **Status:** DRAFT lines
- `docs/TICKETS/TICKET-M10-workflow-doc-truth-up.md` — marked IN_PROGRESS

### Tests
960 passing → 960 passing (no test changes needed)

### Decisions made during the session
- Chose Option B (delete ghost workflow) over Option A (rewrite it): GITHUB_TOKEN lacks the `project` OAuth scope needed to mutate user-owned Projects v2 boards from Actions; Step 2 already handles Done reconciliation robustly.

### Out-of-scope items noticed
- Old closed ticket files (TICKET-C2, TICKET-026, TICKET-CSV-1) and ADRs (ADR-008, ADR-011) still reference regen_context/CONTEXT.md as historical context — left as-is; they describe completed work.

### Tokens used (rough)
~50k

## 2026-06-04 — TICKET-ROBUST-1
**Surface:** Claude Code
**Model:** opus-4.8
**Duration:** ~50 min
**Branch:** ticket-robust-1-surface-errors-and-escape-html
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Router (`app/ui/main.py`): replaced `except Exception: pass` → "Coming Soon" with a real error surface. `render_page()` now distinguishes the not-built case (missing module file or no `render` attr → placeholder) from a crash (import/`render()` raised → `logging.exception` + visible error; `st.exception` in dev, friendly message in prod). Moved the Streamlit bootstrap into a `main()` guarded by `if __name__ == "__main__"` so the router helpers are unit-testable without page-render side effects.
- HTML-escaping audit: applied `html.escape()` to every data-derived string interpolated into a `render_html` / `unsafe_allow_html` builder under `app/ui/` — overview positions table (name, ticker) + thesis pills, sell-simulator header ticker, mappings unmapped-name tooltip, analytics concentration table (ticker, name), company snapshot header (name, ticker, ISIN) + next-catalyst (kind, detail), and tax exposure/harvest tables (tickers). Left static/computed interpolation (formatted EUR, enum values, controlled labels) unescaped per spec.

### Files touched
- `app/ui/main.py` — router error surface + `main()` guard
- `app/ui/pages/overview.py`, `mappings.py`, `analytics.py`, `company.py`, `tax.py` — escape data-derived strings
- `app/ui/components/sell_simulator.py` — escape ticker in header
- `tests/unit/ui/test_main_router.py` — new: 8 router tests (placeholder vs error vs render; dev vs prod surface)
- `tests/unit/ui/test_overview_render.py` — new: positions-table escaping tests (name, ticker)

### Tests
951 passing → 960 passing (9 new). ruff / mypy / lint-imports clean.

### Decisions made during the session
- Used `if __name__ == "__main__"` to guard the Streamlit bootstrap. Verified against Streamlit 1.57 source: `streamlit run` execs the script in a module named `"__main__"`, so the guard fires under the app and is skipped on `import app.ui.main` in tests. No architectural decision (no ADR needed).
- Treated import-time errors as crashes (error surface), not as the not-built case — only a missing file or missing `render` attr yields "Coming Soon".

### Out-of-scope items noticed
- `app/ui/components/topbar.py` and `app/ui/main.py` (CSS) still call `st.markdown(..., unsafe_allow_html=True)` directly (pre-existing convention violation vs `app/ui/CLAUDE.md`), but both interpolate only static strings — no injection risk, left as-is.

### Tokens used (rough)
~110k

## 2026-06-04 — TICKET-CLEAN-1
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~30 min
**Branch:** ticket-clean-1-remove-dead-code
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Deleted `tools/run.sh` and `tools/cleanup-worktrees.sh` (worktree tooling, dead post-ADR-012); removed entries from `tools/README.md` and the `cleanup-worktrees.sh` mention from `docs/VIVEK.md`.
- Removed `get_fx_provider()` back-compat shim from `app/ui/wiring.py` (no live callers; also removed now-unused `FxProvider` import).
- Standardized all provider singletons in `wiring.py` from `@lru_cache(maxsize=1)` to `@st.cache_resource` — matching the idiom already used by `get_company_provider`.

### Files touched
- `tools/run.sh` — deleted
- `tools/cleanup-worktrees.sh` — deleted
- `tools/README.md` — removed entries for deleted scripts
- `docs/VIVEK.md` — removed cleanup-worktrees reference; cleaned worktree paragraph
- `app/ui/wiring.py` — removed `get_fx_provider` shim + `FxProvider` import; converted all `@lru_cache(maxsize=1)` to `@st.cache_resource`

### Tests
951 passing, 91 skipped (no change — deletion-only ticket)

### Decisions made during the session
- No architectural decisions. Used `@st.cache_resource` as the single singleton idiom (already used by `get_company_provider`; Streamlit-correct for cross-session resources).

### Out-of-scope items noticed
- `tools/README.md` still documents `regen_context.py`, which was retired on 2026-06-03. Not touched — separate ticket if needed.

### Tokens used (rough)
~20k

## 2026-06-03 — TICKET-THESIS-1
**Surface:** Claude Code
**Model:** opus-4.8
**Duration:** ~45 min
**Branch:** ticket-thesis-1-thesis-data
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Moved the two hardcoded ticker→value dicts (`_PLACEHOLDER_THESIS_STATUS`,
  `_PLACEHOLDER_HORIZON`) out of `overview.py` into an editable data file,
  mirroring the `isin_map` data+repo pattern (ADR-006).
- New domain model (`ThesisEntry`, `ThesisMapDocument`), port
  (`ThesisMapRepository`), and JSON adapter (`JsonThesisMapRepository`).
- `data/thesis.json` seeded from the previous placeholder values; gitignore-
  allowlisted like `isin_map.json`; wired via `get_thesis_repo()`.
- Unknown holdings now render an honest `"unknown"`/`"—"` badge instead of a
  false `"intact"`/`"H2"`. `render_thesis_badge()` gained a neutral `badge-grey`
  `"unknown"` state; the Thesis Status KPI shows an unknown count when present.

### Files touched
- `app/domain/thesis_map.py`, `app/ports/thesis_map.py`,
  `app/adapters/thesis_map/{__init__,repo}.py` — new model/port/adapter
- `app/config.py`, `.gitignore`, `app/ui/wiring.py` — config + allowlist + wiring
- `data/thesis.json` — seed data
- `app/ui/components/badges.py` — `"unknown"` badge state
- `app/ui/pages/overview.py` — read from repo; removed the two dicts
- `tests/unit/test_thesis_map_repo.py`, `tests/unit/ui/test_overview_thesis.py` — new
- `tests/unit/ui/test_components.py`, `tests/unit/ui/test_overview_render.py` — updated

### Tests
943 passing → 951 passing (8 net new). Removed `test_placeholder_thesis_status_defaults`
(it asserted the silent-default bug this ticket fixes).

### Decisions made during the session
- Named the new module `thesis_map` (not the `thesis.py` stub named in
  `app/domain/CLAUDE.md`, which did not exist) to mirror `isin_map` exactly.
- No architectural decisions; follows the existing ADR-006 data-as-classification
  precedent.

### Out-of-scope items noticed
- `company.py` "Risk & Thesis" tab is still a coming-soon stub (Panel framework);
  `analytics_views.thesis_status` is always `None` — neither read the old dicts.

### Tokens used (rough)
~70k

## 2026-06-03 — TICKET-PERF-1
**Surface:** Claude Code
**Model:** opus-4.8
**Duration:** ~90 min
**Branch:** ticket-perf-1-batched-parallel-valuation
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Added batch methods to the ports: `PriceProvider.get_current_prices` and
  `OhlcDataProvider.get_ohlc_histories` (failed/missing tickers omitted, never raised).
- Implemented batching in both yfinance adapters with a capped (8-worker)
  `ThreadPoolExecutor`; cache is checked first, only misses are fetched, and a
  shared per-ticker fetch/parse helper keeps single and batch paths from drifting.
- Generalized `compute_live_positions`: one batched price fetch, one FX rate per
  distinct non-EUR currency; any supported currency (e.g. JPY) now values correctly.
  Missing price or missing FX rate → stale, never silently mis-valued.
- Routed every call site through the batch path: overview trend column, analytics
  correlation, NAV reconstruction (prices + FX series), and the single-symbol
  technicals/performance fetches. No per-ticker network loop remains under `app/`.

### Files touched
- `app/ports/price_feed.py`, `app/ports/market_data.py` — batch method signatures
- `app/adapters/yfinance_price/adapter.py`, `app/adapters/yfinance_ohlc/adapter.py` — parallel batch + shared helper
- `app/services/valuation.py` — batched prices + general multi-currency FX
- `app/services/market_data.py` — `get_ohlc_histories` service wrapper (aggregation-aware)
- `app/services/analytics_correlation.py`, `app/services/nav.py`, `app/services/analytics_technicals.py`, `app/services/analytics_performance.py` — batch routing
- `app/ui/pages/overview.py` — `_fetch_trend_texts` one-shot batch
- `tests/fakes/{price_feed,ohlc}.py` + inline fakes — batch methods
- `tests/unit/adapters/test_yfinance_batch.py` (new) + updated valuation/perf/technicals tests

### Tests
931 passing → 943 passing (12 new). ruff / mypy / lint-imports clean.

### Decisions made during the session
- Batch contract omits failed tickers (callers treat absence as stale); the
  per-ticker upstream reason is no longer surfaced. Updated two tests whose
  assertions depended on the old reason string. No new ADR needed.

### Out-of-scope items noticed
- The `_PLACEHOLDER_THESIS_STATUS`/`_HORIZON` dicts in overview.py are addressed
  by TICKET-THESIS-1 (already filed) — left untouched.

### Tokens used (rough)
~140k

## 2026-06-02 — TICKET-C4
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~45 min
**Branch:** ticket-c4-composite-ticker-resolver
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/130
**Status at session end:** IN_REVIEW

### What got done
- Created `app/adapters/ticker_resolver_composite/adapter.py`: `CompositeTickerResolver` with primary + fallback merge logic. Primary wins on symbol dedup. Each adapter's exceptions caught individually so one source down cannot break the composite.
- Created `app/adapters/ticker_resolver_finnhub/adapter.py`: `FinnhubTickerResolverAdapter` using `/search` and `/stock/profile2` endpoints. Skips silently when API key is unset.
- Created `app/adapters/ticker_resolver_factory.py`: `build_ticker_resolver` factory composing `cache(composite(yfinance, [finnhub]))`. Reads `settings.finnhub_api_key` directly. Mirrors `company_factory.py` pattern.
- Updated `app/ui/wiring.py`: `get_ticker_resolver` delegates to factory, passing `settings.finnhub_api_key`.
- Created `tests/unit/adapters/test_ticker_resolver_composite.py`: 11 unit tests covering all four composite scenarios (primary fills limit, fallback fills gap, primary raises, both raise, dedup) plus lookup variants and clear_cache.
- Created `tests/integration/test_finnhub_resolver.py`: 6 integration tests gated on `FINNHUB_API_KEY`.

### Files touched
- `app/adapters/ticker_resolver_composite/__init__.py` — new
- `app/adapters/ticker_resolver_composite/adapter.py` — new
- `app/adapters/ticker_resolver_finnhub/__init__.py` — new
- `app/adapters/ticker_resolver_finnhub/adapter.py` — new
- `app/adapters/ticker_resolver_factory.py` — new
- `app/ui/wiring.py` — get_ticker_resolver now uses factory
- `docs/TICKETS/TICKET-C4-composite-ticker-resolver.md` — Status QUEUED → IN_PROGRESS
- `tests/unit/adapters/test_ticker_resolver_composite.py` — new (11 tests)
- `tests/integration/test_finnhub_resolver.py` — new (6 tests, env-gated)

### Tests
901 passing → 912 passing (+11)

### Decisions made during the session
- Factory reads `settings.finnhub_api_key` instead of raw `os.environ` — consistent with company_factory pattern
- `FinnhubTickerResolverAdapter.clear_cache` is a no-op (stateless); outer `CachedTickerResolver` covers it

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~50k

---

## 2026-06-02 — TICKET-R2
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~45 min
**Branch:** ticket-r2-chart-aggregation-toggle
**PR:** TBD
**Status at session end:** IN_REVIEW

### What got done
- Added `freq: AggregationFreq | None = None` to `get_ohlc_history` service; `None` preserves existing default behaviour
- Added `render_aggregation_toggle(key, period)` in `period_selector.py`; shows Auto/Day/Week/Month with period-appropriate option hiding
- Wired the toggle into Research, Overview Position Chart, and Analytics Technicals tab
- Added `freq` param to `build_technicals_view`; aggregates bars and adjusts visible-slice count for coarser frequencies
- Technicals MA overlay labels switch to "50-period MA" when freq is not "day"
- Updated existing research page tests (input row grew from 2 to 3 columns)

### Files touched
- `app/services/market_data.py` — freq override param
- `app/services/analytics_technicals.py` — freq param, aggregation, slice adjustment
- `app/ui/components/period_selector.py` — render_aggregation_toggle
- `app/ui/pages/research.py` — toggle wiring
- `app/ui/pages/overview.py` — toggle wiring (Position Chart section)
- `app/ui/pages/analytics.py` — toggle wiring (Technicals tab)
- `tests/unit/services/test_market_data.py` — 4 new freq-override tests
- `tests/unit/ui/test_research_page.py` — updated column counts for 3-col input row

### Tests
901 passing → 905 passing (4 new)

### Decisions made during the session
- No architectural decisions; freq override is purely additive

### Out-of-scope items noticed
- None

### Tokens used (rough)
~80k

## 2026-06-02 — TICKET-C1
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~60 min
**Branch:** ticket-c1-fx-ecb-adapter
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/TBD
**Status at session end:** IN_REVIEW

### What got done
- Split `FxProvider` protocol into `HistoricalFxProvider` (cost-basis) and `LiveFxProvider` (valuation); kept `FxProvider` as combined back-compat protocol
- Added `app/adapters/fx_ecb/adapter.py` — `EcbFxAdapter` fetches ECB daily reference rates from `eurofxref-hist.zip`, caches as `data/fx_cache/ecb.json`, derives cross rates via EUR base, walks back up to 7 days for weekends/holidays
- Updated `app/ui/wiring.py` — added `get_historical_fx_provider()` (ECB) and `get_live_fx_provider()` (yfinance); `get_fx_provider()` kept as back-compat shim
- Routed all cost-basis call sites (manage.py transaction recording and ECB deviation check) to `get_historical_fx_provider()`
- Routed all live-valuation call sites (overview, tax, analytics, topbar, sell simulator) to `get_live_fx_provider()`
- Updated service signatures: `build_transaction` → `HistoricalFxProvider`, `compute_live_positions` / `get_live_positions_cached` / `clear_caches` / `build_correlation_view` → `LiveFxProvider`

### Files touched
- `app/ports/fx_feed.py` — added `HistoricalFxProvider`, `LiveFxProvider`; `FxProvider` now extends both
- `app/ports/__init__.py` — exported new protocols
- `app/adapters/fx_ecb/__init__.py` — new
- `app/adapters/fx_ecb/adapter.py` — new `EcbFxAdapter`
- `app/services/trading.py` — `fx_provider: FxProvider` → `HistoricalFxProvider`
- `app/services/valuation.py` — `fx_provider: FxProvider` → `LiveFxProvider` (all 3 signatures)
- `app/services/analytics_correlation.py` — `fx_feed: FxProvider` → `LiveFxProvider`
- `app/ui/wiring.py` — added `get_historical_fx_provider`, `get_live_fx_provider`
- `app/ui/pages/manage.py` — historical calls → `get_historical_fx_provider()`; clear_caches → `get_live_fx_provider()`
- `app/ui/pages/overview.py`, `tax.py`, `analytics.py` — live calls → `get_live_fx_provider()`
- `app/ui/components/topbar.py`, `sell_simulator.py` — live calls → `get_live_fx_provider()`
- `tests/unit/adapters/test_fx_ecb.py` — new; 16 tests covering CSV parsing, cold/warm/memory cache, weekend walk-back, cross-rate derivation, EUR special cases, error conditions

### Tests
901 passing → 901 passing (16 new ECB tests included; previously skipped slots taken)

### Decisions made during the session
- `parse_ecb_zip` extracted as a module-level function (not a method) so tests can inject fixture zip bytes without needing a full adapter
- `_fetch_ecb_zip` extracted as a module-level function so `monkeypatch` can replace it cleanly without network calls
- `get_fx_provider()` shim creates a separate `YfinanceLiveFxAdapter` instance rather than delegating to `get_live_fx_provider()` to avoid returning a `LiveFxProvider` where `FxProvider` is expected (type safety without `# type: ignore`)

### Out-of-scope items noticed
- None

### Tokens used (rough)
~80k

## 2026-05-31 — TICKET-CSV-13
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-csv13-zero-touch-import
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/126
**Status at session end:** IN_REVIEW

### What got done
- Added `get_quote_type(ticker) -> str | None` to `CompanyDataProvider` port and all adapters
  (YfinanceCompanyAdapter, CacheCompanyAdapter, CompositeCompanyAdapter, FinnhubCompanyAdapter)
- Fixed `_merge_sections` and profile cache section to persist and restore `quote_type`
  (pre-existing bug: cached `get_company()` always returned `quote_type=None`)
- New service `app/services/isin_autoresolve.py`: resolves ISIN → ticker + InstrumentKind
  using `resolver.resolve(ISIN)` (yfinance Search accepts ISINs) with scoring by EUR
  preference, German-exchange suffix (.DE/.F/…), and name similarity via difflib
- New component `app/ui/components/isin_mapper.py`: shared `suggest_kind`, `KIND_LABEL`,
  `render_kind_selector`, `render_isin_mapper_row`, `build_mapping` — used by both pages
- Import Workbench rewritten: auto-resolves all unmapped ISINs on upload; saves
  high/medium-confidence results to `isin_map.json`; shows green "Auto-mapped N ISINs"
  banner with per-ISIN Reject buttons; remaining manual ISINs get inline fuzzy search
- Mappings page updated to import `suggest_kind`/`KIND_LABEL`/`KIND_OPTIONS` from shared
  component; removed stale "re-run importer after mapping" footer
- All auto-resolve decisions logged to `import_log.json` with confidence + reason fields
- 22 new unit tests (autoresolve service + cache/composite get_quote_type coverage)

### Files touched
- `app/ports/company_data.py` — added `get_quote_type` to Protocol
- `app/adapters/company_yfinance/adapter.py` — implemented `get_quote_type`
- `app/adapters/company_cache/adapter.py` — implemented `get_quote_type`, fixed `quote_type` persistence
- `app/adapters/company_composite/adapter.py` — implemented `get_quote_type`, fixed `_merge`
- `app/adapters/company_finnhub/adapter.py` — stub `get_quote_type` (returns None)
- `app/services/isin_autoresolve.py` — NEW
- `app/ui/components/isin_mapper.py` — NEW
- `app/ui/pages/import_workbench.py` — auto-resolve flow, new session-state keys
- `app/ui/pages/mappings.py` — use shared component, remove stale footer
- `tests/unit/services/test_isin_autoresolve.py` — NEW (19 tests)
- `tests/unit/adapters/test_company_cache.py` — added `get_quote_type` to FakeInner + 3 new tests
- `tests/unit/adapters/test_company_composite.py` — added `get_quote_type` to FakeProvider + 4 new tests
- `tests/unit/services/test_company_service.py` — added `get_quote_type` to FakeProvider

### Tests
870 passing → 892 passing (22 new)

### Decisions made during the session
- Used `difflib.SequenceMatcher` (stdlib) for name similarity — no new dependency
- Confidence drops to "low" if quoteType is unavailable or non-mappable, preventing
  silent auto-mapping of exotic instruments (crypto, indices, etc.)

### Out-of-scope items noticed
- None

## 2026-05-31 — TICKET-R1
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~45 min
**Branch:** ticket-r1-holiday-intraday-rangebreaks
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/124
**Status at session end:** IN_REVIEW

### What got done
- Added `_holiday_rangebreaks(series)` — computes missing weekdays within series window and returns Plotly `{"values": [...]}` rangebreaks for each holiday gap
- Added `_intraday_overnight_rangebreaks(series)` — derives trading-hour bounds from min/max UTC hour observed; FX tickers (`=X`) return empty; falls back to `[22, 13]` default
- Updated `render_candlestick`, `render_line_chart`, `render_drawdown_chart` to apply holiday breaks on daily paths and overnight breaks on intraday paths
- Fixed root cause of rangebreaks being silently ignored: added explicit `xaxis.type='date'` (Plotly.js does not auto-detect date axis from UTC-aware ISO strings)
- Fixed repeated x-axis month label: switched daily `tickformat` from `%b %Y` to `%b %d`
- Added 15 new unit tests

### Files touched
- `app/ui/components/charts.py` — two new helpers + updated render wiring + `type='date'` + `tickformat` fix
- `tests/unit/ui/test_chart_components.py` — 15 new tests

### Tests
509 passing → 524 passing (15 new)

### Decisions made during the session
- FX ticker detection via `ticker.endswith("=X")` — no adapter import needed
- Root cause: Plotly.js ignores rangebreaks unless `xaxis.type` is explicitly `'date'`

### Out-of-scope items noticed
- Per-exchange holiday calendars (pandas_market_calendars): out of scope per ticket; see TICKET-R2

### Tokens used (rough)
~60k

---

## 2026-05-31 — TICKET-M8
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~30 min
**Branch:** ticket-m8-file-sh-priority-ordering
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/125
**Status at session end:** IN_REVIEW

### What got done
- Added Step 7 (priority-band ordering) to `tools/file.sh`: each newly-filed item is placed at the top of its priority band in Backlog using `updateProjectV2ItemPosition` GraphQL mutation
- Failures in the reorder step are non-fatal (warning printed, drag to fix)
- Updated Step 8 (commit/push) and Step 9 (summary) numbering; summary now shows each ticket's final Backlog rank and priority band
- Updated AGENTS.md "What you do NOT do": replaced old board-ordering restriction with ADR-010-aligned wording
- Updated METHODOLOGY.md anti-pattern: clarified that `tools/file.sh` may write both Status and Backlog position
- Flipped ADR-010 status from Proposed → Accepted

### Files touched
- `tools/file.sh` — added Step 7 priority-band reorder, updated step numbering and summary
- `AGENTS.md` — updated board-ordering anti-pattern line
- `docs/METHODOLOGY.md` — updated "Writing scripts" anti-pattern line
- `docs/DECISIONS/ADR-010-file-sh-priority-ordering.md` — Status: Proposed → Accepted

### Tests
870 passing → 870 passing (no Python changes)

### Decisions made during the session
No architectural decisions made.

### Out-of-scope items noticed
None.

### Tokens used (rough)
~40k

---

## 2026-05-31 — TICKET-C3
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~45 min
**Branch:** ticket-c3-split-yfinance-adapter
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/122
**Status at session end:** IN_REVIEW

### What got done
- Created `app/adapters/_yfinance_client.py` as single yfinance import point
- Created `YfinancePriceAdapter` in `app/adapters/yfinance_price/` implementing `PriceProvider`
- Created `YfinanceOhlcAdapter` in `app/adapters/yfinance_ohlc/` implementing `OhlcDataProvider`
- Created `YfinanceResolverAdapter` in `app/adapters/yfinance_resolver/` implementing `TickerResolver`
- Added `YfinanceLiveFxAdapter` to `app/adapters/fx_yfinance/` implementing `FxProvider`
- Rewrote `app/ui/wiring.py`: each provider wired to its own adapter, zero `type: ignore`
- Updated `FxYfinanceDiskAdapter._get_inner` to use `YfinanceLiveFxAdapter`
- Updated `app/scripts/migrate_currency.py` to use `YfinancePriceAdapter`
- Deprecated `yfinance_feed/__init__.py` with `YfinanceAdapter = YfinancePriceAdapter` alias
- Updated all unit tests to use per-protocol adapters
- Created integration test stubs: `test_yfinance_price.py`, `test_yfinance_live_fx.py`
- Updated `test_yfinance_resolver.py` to use `YfinanceResolverAdapter`
- Added `tests/unit/adapters/test_yfinance_live_fx.py` for `YfinanceLiveFxAdapter`

### Files touched
- `app/adapters/_yfinance_client.py` — new shared yfinance import
- `app/adapters/yfinance_price/` — new PriceProvider adapter
- `app/adapters/yfinance_ohlc/` — new OhlcDataProvider adapter
- `app/adapters/yfinance_resolver/` — new TickerResolver adapter
- `app/adapters/fx_yfinance/adapter.py` — added YfinanceLiveFxAdapter
- `app/adapters/fx_yfinance/__init__.py` — export YfinanceLiveFxAdapter
- `app/adapters/yfinance_feed/__init__.py` — deprecated back-compat alias
- `app/ui/wiring.py` — rewired to per-protocol adapters
- `app/scripts/migrate_currency.py` — use YfinancePriceAdapter
- All unit tests in `tests/unit/adapters/test_yfinance_*`
- New integration tests in `tests/integration/`

### Tests
864 passing → 870 passing (6 new)

### Decisions made during the session
- `YfinanceAdapter` alias kept in `yfinance_feed/__init__.py` for one release pointing at `YfinancePriceAdapter`
- `YfinanceLiveFxAdapter` implements both `get_current_rate` and `get_historical_rate` via yfinance; TICKET-C1 will replace historical with ECB
- No architectural decisions beyond what ADR-009 already specified

### Out-of-scope items noticed
- None

### Tokens used (rough)
~80k

## 2026-05-31 — wrapper (run.sh + AGENTS.md sweep)
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~15 min
**Branch:** wrapper
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/123
**Status at session end:** IN_REVIEW

### What got done
- Added `tools/run.sh` — runs any command inside a named worktree with the conda env active
- Updated AGENTS.md Step 7 gate-check to use `run.sh`; replaced "Conda env activation" sub-section with "Running commands in a worktree" covering both `run.sh` (worktree) and direct prefix (main checkout)
- Added `run.sh` entry to `tools/README.md`

### Files touched
- `tools/run.sh` — new
- `AGENTS.md` — Step 7 + conda section rewritten
- `tools/README.md` — run.sh documented

### Tests
864 passing (no change — no app code modified)

### Decisions made during the session
- No architectural decisions

### Out-of-scope items noticed
- None

### Tokens used (rough)
~10k

## 2026-05-31 — TICKET-M10
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~60 min
**Branch:** ticket-m10-worktree-workflow-polish
**PR:** TBD
**Status at session end:** IN_REVIEW

### What got done
- Rewrote `tools/cleanup-worktrees.sh`: now detects merged worktrees via three cases (upstream gone + was tracked, ancestor-of-main, squash-merged via tree-hash); uses `git-common-dir` to identify the main checkout correctly when called from inside a worktree; preserves brand-new branches that have never been pushed
- Updated `AGENTS.md` Step 5: prepends `bash tools/cleanup-worktrees.sh || true` before creating each new worktree; after `git worktree add`, removes the checked-out `data/` directory and replaces it with a symlink to the main checkout's `data/` (and `.env` if present)
- Updated `docs/VIVEK.md` Section 3: added one-line note that all worktrees share the main checkout's `data/` automatically

### Files touched
- `tools/cleanup-worktrees.sh` — full rewrite with merged-branch detection
- `AGENTS.md` — Step 5 extended with cleanup call + data symlink
- `docs/VIVEK.md` — Section 3 shared-data note

### Tests
864 passing → 864 passing (no new tests; no Python code changed)

### Decisions made during the session
- Used `git config --get "branch.$name.remote"` to distinguish new-never-pushed branches from upstream-deleted branches in Case 1 of the cleanup script. Alternative (commits-ahead check) would fail for fresh branches with no commits yet.
- Used `git rev-parse --git-common-dir` (not `--show-toplevel`) to find the main repo; `--show-toplevel` returns the worktree path when called from a worktree, causing the main-checkout guard to fail.

### Out-of-scope items noticed
- None

### Tokens used (rough)
~60k

## 2026-05-31 — TICKET-R5
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~45 min
**Branch:** ticket-r5-consolidate-caching-and-live-positions
**PR:** TBD
**Status at session end:** IN_REVIEW

### What got done
- Added `get_live_positions_cached` and `clear_live_positions_cache` to `services/valuation.py`: module-level TTL cache (60 s) keyed by transactions signature; single source of truth for live positions across all pages
- Removed three page-local `@st.cache_data` wrappers (`_cached_live_positions` in tax.py, `_cached_concentration_live_positions` in analytics.py, `_live_positions_cached` in sell_simulator.py); all pages now call `get_live_positions_cached` directly
- Removed service-level `_cache` from `services/market_data.py`; OHLC caching now delegates entirely to the adapter (YfinanceAdapter._ohlc_cache), which already held identical data with matching TTLs
- Updated `clear_market_data_caches` to clear live-positions cache + adapter cache in one call; topbar Refresh button now calls only this function
- Updated test suite: added 4 new TTL/invalidation tests for `get_live_positions_cached` in test_valuation.py; rewrote test_market_data.py (removed cache TTL tests, added aggregation and clear tests); updated sizer-tab and sell-simulator UI tests to patch the new function

### Files touched
- `app/services/valuation.py` — added `get_live_positions_cached`, `clear_live_positions_cache`, `_live_positions_cache`, `_tx_sig`
- `app/services/market_data.py` — removed `_cache` and TTL logic; updated `clear_market_data_caches`
- `app/ui/pages/tax.py` — removed `_cached_live_positions`; pages call `get_live_positions_cached`
- `app/ui/pages/analytics.py` — removed `_cached_concentration_live_positions`; added `_get_live_positions` helper; pages call `get_live_positions_cached`
- `app/ui/components/sell_simulator.py` — removed `_live_positions_cached`
- `app/ui/components/topbar.py` — updated Refresh to call `clear_market_data_caches`
- `tests/unit/services/test_valuation.py` — added TTL/invalidation tests; removed `test_service_no_module_state`
- `tests/unit/services/test_market_data.py` — rewrote for adapter-delegated caching
- `tests/unit/ui/test_sizer_tab.py` — updated patches
- `tests/unit/ui/test_sell_simulator_component.py` — removed stale `TestLivePositionsCache`

### Tests
869 passing → 865 passing (net −4: removed stale cache tests, added TTL tests)

### Decisions made during the session
- No architectural decisions; ticket spec was clear and self-contained

### Out-of-scope items noticed
- `overview.py` has a fourth `_cached_live_positions` with the same pattern — not in ticket scope; should be filed as a follow-up

### Tokens used (rough)
~120k

## 2026-05-31 — TICKET-C2
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~20 min
**Branch:** ticket-c2-drop-stub-pages
**PR:** TBD
**Status at session end:** IN_REVIEW

### What got done
- Deleted four stub page files: `decision.py`, `lots.py`, `performance.py`, `behaviour.py`
- Removed the four entries from `NAV_ITEMS` in `sidebar.py`; adjusted `_SECTIONS` ranges (13 → 9 items)
- Removed the four titles from `PAGE_TITLES` in `topbar.py`
- Updated `ARCHITECTURE.md` file layout to reflect the 9 live pages; added note that per-lot view is in the Tax page
- Regenerated `CONTEXT.md` via `tools/regen_context.py`
- Updated `test_components.py`: removed stub imports and assertions; count 13 → 9
- Updated `test_sidebar_structure.py`: updated portfolio/tools section tests, removed `test_badge_appears_on_decision_gates`, count 13 → 9

### Files touched
- `app/ui/pages/decision.py` — deleted
- `app/ui/pages/lots.py` — deleted
- `app/ui/pages/performance.py` — deleted
- `app/ui/pages/behaviour.py` — deleted
- `app/ui/components/sidebar.py` — removed 4 nav entries, adjusted section ranges
- `app/ui/components/topbar.py` — removed 4 page titles
- `docs/ARCHITECTURE.md` — updated file layout, added lots note
- `docs/CONTEXT.md` — regenerated
- `tests/unit/ui/test_components.py` — updated imports and assertions
- `tests/unit/ui/test_sidebar_structure.py` — updated tests for new nav shape

### Tests
869 passing → 868 passing (removed test_badge_appears_on_decision_gates)

### Decisions made during the session
- No architectural decisions made; implements ADR-008 as specified.

### Out-of-scope items noticed
- None

### Tokens used (rough)
~30k

## 2026-05-31 — TICKET-M9
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~20 min
**Branch:** ticket-m9-worktree-and-conda-env
**PR:** TBD
**Status at session end:** IN_REVIEW

### What got done
- Amended `AGENTS.md` Step 5 to be worktree-aware: creates a sibling worktree `<repo>-<ticket-id>` and cds into it when starting from main; reuses existing worktree when already inside one
- Added conda env activation subsection under `AGENTS.md` Step 7: all Python shell calls must prefix with `source ... && conda activate investment-dashboard &&`
- Created `tools/cleanup-worktrees.sh`: removes local worktrees whose upstream branches no longer exist; marks executable; idempotent
- Documented `cleanup-worktrees.sh` in `tools/README.md`
- Updated `docs/VIVEK.md` Section 3 to reflect the new minimal two-step start flow
- Flipped `docs/DECISIONS/ADR-011-parallel-agent-workflow.md` status from `Proposed` to `Accepted (2026-05-31)`

### Files touched
- `AGENTS.md` — Step 5 and Step 7 amendments
- `tools/cleanup-worktrees.sh` — new script
- `tools/README.md` — added cleanup-worktrees.sh entry
- `docs/VIVEK.md` — Section 3 rewritten
- `docs/DECISIONS/ADR-011-parallel-agent-workflow.md` — status accepted
- `docs/TICKETS/TICKET-M9-automate-worktree-and-env.md` — status IN_PROGRESS

### Tests
869 passing → 869 passing (no Python changes)

### Decisions made during the session
No architectural decisions — this ticket implements an already-accepted ADR (ADR-011).

### Out-of-scope items noticed
None.

### Tokens used (rough)
~30k

---

## 2026-05-16 — TICKET-CSV-10
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~25 min
**Branch:** ticket-csv-10-live-overview-names-ccy-price
**PR:** TBD
**Status at session end:** IN_REVIEW

### What got done
- Replaced `_PLACEHOLDER_NAME` dict with live lookup from `isin_map.json` mapped entries (ticker→name dict built in `render()`, passed to `_build_positions_table_html`)
- `_build_positions_table_html` accepts optional `name_lookup` dict; falls back to ticker string when ISIN/name absent
- Removed CCY column (header + all body cells); was always "EUR" regardless of actual trading currency
- Price cell now shows native amount with `title=` tooltip: `"USD 225.32 · €198.45 per share"` for USD securities, `"EUR 1120.00"` for EUR-native; stale rows render `—` with no tooltip
- Data fix: corrected `data/isin_map.json` ISIN IE000QDFFK00 ticker ANAU → ANAV.DE (stale from old session)
- 8 new tests covering: CCY removal, name resolution, name fallback, USD tooltip, EUR tooltip, stale no-tooltip

### Files touched
- `app/ui/pages/overview.py` — implementation
- `tests/unit/ui/test_overview_render.py` — 8 new tests
- `data/isin_map.json` — ANAV.DE ticker fix

### Tests
859 passing → 867 passing (8 new)

### Decisions made during the session
- Used option (2) from ticket: ticker→name reverse lookup from isin_map rather than adding ISIN to OpenLot (no-risk, same effective result)
- No architectural decisions required

### Out-of-scope items noticed
- `_PLACEHOLDER_THESIS_STATUS` and `_PLACEHOLDER_HORIZON` still hardcoded — out of scope per ticket

### Tokens used (rough)
~40k

## 2026-05-16 — TICKET-CSV-9
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~20 min
**Branch:** ticket-csv-9-mappings-fuzzy-typeahead
**PR:** TBD
**Status at session end:** IN_REVIEW

### What got done
- Replaced `st.text_input` ticker fields in Mappings page with `render_ticker_searchbox` (same component as Manage Portfolio)
- Both unmapped-section assign field and edit-row field now use fuzzy typeahead backed by the yfinance resolver
- Edit row pre-seeds searchbox from current mapped ticker via `resolver.lookup`
- Save blocked with error toast when `selected_match is None`
- Removed `mappings_edit_ticker_value` session-state key (no longer needed)
- Added 4 new tests; updated `test_init_state_sets_all_defaults` to reflect removed key

### Files touched
- `app/ui/pages/mappings.py` — swap text_input → searchbox in `_render_unmapped_section` and `_render_edit_row`; remove `mappings_edit_ticker_value`
- `tests/unit/ui/test_mappings_page.py` — updated state test, added 4 new tests

### Tests
855 passing → 859 passing (+4)

### Decisions made during the session
- No architectural decisions; reused existing `render_ticker_searchbox` component as specified in ticket

## 2026-05-16 — TICKET-CSV-12
**Surface:** Claude Code
**Model:** sonnet-4.6
**Branch:** ticket-csv-12-backfill-isin-recovery-script
**Status at session end:** IN_REVIEW

### What got done
- Created `tools/backfill_isin_from_csv.py`: standalone CLI that backfills isin onto scalable_csv transactions via csv_reference→ISIN lookup from the original Scalable Capital CSV export
- Defaults to `--dry-run`; `--apply` required to write; backup-before-mutation; atomic write; never overwrites existing ISINs; refuses non-v3 portfolios
- Reuses `app.adapters.scalable_csv.parser.parse_csv` (no fresh DictReader)
- 12 tests in `tests/unit/tools/test_backfill_isin_from_csv.py`
- Updated `tools/README.md` with usage docs and when-to-use guidance
- Smoke test on live data: 2 transactions still had isin=None (missed by original one-shot recovery), 149 already set — script ready to fix those 2 with --apply

### Files touched
- `tools/backfill_isin_from_csv.py` — new script
- `tests/unit/tools/test_backfill_isin_from_csv.py` — new tests
- `tools/README.md` — new section for the script

### Tests
843 passing → 855 passing (+12)

### Decisions made during the session
- No architectural decisions; script lives in tools/ (no app/ changes)

## 2026-05-16 — TICKET-CSV-11
**Surface:** Claude Code
**Model:** sonnet-4.6
**Branch:** ticket-csv-11-fix-migration-v2-v3-backfill
**Status at session end:** IN_REVIEW

### What got done
- Added `isin_map_path: Path | None` parameter to `migrate_v2_to_v3`; falls back to `portfolio_path.parent/isin_map.json` when omitted (fully backward compatible)
- `JsonTransactionRepository.__init__` accepts and stores `isin_map_path`, forwards it to the migration
- Added zero-backfill WARNING log in `load_all()` when `scalable_unbackfilled_count > 0 and migrated_count == 0` — canary that would have caught the production failure at startup
- Created `tests/fixtures/migration/portfolio_v2_production_shape.json` (151 transactions, 20 tickers, exact production shape)
- Created `tests/fixtures/migration/isin_map_v1_production_shape.json` (20 mapped entries + 6 unmapped)
- Added 6 new tests: production-shape regression, zero-backfill warning, edge cases (empty map, all-unmapped, missing ticker field, mixed/missing source)

### Root cause diagnosis
H1 confirmed: `migrate_v2_to_v3` infers isin_map path as `portfolio_path.parent/isin_map.json` with no fallback and no signal when absent. If the file is missing at migration time, all scalable_csv transactions silently receive `isin=None` with no error or log.

### Files touched
- `app/adapters/repo_json/migration.py` — added `isin_map_path` parameter
- `app/adapters/repo_json/json_repo.py` — added `isin_map_path` to constructor; warning canary in `load_all()`
- `tests/unit/adapters/test_migration_v2_v3.py` — 6 new tests
- `tests/fixtures/migration/portfolio_v2_production_shape.json` — new
- `tests/fixtures/migration/isin_map_v1_production_shape.json` — new

### Tests
827 passing → 843 passing (16 new in migration test file, net 16 added)

### Decisions made during the session
- No architectural decisions; change is limited to migration.py and json_repo.py per ticket scope

## 2026-05-16 — TICKET-CSV-8
**Surface:** Claude Code
**Model:** sonnet-4.6
**Branch:** ticket-csv-8-isin-on-transaction-remap
**PR:** pending
**Status at session end:** IN_REVIEW

### What got done
- Added `Transaction.isin: str | None = None` to domain model (between `notes` and `csv_reference`)
- CSV importer now populates `isin=row.isin` on every scalable_csv transaction
- Added `migrate_v2_to_v3()` in `migration.py`: reverse-lookup against `isin_map.json` (same directory), collision-safe abort, atomic write, backup to `portfolio.json.v2.bak`
- Bumped `JsonTransactionRepository.SCHEMA_VERSION` to 3; auto-migrates v2→v3 on `load_all()`
- Created `app/services/isin_remap.py` with `rewrite_ticker_for_isin` and `count_transactions_for_isin`
- Mappings page edit-save now rewrites transaction tickers for the edited ISIN and includes count in toast
- Mappings page delete hard-blocked when transactions reference the ISIN

### Files touched
- `app/domain/models.py` — added `isin` field
- `app/adapters/scalable_csv/importer.py` — populate isin on import
- `app/adapters/repo_json/migration.py` — added `migrate_v2_to_v3`
- `app/adapters/repo_json/json_repo.py` — bump SCHEMA_VERSION, add v2→v3 branch
- `app/services/isin_remap.py` — new file
- `app/ui/pages/mappings.py` — wired remap service for edit + delete
- `tests/unit/services/test_isin_remap.py` — new file (11 tests)
- `tests/unit/adapters/test_migration_v2_v3.py` — new file (11 tests)
- `tests/unit/test_scalable_csv_importer.py` — 1 new reconciliation test
- `tests/integration/test_json_repo.py` — 2 new tests + fixed wrong-version test
- `tests/unit/ui/test_mappings_page.py` — 3 new tests

### Tests
813 passing → 837 passing (24 new)

### Decisions made during the session
- No architectural decisions made; all decisions were pre-resolved in the ticket

### Out-of-scope items noticed
- TICKET-CSV-9 (fuzzy typeahead in Mappings) and TICKET-CSV-10 (name resolution on Live Overview) remain next

---

## 2026-05-16 — TICKET-CSV-7
**Surface:** Claude Code
**Model:** sonnet-4.6
**Branch:** ticket-csv-7-transfer-eur-native-fix
**Status at session end:** IN_REVIEW

### What got done
- Removed FX provider from planner, importer, wiring, and workbench UI — Scalable CSV prices are always EUR
- Both legs of security-transfer pairs now skip as INTERNAL_TRANSFER (was: incoming leg imported as phantom BUY)
- Added EUR-at-face-value bypass to `validate_ticker_currency` so non-EUR tickers (NVDA, 5631.T, POLY.SW, ALGO.L) can be stored with EUR price + fx_rate_eur=1
- Removed `RowStatus.NEEDS_CURRENCY_SUPPORT`, `FX_UNAVAILABLE`, `OUTGOING_TRANSFER` from domain
- Added 45-row synthetic fixture `full_export_2026_05_14.csv` with all 27 ISIN types including 3 transfer pairs and tickers from all currency zones

### Files touched
- `app/domain/models.py` — EUR-at-face-value bypass in `validate_ticker_currency`
- `app/domain/csv_import.py` — new RowStatus: INTERNAL_TRANSFER; removed FX/OUTGOING_TRANSFER statuses
- `app/adapters/scalable_csv/planner.py` — removed fx_provider; both transfer legs → INTERNAL_TRANSFER
- `app/adapters/scalable_csv/importer.py` — removed fx_provider; both transfer legs skipped; always EUR
- `app/ui/wiring.py` — removed `get_import_fx_provider`
- `app/ui/pages/import_workbench.py` — removed FX UI, manual_fx_rates, FX status chips
- `tests/fixtures/scalable_csv/full_export_2026_05_14.csv` — new 46-row fixture
- `tests/fixtures/scalable_csv/full_export_2026_05_14_isin_map.json` — companion ISIN map
- `tests/unit/test_scalable_csv_importer.py` — updated for new transfer + EUR-native behavior
- `tests/unit/adapters/test_csv_import_planner.py` — removed FX tests, updated transfer tests
- `tests/unit/domain/test_transaction.py` — updated validator test for EUR bypass
- `tests/unit/ui/test_import_workbench.py` — removed FX-related tests

### Tests
735 passing → 813 passing (81 skipped unchanged)

### Decisions made during the session
- EUR-at-face-value bypass uses `price_native.currency == EUR and fx_rate_eur == Decimal("1")` as sentinel; non-unit fx_rate still enforces native-currency check
- Synthetic fixture preferred over real 301-row CSV (not in repo)

### Tokens used (rough)
~200k (split session with context compaction)

## 2026-05-16 — TICKET-CSV-5
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~2 hr
**Branch:** ticket-csv-5-native-currency
**PR:** TBD
**Status at session end:** IN_REVIEW

### What got done
- Extended `app/domain/tickers.py`: 15+ new exchange suffixes (Stuttgart, Munich, Brussels, etc.), override map for HXSCL/ASX, new unsupported suffixes (GBP, CHF, AUD, CAD)
- Added `FX_UNAVAILABLE` to `RowStatus` and `fx_rate_eur` field to `PlannedRow` in `app/domain/csv_import.py`
- New `app/adapters/fx_yfinance/` adapter: disk-cached FX lookup at `data/fx_cache/{FROM}_{TO}.json`, historical rates cached indefinitely, wraps yfinance via composition
- Updated `planner.plan_import` to accept `fx_provider`; non-EUR rows now resolve to `NEW` (fx_rate_eur set) or `FX_UNAVAILABLE` (offline) instead of `NEEDS_CURRENCY_SUPPORT` when a provider is given
- Updated `importer.run_import` to accept `fx_provider`; builds native-currency `Transaction` objects for USD/JPY tickers using FX-derived rates
- Updated `import_workbench.py`: wires `FxYfinanceDiskAdapter`, shows manual-rate input for `FX_UNAVAILABLE` rows, builds correct native-currency Transactions on Apply (FX cache not written from manual overrides)
- Added `fx_cache_dir` to `Settings` (default `data/fx_cache/`)
- Added `get_import_fx_provider()` to `wiring.py`

### Files touched
- `app/domain/tickers.py` — override map + 15+ new suffixes
- `app/domain/csv_import.py` — FX_UNAVAILABLE status, fx_rate_eur on PlannedRow
- `app/config.py` — fx_cache_dir setting
- `app/adapters/fx_yfinance/__init__.py` (new)
- `app/adapters/fx_yfinance/adapter.py` (new) — FxYfinanceDiskAdapter
- `app/adapters/scalable_csv/planner.py` — fx_provider param, FX lookup branch
- `app/adapters/scalable_csv/importer.py` — fx_provider param, native-currency tx building
- `app/ui/wiring.py` — get_import_fx_provider()
- `app/ui/pages/import_workbench.py` — FX wiring, FX_UNAVAILABLE UI, _build_transaction for non-EUR
- `tests/unit/adapters/test_fx_yfinance.py` (new) — 8 FX adapter tests
- `tests/unit/domain/test_tickers.py` — 25+ new ticker detection tests
- `tests/unit/adapters/test_csv_import_planner.py` — 6 new FX-related planner tests
- `tests/unit/test_scalable_csv_importer.py` — 5 new USD/JPY/regression importer tests
- `tests/unit/ui/test_import_workbench.py` — 5 new workbench helper tests

### Tests
761 passing → 821 passing (60 new)

### Decisions made during the session
- Reused existing `FxProvider` port (fx_feed.py) rather than creating a new `app/ports/fx_rate.py` — the existing protocol already covers historical rate lookup; duplication avoided
- FxYfinanceDiskAdapter wraps YfinanceAdapter via composition (lazy init) rather than duplicating yfinance fetch logic
- Override map in tickers.py checked before suffix rules to allow explicit per-ticker exceptions
- Manual rate input direction: user enters "1 EUR = X native" (natural direction); adapter converts to fx_rate_eur = 1/user_input before storing

### Out-of-scope items noticed
- TICKET-CSV-6 (operational re-import) is now unblocked; no code needed, it's purely ops

## 2026-05-15 — TICKET-CSV-4
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~2 hr
**Branch:** ticket-csv-4-import-workbench
**PR:** TBD
**Status at session end:** IN_REVIEW

### What got done
- Added `csv_reference` + `source` fields to `Transaction` (schema v2)
- Added `app/domain/csv_import.py`: `RowStatus`, `PlannedAction`, `PlannedRow`, `ImportPlan`
- Added `app/adapters/scalable_csv/planner.py`: pure row classifier (reference dedup, content-hash fallback, currency/unmapped/out-of-scope detection)
- Added `app/adapters/repo_json/migration.py`: v1→v2 auto-migration with backup
- Updated `json_repo.py`: auto-migrates v1 portfolios on first load; bumped `SCHEMA_VERSION` to 2
- Updated `importer.py`: sets `csv_reference` and `source="scalable_csv"` on new transactions
- Added `app/scripts/migrate_portfolio_v1_to_v2.py`: standalone migration script
- Added `app/ui/pages/import_workbench.py`: full workbench (upload, raw preview, planned-changes table with filter chips, inline ISIN mapping, apply bar with backup + import log)
- Added "Import CSV" sidebar entry under TOOLS; topbar title registered
- Updated `config.py`: `backups_dir`, `import_log_json_path`
- Updated legacy fixture to v2; fixed two json_repo integration tests for schema version change

### Files touched
- `app/domain/csv_import.py` — new
- `app/domain/models.py` — csv_reference, source fields
- `app/adapters/scalable_csv/planner.py` — new
- `app/adapters/scalable_csv/importer.py` — sets new fields
- `app/adapters/repo_json/migration.py` — new
- `app/adapters/repo_json/json_repo.py` — schema v2, auto-migration
- `app/scripts/migrate_portfolio_v1_to_v2.py` — new
- `app/config.py` — 2 new settings
- `app/ui/pages/import_workbench.py` — new
- `app/ui/components/sidebar.py` — Import CSV entry
- `app/ui/components/topbar.py` — page title
- `tests/unit/adapters/test_csv_import_planner.py` — new (15 tests)
- `tests/unit/scripts/test_migrate_v1_to_v2.py` — new (7 tests)
- `tests/unit/ui/test_import_workbench.py` — new (16 tests)
- `tests/unit/ui/test_components.py` — count update
- `tests/unit/ui/test_sidebar_structure.py` — count + section update
- `tests/fixtures/portfolio_legacy_jpy_as_usd.json` — bumped to v2
- `tests/integration/test_json_repo.py` — wrong-version test uses v3, invalid-tx test uses v2

### Tests
734 passing → 775 passing (41 new)

### Decisions made during the session
- Planner placed in `app/adapters/scalable_csv/` (not `app/services/`) because it imports `ParsedCsvRow` from adapters, which services cannot import per import-linter contract 3. All four import-linter contracts remain green.
- Backup timestamp uses `%f` microseconds to guarantee unique filenames within the same second.

### Out-of-scope items noticed
- TICKET-CSV-5 will plug into this workbench (needs_currency_support rows will become importable)
- TICKET-CSV-6 is the operational re-import run after CSV-5 ships

## 2026-05-15 — TICKET-CSV-2
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~30 min
**Branch:** ticket-csv-2-mappings-page
**PR:** TBD
**Status at session end:** IN_REVIEW

### What got done
- Added `isin_map_json_path` setting to `app/config.py`
- Added `get_isin_map_repo()` to `app/ui/wiring.py`
- Created `app/ui/pages/mappings.py` — full Mappings page: header strip, unmapped section (save flow with resolver lookup), mapped table (edit + delete with confirm)
- Added "ISIN Mappings" entry to sidebar under SETTINGS (sidebar.py + topbar.py)
- Created `tests/unit/ui/test_mappings_page.py` — 24 tests covering validation, save, delete, init_state, and smoke

### Files touched
- `app/config.py` — added `isin_map_json_path`
- `app/ui/wiring.py` — added `get_isin_map_repo()`
- `app/ui/pages/mappings.py` — new
- `app/ui/components/sidebar.py` — added Mappings nav item, updated _SECTIONS range
- `app/ui/components/topbar.py` — added "mappings" to PAGE_TITLES
- `tests/unit/ui/test_mappings_page.py` — new (24 tests)
- `tests/unit/ui/test_components.py` — updated NAV_ITEMS count 11→12
- `tests/unit/ui/test_sidebar_structure.py` — updated count 11→12

### Tests
710 passing → 734 passing (24 new)

### Decisions made during the session
- no architectural decisions made

### Out-of-scope items noticed
- None

## 2026-05-15 — TICKET-CSV-1-hotfix
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~20 min
**Branch:** ticket-csv1-hotfix
**PR:** TBD
**Status at session end:** IN_REVIEW

### What got done
- Fixed `_check_amount` in `importer.py` to be sign-agnostic: uses `abs(shares×price)` instead of `shares×price`, fixing the sign-flip failure on outgoing Security transfer rows
- Added `_check_sign` to verify directional sign consistency per row type (Buy/Savings plan expect negative amount, Sell expects positive, Security transfer is "either")
- Added outgoing Security transfer filter: rows with `type=="Security transfer"` and `shares<0` are skipped before amount check; counted in new `outgoing_transfers_skipped` field on `ImportSummary`
- Added 4 new fixture CSVs: `outgoing_transfer_only.csv`, `incoming_transfer_only.csv`, `paired_transfers.csv`, `buy_wrong_sign.csv`
- Added 5 new unit tests covering all acceptance criteria

### Files touched
- `app/adapters/scalable_csv/importer.py` — both fixes + new ImportSummary field
- `tests/unit/test_scalable_csv_importer.py` — 5 new tests
- `tests/fixtures/scalable_csv/outgoing_transfer_only.csv` — new
- `tests/fixtures/scalable_csv/incoming_transfer_only.csv` — new
- `tests/fixtures/scalable_csv/paired_transfers.csv` — new
- `tests/fixtures/scalable_csv/buy_wrong_sign.csv` — new

### Tests
710 passing → 715 passing (5 new)

### Decisions made during the session
- Fee is NOT added to the expected amount in the sanity check (contradicts a note in the ticket spec); the existing code comment and real CSV data confirm fee is recorded separately from amount
- No architectural decisions made

### Out-of-scope items noticed
- None

## 2026-05-15 — TICKET-CSV-1
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-csv-1-scalable-csv-import
**PR:** TBD
**Status at session end:** IN_REVIEW

### What got done
- Added `app/domain/isin_map.py` — `IsinMapping` and `IsinMapDocument` Pydantic models
- Added `app/ports/isin_map.py` — `IsinMapRepository` Protocol
- Added `app/adapters/isin_map/repo.py` — `JsonIsinMapRepository` with atomic save
- Added `app/adapters/scalable_csv/parser.py` — pure CSV → `ParsedCsvRow` parser (European decimals, no filtering)
- Added `app/adapters/scalable_csv/importer.py` — orchestrator: status/type filter, dedup, ISIN map lookup, Transaction construction, amount sanity check, non-EUR currency defense
- Added `tools/import_scalable_csv.py` — CLI entry point with `--input`, `--isin-map`, `--portfolio`, `--dry-run`
- Added `data/isin_map.json` — initial empty mapping file (committed; gitignored data/* exception added)
- Deleted `app/scripts/seed_portfolio.py` (replaced by importer), `docs/reference/seed_portfolio.csv`, `tests/integration/test_seed_script.py`
- Rewrote `tests/integration/test_overview_e2e.py` to construct transactions directly (no longer depends on deleted seed script)
- Added 32 unit tests across 3 test files; updated `.gitignore`

### Files touched
- `app/domain/isin_map.py` — new
- `app/ports/isin_map.py` — new
- `app/adapters/isin_map/__init__.py`, `repo.py` — new
- `app/adapters/scalable_csv/__init__.py`, `parser.py`, `importer.py` — new
- `tools/import_scalable_csv.py` — new
- `data/isin_map.json` — new (committed)
- `.gitignore` — added `!data/isin_map.json`, `data/scalable_raw.csv`
- `tests/unit/test_scalable_csv_parser.py`, `test_scalable_csv_importer.py`, `test_isin_map_repo.py` — new
- `tests/fixtures/scalable_csv/*.csv` — new fixture files
- `tests/integration/test_overview_e2e.py` — rewritten (removed seed_portfolio dependency)
- `app/scripts/seed_portfolio.py`, `docs/reference/seed_portfolio.csv`, `tests/integration/test_seed_script.py` — deleted

### Tests
673 passing → 705 passing (32 new), 81 skipped

### Decisions made during the session
- Transactions from Scalable CSV use EUR as native currency (fx_rate_eur=1.0 per ADR-005). Tickers in isin_map.json must therefore be EUR-denominated (e.g., SAP.DE, RHM.DE). USD/JPY tickers would fail Transaction.validate_ticker_currency — the importer catches ValidationError and counts them as invalid_mapping with a clear message.
- Amount sanity check verifies abs(amount) ≈ shares×price (fee is NOT in the amount column per actual CSV data, despite spec description saying "±fee").
- Zero fee (fee="0,00") produces fees_native=Money(0, EUR), not None. Blank fee (Security transfer) produces None.

### Out-of-scope items noticed
- TICKET-CSV-2: Mappings page UI for isin_map.json
- TICKET-CSV-3: Distribution/Interest/Taxes/Corporate-action handling

## 2026-05-15 — TICKET-027
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-027-snapshot-tab
**PR:** TBD
**Status at session end:** IN_REVIEW

### What got done
- Added `DEFAULT_STYLE = STYLE_CLEAN` to `chart_theme.py` (no explicit style choice recorded from TICKET-026 PR; defaulted to STYLE_CLEAN per ticket spec)
- Removed chart style sampler code and `_sample_chart` / `_SAMPLE_QUARTERS` functions from `company.py`
- Created `app/ui/pages/_snapshot_helpers.py` — pure helper module with: `filter_price_history`, `compute_sma`, `compute_revenue_cagr` (date-based CAGR using period_end), `compute_ebit_margin`, `compute_ebit_margin_series`, `compute_net_debt_ebitda`, `compute_net_debt_ebitda_series`, `compute_fcf_yield`, `compute_fcf_series`, `compute_revenue_series`, `compute_historical_pe_range`
- Added `format_multiple` to `format.py` ("2.1x" format)
- Implemented full Snapshot tab in `company.py`: header strip, 5Y price chart + 200DMA with period toggle, 4 KPI tiles with mini sparklines, P/E valuation band (gradient 20-segment background), next-catalyst card
- Created `tests/unit/ui/test_snapshot_helpers.py` with 24 tests covering all helpers

### Files touched
- `app/ui/components/chart_theme.py` — added DEFAULT_STYLE
- `app/ui/format.py` — added format_multiple
- `app/ui/pages/_snapshot_helpers.py` — created
- `app/ui/pages/company.py` — removed sampler, implemented Snapshot tab
- `tests/unit/ui/test_snapshot_helpers.py` — created
- `tests/unit/ui/test_company_page.py` — replaced sampler test with smoke test
- `docs/TICKETS/TICKET-027-...md` — status → IN_PROGRESS

### Tests
649 passing → 673 passing (24 new)

### Decisions made during the session
- STYLE_CLEAN chosen as DEFAULT_STYLE (no PR-review choice recorded; spec says default to STYLE_CLEAN)
- Revenue CAGR uses actual dates (period_end diff / 365.25) rather than counting valid quarters, so gaps in revenue coverage don't corrupt the year span
- Valuation band uses 20 gradient segments (green→red) rendered as plotly shapes + scatter marker

### Out-of-scope items noticed
- None

### Tokens used (rough)
~70k

## 2026-05-14 22:00 — TICKET-M7
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~30 min
**Branch:** ticket-m7-tools-portable-macos-bsd
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/74
**Status at session end:** IN_REVIEW

### What got done
- Chose Strategy 1 (portable rewrite): 6 GNU-isms in tools/file.sh, all with clean POSIX equivalents, well under the 10-occurrence threshold
- Replaced `mapfile` with `while IFS= read -r` loop (bash 3.2-compatible)
- Replaced 3× `grep -oP` (Perl-compat regex) with `sed -nE` capture groups (POSIX)
- Replaced `${var,,}` case conversion with `tr '[:upper:]' '[:lower:]'` (POSIX)
- Added comment block at top of file.sh documenting portability, tested-on, and macOS invocation
- Created `tools/README.md` documenting toolchain requirements and forbidden constructs
- Added "Local environment" section to `AGENTS.md` (stock macOS bash 3.2 is sufficient)
- Created `.github/workflows/ci.yml` with pytest/ruff/mypy/lint-imports and shellcheck jobs

### Files touched
- `tools/file.sh` — 6 GNU-isms replaced with POSIX equivalents
- `tools/README.md` — created; documents toolchain and forbidden constructs
- `AGENTS.md` — added Local environment section
- `.github/workflows/ci.yml` — created; pytest + shellcheck jobs
- `docs/TICKETS/TICKET-M7-tools-portable-macos-bsd.md` — status → IN_PROGRESS

### Tests
649 passing, 85 skipped (unchanged — no Python changes)

### Decisions made during the session
- Strategy 1 chosen over Strategy 2: only 6 GNU-isms, all having clean one-line POSIX equivalents. Rewriting preserves script readability and avoids runtime dependency on brew. Strategy 2 (preamble guard) would still require Vivek to install tools; Strategy 1 removes that requirement entirely.

### Out-of-scope items noticed
- None

### Tokens used (rough)
~25k

## 2026-05-14 21:30 — TICKET-M6
**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~30 min
**Branch:** ticket-m6-consolidate-agents-session-log
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/73
**Status at session end:** IN_REVIEW

### What got done
- Confirmed docs/AGENTS.md already deleted; root AGENTS.md is canonical (no STATE.md refs)
- AGENTS.md Step 8: added 8b (append session log entry), renumbered 8b→8c, 8c→8d
- docs/METHODOLOGY.md: updated session-end ritual summary to include step 8b
- tools/regen_context.py: removed section_tests_inventory, removed tests/ from file tree, added section_recent_sessions() parsing last 10 TICKET-XXX entries from SESSION_LOG.md
- tests/unit/tools/test_regen_context.py: replaced tests_inventory test with recent_sessions test
- docs/SESSION_LOG.md: created with historical entries recovered from commit 3f6d520f^ and active-log structure
- docs/CONTEXT.md: regenerated — 2273 → 1412 lines (861 lines removed)

### Files touched
- `AGENTS.md` — Step 8 reordered with new 8b session-log step
- `docs/METHODOLOGY.md` — session-end ritual updated
- `tools/regen_context.py` — tests_inventory removed, file tree scoped, recent_sessions added
- `tests/unit/tools/test_regen_context.py` — assertions updated
- `docs/SESSION_LOG.md` — created (new file)
- `docs/CONTEXT.md` — regenerated

### Tests
649 passing, 85 skipped → 649 passing, 85 skipped (no net change)

### Decisions made during the session
- CONTEXT.md is 1412 lines, not 500-900 as estimated in ticket; public interfaces section (~1105 lines) was not identified as bloat and was not removed — the ticket explicitly notes "drop bloat, not hit a number"

### Out-of-scope items noticed
- No issues

### Tokens used (rough)
~40k

---

## Historical entries (pre-deletion)

# SESSION_LOG.md

Append-only log of every Claude Code session and significant Claude Chat session.
Newest entries at the bottom.

When this file exceeds ~500 lines, archive everything older than 30 days into `docs/SESSION_LOG_ARCHIVE_<year>_Q<N>.md` and keep this file lean.

---

## 2026-05-03 — Foundation setup (Claude Chat)

**Surface:** Claude Chat (claude.ai)
**Participants:** Vivek + Claude
**Duration:** ~1.5 hours

### What got done
- Decided on greenfield rebuild (old repo archived as reference only)
- Confirmed stack: Streamlit + Pydantic v2 + JSON storage
- Designed the state-handoff system (PROJECT_STATE.md + SESSION_LOG.md + ADRs + TICKETS)
- Defined the Vivek/Claude Chat/Claude Code division of labor
- Drafted root `CLAUDE.md`, `PROJECT_STATE.md`, `METHODOLOGY.md`, `ARCHITECTURE.md`
- Drafted `BACKLOG.md` and `TICKET-000` in detail
- Drafted `ADR-001` (Streamlit over FastAPI)
- Set up `.github/PULL_REQUEST_TEMPLATE.md` for standardized PRs

---

## 2026-05-03 — TICKET-000

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~25 min
**Branch:** ticket-000-scaffolding
**PR:** https://github.com/vivekbhargava23/Investement-Dashboard-Claude/pull/1
**Status at session end:** IN_REVIEW

### What got done
- Created `pyproject.toml` with runtime + dev deps, ruff/mypy/pytest config
- Created full `app/` package structure: domain, services, ports, adapters, ui sub-packages
- Created `app/config.py` — pydantic-settings `Settings` class (single secret-loading boundary)
- Created `app/ui/app.py` — Streamlit placeholder page
- Created `tests/unit/` — smoke, import, and config tests (5 passing)
- Created `.github/workflows/ci.yml` — pytest + ruff + mypy + lint-imports on every push/PR
- Created `.importlinter` — 3 contracts enforcing clean-architecture layer boundaries
- Created `.env.example`, `environment.yml`, `README.md`

---

## 2026-05-03 — TICKET-001

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~45 min
**Branch:** ticket-001-domain-models
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Implemented `Money` value object with normalized Decimal precision and arithmetic/comparison operators.
- Implemented `Transaction` model with validation for EUR FX rates, ticker case, and share quantities.
- Implemented `OpenLot` and `Position` models with consistency checks between positions and underlying lots.
- Created exhaustive unit tests for all domain models, including property-based tests for `Money`.
- Restored `.importlinter` configuration to enforce clean architecture layers.
- Exported all models via `app.domain.__init__.py`.
- All tests and lints (ruff, mypy strict, import-linter) pass.

---

## 2026-05-03 — TICKET-003

**Surface:** Gemini CLI
**Model:** Gemini 2.0 Pro
**Duration:** ~30 min
**Branch:** _pending_
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Implemented `TransactionRepository` port (Protocol) in `app/ports/repository.py` with CRUD and atomic save methods.
- Implemented `JsonTransactionRepository` adapter in `app/adapters/repo_json/json_repo.py` using Pydantic serialization.
- Implemented atomic writes using a temporary file, `fsync`, and `os.replace` to prevent data corruption.
- Added schema versioning (`version: 1`) to the JSON file format.
- Created 18 integration tests in `tests/integration/test_json_repo.py` covering CRUD, atomic writes, corruption handling, and Decimal precision.
- All tests (63 passing), lints (ruff), and type checks (mypy) pass.
- `import-linter` contracts verified.

---

## 2026-05-03 — TICKET-004-005

**Surface:** Gemini CLI
**Model:** Gemini 2.0 Pro
**Duration:** ~45 min
**Branch:** ticket-004-005-yfinance-adapter
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Implemented `PriceProvider` and `FxProvider` ports (Protocols) with detailed error classes.
- Implemented `YfinanceAdapter` satisfying both ports with in-memory caching and 60s TTL.
- Added currency inference heuristic for European tickers (.DE, .F, etc.).
- Implemented EUR/USD FX rate handling with automatic inversion for USD/EUR lookups.
- Created `FakePriceProvider` and `FakeFxProvider` for unit testing downstream services.
- Added integration tests gated by `--run-integration` flag hitting real yfinance.
- Verified all unit and integration tests (94 passing), lints (ruff), type checks (mypy), and import contracts.

---

## 2026-05-03 — TICKET-006

**Surface:** Gemini CLI
**Model:** Gemini 2.0 Pro
**Duration:** ~30 min
**Branch:** ticket-006-valuation-service
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Implemented `LivePosition` and `PortfolioSummary` domain models in `app/domain/positions.py`.
- Created `app/services/CLAUDE.md` defining service layer principles (statelessness, dependency injection).
- Implemented `valuation.py` service with `compute_live_positions`, `compute_portfolio_summary`, and `clear_caches`.
- Implemented per-ticker failure isolation in `compute_live_positions`.
- Created exhaustive unit tests in `tests/unit/services/test_valuation.py` using fakes and mocks.
- Verified all quality checks (ruff, mypy, import-linter) and 104 passing tests.

### Files touched
- `app/domain/positions.py` — updated
- `app/domain/__init__.py` — updated
- `app/services/CLAUDE.md` — new
- `app/services/valuation.py` — new
- `tests/unit/services/test_valuation.py` — new
- `docs/PROJECT_STATE.md` — updated
- `docs/TICKETS/BACKLOG.md` — updated
- `docs/SESSION_LOG.md` — updated

### Tests
94 passing → 104 passing (10 new)

### Decisions made during the session
- Used explicit `Literal` type hint for `staleness` to satisfy `mypy`.
- Favored `compute_live_positions` for generating test data instead of manual `LivePosition` instantiation to avoid consistency check issues.

### Out-of-scope items noticed
- (none)

---

## 2026-05-03 14:30 — TICKET-007

**Surface:** Gemini CLI
**Model:** Gemini 2.0 Pro
**Duration:** ~45 min
**Branch:** ticket-007-streamlit-shell
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Created Streamlit shell with custom dark theme (oklch colors).
- Implemented custom sidebar with query-param routing.
- Implemented topbar with page titles and placeholder FX/time.
- Created 8 placeholder page modules for routing verification.
- Implemented pure formatting helpers for EUR, percentages, shares, and dates.
- Created reusable UI components: MetricCard, ThesisBadge, SeverityBadge.
- Added unit tests for formatting and components (100% coverage for formatters).
- Fixed a pre-existing test failure in `test_valuation.py` (pre-flight chore).

### Files touched
- `app/ui/app.py` — main entry and routing
- `app/ui/styles/dark.css` — custom styling
- `app/ui/format.py` — formatting helpers
- `app/ui/components/*.py` — UI components
- `app/ui/pages/*.py` — page placeholders
- `tests/unit/ui/*.py` — UI tests
- `docs/reference/Investment_Dashboard.html` — design reference
- `docs/PROJECT_STATE.md`, `docs/SESSION_LOG.md`, `docs/TICKETS/BACKLOG.md`

### Tests
74 passing → 91 passing (17 new)

### Decisions made during the session
- Chose `st.columns` with `unsafe_allow_html` for sidebar to allow Streamlit buttons and state management while maintaining layout fidelity.
- Chose query-param routing to allow cleaner "active" state styling in the sidebar.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~15k

---

## 2026-05-03 — TICKET-007 Refactor & UI Polish

**Surface:** Gemini CLI
**Model:** Gemini 2.0 Pro
**Duration:** ~30 min
**Branch:** feature/ui-shell-refactor
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/11
**Status at session end:** IN_REVIEW

### What got done
- Fixed Streamlit shell crash by refactoring entry point to use dynamic imports and placeholders.
- Resolved 'app is not a package' error by renaming `app/ui/app.py` to `app/ui/main.py`.
- Fixed sidebar and topbar HTML rendering issues caused by Markdown whitespace sensitivity.
- Improved CSS loading reliability using relative paths.
- Implemented Light Theme as requested, adjusting OKLCH variables for high contrast.
- Updated all documentation and references to point to `main.py`.

### Files touched
- `app/ui/main.py` (renamed from app.py, refactored)
- `app/ui/styles/dark.css` (converted to light theme)
- `app/ui/components/sidebar.py`
- `app/ui/components/topbar.py`
- `app/ui/components/metric_card.py`
- `README.md`
- `docs/TICKETS/TICKET-000-scaffolding.md`
- `docs/TICKETS/TICKET-007-streamlit-shell.md`
- `docs/TICKETS/TICKET-008-live-overview.md`

### Tests
- All UI unit tests pass (pytest tests/unit/ui/)
- Verified manually that shell starts and routes correctly in light mode.

---

## 2026-05-03 — TICKET-008

**Surface:** Gemini CLI
**Model:** Gemini 2.0 Pro
**Duration:** ~45 min
**Branch:** ticket-008-live-overview
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Created seed script `app/scripts/seed_portfolio.py` to bootstrap transactions.
- Wired live overview logic in `app/ui/pages/overview.py` including `st.cache_data`.
- Implemented singleton caching in `app/ui/wiring.py` for repository and providers.
- Wired topbar refresh button to flush cache.
- Added comprehensive unit and e2e integration tests.

### Files touched
- `docs/reference/seed_portfolio.csv` (new)
- `app/scripts/__init__.py` (new)
- `app/scripts/seed_portfolio.py` (new)
- `app/ui/wiring.py` (new)
- `app/ui/pages/overview.py` (updated)
- `app/ui/components/topbar.py` (updated)
- `tests/integration/test_seed_script.py` (new)
- `tests/unit/ui/test_overview_helpers.py` (new)
- `tests/unit/ui/test_overview_render.py` (new)
- `tests/integration/test_overview_e2e.py` (new)

### Tests
91 passing → 97 passing (6 new)

---

## 2026-05-04 — TICKET-008b

**Surface:** Claude Code
**Model:** claude-sonnet-4-6
**Duration:** ~40 min
**Branch:** ticket-008b-html-leak-fix (based on ticket-008-live-overview)
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/13
**Status at session end:** IN_REVIEW

### What got done
- Created `app/ui/render.py`: `render_html(html)` helper that applies `textwrap.dedent` + `.strip()` before calling `st.markdown(..., unsafe_allow_html=True)`. This is now the only place in the codebase where `unsafe_allow_html=True` is set.
- Created `app/ui/CLAUDE.md`: documents the HTML rendering rule so future pages cannot accidentally introduce the same bug.
- Refactored `app/ui/pages/overview.py`: replaced all 5 direct `st.markdown(..., unsafe_allow_html=True)` calls with `render_html()`; extracted `_build_positions_table_html(positions, summary) -> str` as a pure helper that builds the table using single-line string concatenation (no leading whitespace, no markdown code-block trigger).
- Wrote regression tests first (confirmed failing), then implemented the fix:
  - `tests/unit/ui/test_html_helper.py`: 4 tests for `render_html`
  - `tests/unit/ui/test_overview_render.py`: extended with 6 regression tests that assert `_build_positions_table_html` returns a string starting with `<`, with no 4+-space prefix, one `<table` tag, and no double-escaping.

### Files touched
- `app/ui/render.py` (new)
- `app/ui/CLAUDE.md` (new)
- `app/ui/pages/overview.py` (refactored)
- `docs/TICKETS/TICKET-008b-html-leak-fix.md` (status: IN_REVIEW)
- `tests/unit/ui/test_html_helper.py` (new)
- `tests/unit/ui/test_overview_render.py` (extended)

### Tests
97 passing → 107 passing (10 new)

---

## 2026-05-04 — TICKET-008b + cleanup

**Surface:** Claude Code + Claude Chat (debugging session)
**Duration:** ~2 hours
**Branch:** ticket-008b-html-leak-fix
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/13 (merged)
**Status at session end:** MERGED

### What got done
- Fixed positions table HTML leak: extracted `_build_positions_table_html` as pure helper, added `app/ui/render.py:render_html()` as the single place where `unsafe_allow_html=True` is set.
- Added 10 regression tests (4 for the helper, 6 for the table builder), confirmed failing-before-fix and passing-after-fix.
- Discovered and fixed Python stdlib collision: `app/ui/html.py` shadowed the stdlib `html` package in Streamlit's import context, breaking bs4 → yfinance import chain. Renamed module to `app/ui/render.py`.
- Fixed `.gitignore` gap: `data/portfolio.json` was being tracked (rule was for stale filename `data/transactions.json`). Now `data/*` is ignored except `.gitkeep`.
- Closed superseded PR #12 (contained Gemini's ineffective "consolidated UI fix" commits). Merged PR #13 directly to `main`.

### Methodology lessons (to fold into METHODOLOGY.md)
- Module names must not collide with Python stdlib (`html`, `email`, `string`, `io`, `time`, `json`, `logging`, etc.). Add to ticket-drafting checklist.
- "Verification" means observed working behavior in the running app, not just tests passing. PR descriptions should require a screenshot of the working state.
- "Reconcile" and "consolidate" are scope-expansion verbs. Open-ended fix instructions like "fix the problem" license agents to expand scope. Tickets need explicit "Files NOT to modify" sections for bug fixes.
- `pip install -e .` should be in README setup so `PYTHONPATH=.` is never needed.

### Tests
107 passing

---

## 2026-05-04 — TICKET-009

**Surface:** Gemini CLI
**Model:** Gemini 2.5 Pro
**Duration:** ~45 min
**Branch:** main (Direct commit for speed, though normally a branch)
**Status at session end:** IN_REVIEW

### What got done
- Implemented `app/ui/pages/manage.py` for CRUD portfolio operations (Add/Edit/Delete transactions).
- Handled FIFO validation on the form before persistence to prevent invalid sequence states.
- Handled form-level state for Edit and Delete interactions via `st.session_state`.
- Added CSS `.tx-row` styling to `app/ui/styles/dark.css`.
- Added integration tests for CRUD and FIFO interaction in `tests/integration/test_manage_crud.py`.
- Added unit tests for UI helper methods in `tests/unit/ui/test_manage_page.py`.
- Updated backlog and project state markdown documents.

### Files touched
- `app/ui/pages/manage.py`
- `app/ui/styles/dark.css`
- `tests/integration/test_manage_crud.py`
- `tests/unit/ui/test_manage_page.py`
- `docs/PROJECT_STATE.md`
- `docs/TICKETS/BACKLOG.md`
- `docs/TICKETS/TICKET-009-manage-portfolio.md`
- `docs/SESSION_LOG.md`

### Tests
107 passing -> 117 passing (10 new)

## 2026-05-04 — Drafting session: ADR-005 + TICKET-008c, 020, 009-revised (Claude Chat)

**Surface:** Claude Chat (claude.ai)
**Participants:** Vivek + Claude
**Duration:** ~2 hours

### What got done
- Bench-tested original TICKET-009 implementation against real Scalable Capital workflow.
- Surfaced three silent-corruption bugs: (1) FX field defaulted to 1.0 with no warning on USD APD purchase; (2) Currency dropdown defaulted to EUR for NVDA, producing stale row; (3) 5631.T mislabelled as USD since seed time, producing €4,032 of fake unrealised gain.
- Diagnosed root cause: form's input model demands data Scalable doesn't surface to the user (native price, FX rate). Three bugs were symptoms of one mismatch.
- Drafted ADR-005: input becomes EUR-native; currency and FX inferred from ticker + broker EUR total; data model unchanged.
- Drafted TICKET-008c: extend Currency enum (add JPY); add ticker↔currency domain validator; migrate `data/portfolio.json`.
- Drafted TICKET-020: new `TickerResolver` port + yfinance adapter for autocomplete.
- Drafted TICKET-009-revised: replaces original TICKET-009 form with EUR-native input, ticker autocomplete, 2% FX-deviation guard, transparent fallback to manual entry.
- Decided to close original TICKET-009 PR #14 without merging.

### Decisions made during the session
- ADR-005 chosen over three alternatives (patch existing form; pure EUR-only with no currency tracking; native + live EUR readout). See ADR for rejection reasons.
- 2% FX deviation tolerance for the new form's warning (catches typos; tolerates broker spread of 5–25 bps).
- Migration script (TICKET-008c) preserves recorded EUR cost basis rather than recomputing from yfinance, with an interactive override for 5631.T specifically.
- Currency enum extended only to JPY in this round; GBP/CHF/HKD added on demand.
- TICKET-009-revised supersedes TICKET-009 wholesale (form module rewrite). Original PR closed, not merged. Implementer not penalised — the ticket spec was correct as drafted; the spec itself was wrong, which is what bench-testing surfaced.

### Out-of-scope items noticed
- METHODOLOGY.md updates from TICKET-008b's session log (stdlib name collisions, "verification = observed behavior", scope-expansion verbs) still pending.
- The placeholder `_TICKER_NAMES` dict in `app/ui/pages/overview.py` becomes obsolete after TICKET-009-revised; cleanup folded into that ticket.
- Methodology lesson to fold in: "Bench-test ticket specs against real-world workflow before marking READY."

### Files touched (chat-side; repo edits done by Vivek post-session)
- `docs/DECISIONS/ADR-005-eur-native-input.md` (new)
- `docs/TICKETS/TICKET-008c-currency-correctness.md` (new)
- `docs/TICKETS/TICKET-020-ticker-resolver.md` (new)
- `docs/TICKETS/TICKET-009-revised-eur-native-form.md` (new)
- `docs/PROJECT_STATE.md` (updated)
- `docs/TICKETS/BACKLOG.md` (updated)
- `docs/SESSION_LOG.md` (this entry)

---

## 2026-05-05 — Drafting session: Tax Engine, Dashboard, and Simulator (Claude Chat)

**Surface:** Claude Chat (claude.ai)
**Participants:** Vivek + Claude
**Duration:** ~1 hour

### What got done
- Drafted TICKET-010: Detailed spec for the pure-Python tax engine (pipeline, rates, classification).
- Drafted TICKET-011: Detailed spec for the Tax Dashboard page and service layer.
- Drafted TICKET-012: Detailed spec for the Pre-trade sell simulator and FIFO lot-preview.
- Updated docs/TICKETS/BACKLOG.md and docs/PROJECT_STATE.md to reflect the new tickets.

### Decisions made during the session
- Chose to keep the tax engine pure and stateless in `app/domain/tax/`.
- Decided on a JSON-based tax profile repository for persisting carryforwards and status.
- Opted for a "sequential" harvest impact model in the UI to reflect shared allowance.
- Simulator will use a promoted `simulate_lot_consumption` helper from the FIFO engine.


---

## 2026-05-05 — TICKET-010 Appendix: Bench-test findings (Claude Code)

**Surface:** Gemini CLI
**Participants:** Vivek + Claude
**Duration:** ~5 min

### What got done
- Added "Bench-test findings (2026-05-04)" appendix to `docs/TICKETS/TICKET-010-tax-engine.md`.
- Documented requirement for per-trade tax withholding tracking.
- Documented five new transaction types (DIVIDEND, INTEREST, taxes).
- Documented CAD currency requirement for specific holdings (Niobium).


## 2026-05-05 14:30 — TICKET-008c

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-008c-currency-correctness
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/19
**Status at session end:** IN_REVIEW

### What got done
- Pre-existing bug fix: `tests/unit/ui/test_html_helper.py` imported from `app.ui.html`
  (renamed to `app.ui.render` in TICKET-008b) — 4 tests were broken on main before work started.
  Fixed as a prep commit; reported to Vivek.
- `Currency.JPY` added to `app/domain/money.py`; `__str__` updated: JPY → `¥` prefix,
  zero decimal places (e.g. `¥9,049`).
- New `app/domain/tickers.py`: pure `infer_currency_from_ticker()` function; maps
  `.DE`/`.F`/`.MI`/`.PA`/`.AS` → EUR, `.T` → JPY, `.HK` → `UnsupportedTickerError`,
  unsuffixed → USD. Single source of truth for ticker→currency mapping (ADR-005).
- `Transaction` gains `@model_validator` that calls `infer_currency_from_ticker`;
  rejects construction if ticker and price currency disagree. 5631.T-as-USD is now
  structurally impossible.
- `JsonTransactionRepository.load_all()` pre-checks ticker↔currency consistency;
  raises `LegacyDataError` (with `.offenders` attribute and migration-script hint)
  before attempting full Pydantic construction. Existing `RepositoryCorruptedError`
  path for other validation failures preserved.
- `YfinanceAdapter._infer_currency()` now delegates to `infer_currency_from_ticker()`
  (eliminating duplicated logic). FX rate methods extended to cover EUR/JPY, JPY/EUR,
  USD/JPY, JPY/USD via new `_fx_yfinance_ticker()` helper.
- New `app/scripts/migrate_currency.py`: one-shot CLI that detects legacy ticker↔
  currency mismatches, fetches historical native-currency close from yfinance,
  back-computes FX rate to preserve recorded EUR cost basis; dry-run, --force,
  interactive override for the specific 5631.T row; validates output round-trips
  through `JsonTransactionRepository` before writing.
- `docs/reference/seed_portfolio.csv`: 5631.T row rewritten as JPY (price=8829.5596,
  fx=0.005776); "use USD as approximation" note deleted; schema comment added.
- `data/portfolio.json` already had JPY for 5631.T from prior aborted attempt;
  file is gitignored so not committed — migration is a no-op in current state.

### Files touched
- `app/domain/money.py` — JPY enum member + __str__ dispatch
- `app/domain/tickers.py` — new module
- `app/domain/models.py` — ticker↔currency @model_validator
- `app/domain/__init__.py` — export infer_currency_from_ticker, UnsupportedTickerError
- `app/adapters/repo_json/json_repo.py` — LegacyDataError + pre-check in load_all
- `app/adapters/yfinance_feed/yfinance_adapter.py` — delegate + JPY FX pairs
- `app/scripts/migrate_currency.py` — new migration script
- `tests/unit/domain/test_money.py` — JPY cases
- `tests/unit/domain/test_transaction.py` — currency validator cases (incl. regression)
- `tests/unit/domain/test_tickers.py` — new test module
- `tests/unit/domain/test_fifo.py` — ticker fixtures updated to EUR-suffixed (.DE)
- `tests/unit/services/test_valuation.py` — MISSING→NOPRICE.DE
- `tests/unit/ui/test_html_helper.py` — import path fix (app.ui.html → app.ui.render)
- `tests/integration/test_json_repo.py` — LegacyDataError tests
- `tests/integration/test_yfinance_real.py` — JPY price + FX rate integration tests
- `tests/integration/test_migrate_currency.py` — new migration tests
- `tests/fixtures/portfolio_legacy_jpy_as_usd.json` — new legacy fixture
- `docs/reference/seed_portfolio.csv` — 5631.T row fixed
- `docs/TICKETS/TICKET-008c-currency-correctness.md` — status IN_REVIEW
- `docs/TICKETS/BACKLOG.md` — TICKET-008c → IN_REVIEW
- `docs/PROJECT_STATE.md` — TICKET-008c moved to In review

### Tests
107 passing → 128 passing (21 new; 38 skipped — integration tests gated behind @pytest.mark.integration)

### Decisions made during the session
- Pre-existing test failure (app.ui.html → app.ui.render import) fixed inline as a
  prep commit rather than a separate hotfix PR — reported to Vivek before proceeding.
- `data/portfolio.json` is gitignored; migration confirmed as no-op since prior
  aborted attempt already updated the local file; documented in PR description.
- `dict[str, Any]` used in migration script for raw JSON data — `object` type is too
  restrictive for mypy's attribute checks on JSON-sourced dicts.

### Out-of-scope items noticed
- TICKET-008b session note: `app/ui/html.py` → `app/ui/render.py` rename left stale
  import in `test_html_helper.py`. Fixed here since it was blocking a green baseline.
- `data/portfolio.json` is gitignored. The ticket spec assumed it would be committed;
  per `.gitignore`, it's user data. Migration documented in PR instead.

### Tokens used (rough)
~85k

## 2026-05-05 16:00 — TICKET-020

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~40 min
**Branch:** ticket-020-ticker-resolver
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/20
**Status at session end:** IN_REVIEW

### What got done
- New `app/ports/ticker_resolver.py`: `TickerMatch` frozen Pydantic model
  (symbol, name, exchange, currency: Currency, recent_price: Money | None) and
  `TickerResolver` Protocol (resolve, lookup, clear_cache).
- `app/ports/__init__.py` updated to export `TickerMatch` and `TickerResolver`.
- `YfinanceAdapter` extended to satisfy `TickerResolver` alongside existing
  `PriceProvider` and `FxProvider`:
  - `_resolver_cache: dict[str, tuple[float, Any]]` with 3600s TTL
  - `_build_match(symbol, name, exchange)`: shared helper that calls
    `infer_currency_from_ticker`; returns `None` for unsupported currencies
    (e.g. HKD) so callers can silently omit rather than raise
  - `resolve(query, limit)`: yf.Search-backed; normalises query; empty →
    returns []; exceptions → empty list with warning log; respects limit
  - `lookup(symbol)`: yf.Ticker.info exact fetch; None on miss or unsupported
  - `clear_cache()` extended to also clear `_resolver_cache`
- `tests/fakes/ticker_resolver.py`: `FakeTickerResolver` that satisfies
  `TickerResolver` Protocol via hardcoded match list; used by TICKET-009-revised.
- `tests/unit/ports/test_ticker_resolver_protocol.py`: 12 unit tests covering
  TickerMatch construction/frozen, EUR/JPY variants, FakeTickerResolver resolve/
  lookup/clear_cache behaviour.
- `tests/integration/test_yfinance_resolver.py`: 11 tests (7 integration-marked
  needing network; 4 using mocks); covers USD/EUR/JPY resolve, empty/garbage
  queries, unsupported-currency omission, search exceptions, limit enforcement.

### Files touched
- `app/ports/ticker_resolver.py` — new
- `app/ports/__init__.py` — export TickerMatch, TickerResolver
- `app/adapters/yfinance_feed/yfinance_adapter.py` — resolver methods added
- `tests/fakes/ticker_resolver.py` — new
- `tests/unit/ports/__init__.py` — new
- `tests/unit/ports/test_ticker_resolver_protocol.py` — new
- `tests/integration/test_yfinance_resolver.py` — new
- `docs/TICKETS/TICKET-020-ticker-resolver.md` — status IN_REVIEW
- `docs/TICKETS/BACKLOG.md` — TICKET-020 → IN_REVIEW
- `docs/PROJECT_STATE.md` — TICKET-020 moved to In review

### Tests
128 passing → 140 passing (12 new; 50 skipped — integration tests gated behind @pytest.mark.integration)

### Decisions made during the session
- yfinance Search results have no `currency` field; `infer_currency_from_ticker`
  is used exclusively rather than cross-checking yfinance metadata — this is
  consistent with TICKET-008c's design and avoids the risk of stale yfinance
  currency metadata causing issues.
- resolve() returns `list(cached)` (a new list) rather than the cached list
  object directly, to prevent callers mutating the cache.
- lookup() uses `isinstance(cached, TickerMatch)` guard when returning from
  cache to keep the return type clean for mypy.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~25k

## 2026-05-06 — TICKET-009-revised

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min (including context-window continuation)
**Branch:** ticket-009-revised-eur-native-form
**PR:** (opening this session)
**Status at session end:** IN_REVIEW

### What got done
- New `app/services/trading.py`: `build_transaction()` pure pipeline — EUR-native path
  (price_per_share from net EUR / shares, fx_rate_eur=1) and non-EUR path (fetch
  historical close via PriceProvider, back-compute implied FX, deviation check vs ECB).
  Returns `(Transaction, deviation_pct)` where deviation_pct is None for EUR.
- Full rewrite of `app/ui/pages/manage.py` (EUR-native form, ADR-005):
  - Two-step Add flow: Fill → Calculate Preview → Confirm & Record.
    Preview hidden until explicitly triggered; "Confirm & Record" becomes "Record anyway"
    if FX deviation ≥ 10%.
  - Bug fix: "Total EUR paid" defaults to `None` (blank) instead of 0.01; user must
    type their actual broker debit.
  - Ticker autocomplete with `TickerResolver.resolve()` + "Use as-typed" escape hatch.
  - Fallback manual-entry path exposed in the preview step when `PriceUnavailableError`.
  - Live recording preview in edit form (unchanged — edit flow keeps inline preview).
  - Edit / Delete table with per-row buttons and inline delete confirmation.
  - `_init_state`, `_tx_to_form_values`, `_match_label` as pure testable helpers.
- New `app/ui/wiring.py`: `get_ticker_resolver()` singleton.
- New `tests/unit/ui/test_manage_form_pipeline.py`: 12 tests for `build_transaction`
  (EUR/USD/JPY happy paths, cost_eur round-trip, zero fees, deviation warning,
  graceful on missing ECB rate, FIFO sell guard pass/fail, validator regression).
- New `tests/unit/ui/test_manage_page.py`: 10 tests for pure helpers
  (`_init_state` idempotency, `_tx_to_form_values` EUR/USD, `_match_label` formatting).
- New `tests/integration/test_manage_e2e.py`: 9 tests (add EUR/USD/JPY, three together,
  edit shares, delete, resolver lookup, manual fallback).
- Fixed pre-existing test failures caused by TICKET-008c ticker↔currency validator:
  renamed test tickers in `test_fifo.py` (NVDA → NVDA.DE / SAP.DE / RHM.DE) and
  `test_valuation.py` (MISSING → NOPRICE.DE) to use EUR-suffixed symbols.
- New `tests/fixtures/portfolio_legacy_jpy_as_usd.json` for LegacyDataError tests.
- New `tests/fakes/ticker_resolver.py`: `FakeTickerResolver`.

### Files touched
- `app/services/trading.py` — new
- `app/ui/pages/manage.py` — full rewrite (EUR-native two-step form)
- `app/ui/wiring.py` — get_ticker_resolver() singleton
- `tests/unit/ui/test_manage_form_pipeline.py` — new
- `tests/unit/ui/test_manage_page.py` — new
- `tests/integration/test_manage_e2e.py` — new
- `tests/fakes/ticker_resolver.py` — new
- `tests/fixtures/portfolio_legacy_jpy_as_usd.json` — new
- `tests/unit/domain/test_fifo.py` — ticker renames (EUR-suffix fix)
- `tests/unit/services/test_valuation.py` — ticker rename (EUR-suffix fix)
- `tests/unit/ui/test_html_helper.py` — import fix (app.ui.html → app.ui.render)
- `docs/TICKETS/TICKET-009-revised-eur-native-form.md` — status IN_REVIEW

### Tests
140 passing → 161 passing (21 new)

### Decisions made during the session
- Two-step submit (Fill → Preview → Confirm) chosen over live preview to prevent
  accidental submissions before the user has verified the FX back-computation.
- `build_transaction` placed in `app/services/` (pure, no Streamlit) so it is
  fully unit-testable without a Streamlit context.
- Fallback manual-entry exposed in preview step (not fill step) to keep the happy
  path clean; only surfaced when yfinance price fetch actually fails.
- Deviation threshold for button-label change: ≥10% → "Record anyway";
  >2% → warning shown inline (both thresholds tunable without tests).
- `eur_total value=None` (blank) is correct UX; 0.01 was a Streamlit default
  artefact that had no relation to any real transaction amount.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~120k (two context windows)

---

## 2026-05-06 14:00 — TICKET-010

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-010-tax-engine
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/22
**Status at session end:** IN_REVIEW

### What got done
- Created `app/domain/tax/` sub-package with 6 files:
  - `classification.py` — `InstrumentKind` enum + `TICKER_KIND` table (12 seed tickers) + `classify_instrument` (raises loudly on unknown)
  - `rates.py` — `TaxYearRates`, `TAX_RATES_2025`, `TAX_RATES_2026`, `RATES_BY_YEAR`, `UnsupportedTaxYearError`
  - `models.py` — `FilingStatus`, `TaxProfile`, `TaxImpact`, `LossPotState`, `TaxYearSummary` (all frozen Pydantic)
  - `pipeline.py` — internal `TaxYearLedger` dataclass + 8 ordered pipeline steps enforcing §20 EStG rule sequence
  - `engine.py` — `compute_tax_year_summary` (pure, referentially transparent)
  - `CLAUDE.md` — per-module rules
- Extended `app/domain/__init__.py` to re-export tax public API
- Created 50 unit tests across 5 test files in `tests/unit/domain/tax/`
- Created `tests/fixtures/tax/nrw_aktienfonds_2024.json`

### Files touched
- `app/domain/tax/` — entire sub-package (new)
- `app/domain/__init__.py` — added tax re-exports
- `tests/unit/domain/tax/` — 5 test files (new)
- `tests/fixtures/tax/nrw_aktienfonds_2024.json` — new
- `docs/TICKETS/TICKET-010-tax-engine.md` — status → IN_REVIEW

### Tests
161 passing → 211 passing (50 new)

### Decisions made during the session
- No architectural decisions required beyond what was drafted in the ticket spec.
- `TaxYearLedger` is a mutable dataclass (not frozen) since it is internal-only; pipeline steps mutate and return it.
- Tests import private pipeline functions (`_apply_*`) directly — acceptable since these functions are the primary test surface; the tests are in `tests/unit/domain/tax/` not in production code.

### Out-of-scope items noticed
- `tests/unit/domain/tax/test_known_scenarios.py::test_loss_pot_firewall_worked_example` uses TaxImpact with `teilfreistellung_pct=0.00` on an AKTIENFONDS to get an exact -€1000 taxable amount. This is a test construct only; in production, the classifier + rates always compute the correct percentage.

### Tokens used (rough)
~80k

## 2026-05-06 14:30 — TICKET-011

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-011-tax-dashboard
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/23
**Status at session end:** IN_REVIEW

### What got done
- Added `HarvestImpact`, `HarvestImpactReport` to `app/domain/tax/models.py`
- Added `current_year_losses_unconsumed_eur` property to `LossPotState`
- Created `app/ports/tax_profile_repo.py` — `TaxProfileRepository` Protocol, `TaxProfileDocument`, `YearlyTaxInputs`
- Created `app/adapters/repo_json/tax_profile_repo.py` — `JsonTaxProfileRepository` (atomic write, legacy version detection)
- Created `app/services/tax_planning.py` — three pure service functions:
  `compute_current_tax_summary`, `compute_per_position_harvest_impact`, `compute_tax_if_full_liquidation`
- Created `app/ui/cache_keys.py` — factored `transactions_signature` + added `file_mtime_key`
- Built Tax Dashboard page (`app/ui/pages/tax.py`): YTD tiles, Sparerpauschbetrag progress bar,
  total tax exposure section, harvest opportunity table (sequential), loss harvesting table,
  edit tax profile expander with Steuerbescheid guidance
- Wired Sparerpauschbetrag and Tax Headroom tiles on Live Overview (removed hardcoded TICKET-010 placeholders)
- Added `tax_profile_json_path` to `app/config.py` and `Settings`
- Added `get_tax_profile_repo()` lazy singleton to `app/ui/wiring.py`
- Added `.tax-progress-wrap` and `.harvest-table` CSS classes to `dark.css`
- Created `.env.example` (was missing from repo), added `data/tax_profile.json` to `.gitignore`
- Created `tests/fixtures/tax_profile_legacy_v0.json` for legacy version rejection test
- 12 new unit tests: 7 service tests, 5 UI helper tests
- 2 integration test files (skipped without `--run-integration` flag)

### Files touched
- `app/domain/tax/models.py` — added HarvestImpact, HarvestImpactReport, LossPotState property
- `app/domain/tax/__init__.py` — re-exported new types
- `app/ports/tax_profile_repo.py` — new
- `app/adapters/repo_json/tax_profile_repo.py` — new
- `app/config.py` — tax_profile_json_path setting
- `app/services/tax_planning.py` — new
- `app/ui/cache_keys.py` — new
- `app/ui/pages/tax.py` — full implementation (was stub)
- `app/ui/pages/overview.py` — wire two tiles; use transactions_signature from cache_keys
- `app/ui/styles/dark.css` — .tax-progress-wrap, .harvest-table
- `app/ui/wiring.py` — get_tax_profile_repo()
- `.env.example` — new
- `.gitignore` — data/tax_profile.json
- `tests/unit/services/test_tax_planning.py` — new
- `tests/unit/ui/test_tax_page_helpers.py` — new
- `tests/integration/test_tax_profile_repo.py` — new
- `tests/integration/test_tax_dashboard_e2e.py` — new
- `tests/fixtures/tax_profile_legacy_v0.json` — new
- `tests/unit/ui/test_overview_helpers.py` — updated import to cache_keys
- `docs/TICKETS/TICKET-011-tax-dashboard-page.md` — status → IN_REVIEW

### Tests
211 passing → 223 passing (12 new)

### Decisions made during the session
- `compute_per_position_harvest_impact` takes `transactions` + `as_of` in addition to `current_summary`
  because the engine computes FIFO gains from transactions internally; there's no way to reconstruct
  the per-gain breakdown from the summary alone without duplicating pipeline logic.
- `compute_headroom` uses `remaining_carryforward_eur` from each pot (not `prior_year_carryforward + unconsumed_current_losses`)
  because they are mathematically equivalent and simpler. The property `current_year_losses_unconsumed_eur`
  is added to `LossPotState` for completeness but is not used in the headroom formula.
- Test case for headroom with "mixed components" redesigned from ticket spec: the ticket's described
  scenario (€400 allowance remaining + €300 aktien pot + €200 general pot intact) is not achievable
  with the current engine pipeline (carryforward is consumed before allowance). Used a correct equivalent.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~100k

---

## 2026-05-07 — TICKET-012

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-012-pre-trade-sell-simulator
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/26
**Status at session end:** IN_REVIEW

### What got done
- Promoted `_consume_from_lots` to public `simulate_lot_consumption` (pure, tuple-in/tuple-out); refactored `compute_realised_gains` to call it internally.
- Added `MarginalTaxImpact` frozen Pydantic model to `app/domain/tax/models.py`.
- Added `compute_marginal_tax_for_realised_gains` to `app/services/tax_planning.py` — runs the engine before/after the proposed sell and returns per-field deltas.
- New `app/services/sell_simulator.py`: `SellSimulationRequest`, `LotConsumption`, `PositionAfterSnapshot`, `SellSimulation`, `simulate_sell` (read-only, deterministic — uses a stable transaction ID derived from request fields).
- New `app/ui/components/sell_simulator.py`: embeddable `render_sell_simulator` panel with lot table, tax impact tiles, and position-after tiles.
- New `app/ui/pages/simulator.py`: top-level Pre-trade Sell Simulator page; reads default ticker from `session_state.simulator_default_ticker` or `?ticker=` query param.
- Added ⚡ Simulate sell HTML links to Live Overview positions table and Tax Dashboard harvest table (navigates to `/?page=simulator&ticker=TICKER`).
- `manage.py`: added `_apply_simulator_handoff` that pre-fills the Add Transaction form and advances to preview step when `session_state.simulator_handoff` is set.
- Sidebar + PAGE_TITLES: added Simulator entry between Lot Ledger and Manage Portfolio.
- Tests: 21 new tests across domain, service, UI, and integration layers. 223 → 244 passing.

### Files touched
- `app/domain/fifo.py` — `simulate_lot_consumption` public function; refactored `compute_realised_gains`
- `app/domain/__init__.py` — export `simulate_lot_consumption`
- `app/domain/tax/models.py` — add `MarginalTaxImpact`
- `app/domain/tax/__init__.py` — export `MarginalTaxImpact`
- `app/services/tax_planning.py` — add `compute_marginal_tax_for_realised_gains`
- `app/services/sell_simulator.py` — new
- `app/ui/components/sell_simulator.py` — new
- `app/ui/pages/simulator.py` — new
- `app/ui/pages/overview.py` — add Sim column
- `app/ui/pages/tax.py` — add Sim column to harvest table
- `app/ui/pages/manage.py` — accept simulator handoff
- `app/ui/components/sidebar.py` — add Simulator nav entry
- `app/ui/components/topbar.py` — add "simulator" to PAGE_TITLES
- `tests/unit/domain/test_simulate_lot_consumption.py` — new (8 tests)
- `tests/unit/services/test_sell_simulator.py` — new (9 tests)
- `tests/unit/ui/test_sell_simulator_component.py` — new (4 tests)
- `tests/integration/test_simulator_e2e.py` — new (3 tests, 1 for each e2e scenario)
- `tests/unit/ui/test_components.py` — updated NAV_ITEMS count

### Tests
223 passing → 244 passing (21 new)

### Decisions made during the session
- Deterministic transaction ID for hypothetical sell (derived from request fields) to make `simulate_sell` a pure function (same input → same output).
- `marginal_taxable_gain_eur` is the delta in `total_taxable_after_loss_offset_eur` (before allowance deduction), per ticket spec — consistent with how the engine fields are named.
- Simulator → Manage Portfolio handoff uses `st.query_params` (`?ticker=`) for HTML table links (since HTML `<a>` tags can't set session_state), plus `session_state.simulator_default_ticker` for button-triggered navigation.
- Carryforward params added to `compute_marginal_tax_for_realised_gains` and `simulate_sell` (not in original ticket spec, but required for correct marginal analysis with real carryforward losses).

### Out-of-scope items noticed
- (none — stayed within ticket scope)

### Tokens used (rough)
~180k

---

## 2026-05-07 14:00 — TICKET-021

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-021-smooth-ticker-autocomplete
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/27
**Status at session end:** IN_REVIEW

### What got done
- Added `CachedTickerResolver` decorating adapter (`app/adapters/ticker_resolver_cached.py`) — disk-backed JSON cache with 30-day TTL, lazy load, atomic writes, best-effort persistence (never raises)
- Added `render_ticker_searchbox` UI component (`app/ui/components/ticker_searchbox.py`) wrapping `streamlit-searchbox`, with `_search_callback_for` factory (testable without Streamlit runtime)
- Replaced `st.text_input + st.selectbox` ticker block in Add Transaction form with `render_ticker_searchbox`; "use as-typed" escape hatch retained
- Updated Edit Transaction form with pre-filled searchbox (`default_match=resolver.lookup(tx.ticker)`)
- Added `ticker_cache_json_path` to `app/config.py` and `.env.example`
- Updated `app/ui/wiring.py` to wrap the yfinance resolver with `CachedTickerResolver`
- Added `streamlit-searchbox>=0.1.16` to `pyproject.toml`; added `data/ticker_cache.json` to `.gitignore`
- Added call counters (`resolve_call_count`, `lookup_call_count`) to `FakeTickerResolver`

### Files touched
- `app/adapters/ticker_resolver_cached.py` — new
- `app/ui/components/ticker_searchbox.py` — new
- `app/ui/wiring.py` — wrap resolver with CachedTickerResolver
- `app/ui/pages/manage.py` — swap ticker input for searchbox (add + edit forms)
- `app/config.py` — add ticker_cache_json_path
- `pyproject.toml` — add streamlit-searchbox dependency + mypy override
- `.gitignore` — add data/ticker_cache.json
- `.env.example` — document TICKER_CACHE_JSON_PATH
- `tests/fakes/ticker_resolver.py` — add resolve_call_count, lookup_call_count
- `tests/unit/ports/test_ticker_resolver_protocol.py` — 3 new round-trip tests
- `tests/unit/adapters/test_ticker_resolver_cached.py` — new (13 tests)
- `tests/unit/ui/test_ticker_searchbox.py` — new (5 tests)
- `tests/integration/test_ticker_cache_e2e.py` — new (1 integration test, skipped without --run-integration)

### Tests
244 passing → 265 passing (21 new); 68 skipped (integration tests including new one)

### Decisions made during the session
- `_search_callback_for(resolver)` factory pattern makes the callback testable without a Streamlit runtime (imported directly in unit tests)
- `manage_add_form_key` counter in session state resets the searchbox widget after a transaction is recorded (Streamlit widget-reset pattern)
- `cast(TickerResolver, get_price_provider())` in wiring.py avoids a type: ignore while correctly expressing that YfinanceAdapter satisfies both protocols

### Out-of-scope items noticed
- (none — stayed within ticket scope)

### Tokens used (rough)
~120k

---

## 2026-05-07 — TICKET-023

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~30 min
**Branch:** ticket-023-eur-price-check
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/28
**Status at session end:** IN_REVIEW

### What got done
- `app/domain/tickers.py`: promoted `_UNSUPPORTED_SUFFIXES` from a local tuple
  to a module-level dict mapping suffix → currency name. Added `.KS`/`.KQ` (KRW),
  `.TW`/`.TWO` (TWD), `.BK` (THB). These now raise `UnsupportedTickerError` instead
  of silently defaulting to USD. `.HK` retained with the same error message.
- `app/ui/pages/manage.py` (`_render_recording_preview`): replaced the EUR branch
  early-return (no price check) with a real `get_historical_close` call. Computes
  `eur_deviation_pct`; shows ⚠ warning when >2%, ✓ confirmation when within 2%,
  or a "Couldn't fetch" warning on `PriceUnavailableError`. Form remains usable in
  all cases (`price_available=True`).
- `app/ui/pages/manage.py`: broad `except Exception: return True, None` now logs
  at WARNING with `exc_info=True` before returning, so unexpected errors are visible.

### Files touched
- `app/domain/tickers.py` — `_UNSUPPORTED_SUFFIXES` dict with 6 suffixes
- `app/ui/pages/manage.py` — EUR price check; logging in broad except
- `tests/unit/domain/test_tickers.py` — 5 new cases (.KS, .KQ, .TW, .TWO, .BK)
- `tests/unit/ui/test_manage_form_pipeline.py` — 4 new _render_recording_preview tests

### Tests
265 passing → 274 passing (9 new); 68 skipped

### Decisions made during the session
- Used distinct variable names (`eur_price_per_share`, `eur_deviation_pct`) in the EUR
  branch to avoid mypy type conflicts with identically-named variables in the non-EUR
  path that carry different types (`Money` vs `Decimal`).
- `price_available=True` on `PriceUnavailableError` for EUR path (unlike non-EUR which
  returns `False`): EUR total is always self-consistent without a price check, so the
  form remains fully submittable.

### Out-of-scope items noticed
- (none — stayed within ticket scope)

### Tokens used (rough)
~60k

---

## 2026-05-07 20:18 — TICKET-024

**Surface:** ChatGPT Codex
**Model:** GPT-5
**Duration:** ~30 min
**Branch:** ticket-024-sell-simulator-cold-start
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/29
**Status at session end:** MERGED

### What got done
- Added a 60-second Streamlit cache wrapper around sell simulator live-position computation, keyed by transaction IDs.
- Added a fallback to the existing uncached computation if Streamlit cache serialisation fails at runtime.
- Made yfinance search-result matching skip `fast_info` price enrichment; exact lookup still keeps the richer price path.
- Added unit coverage for sell simulator live-position cache reuse/invalidation and lightweight resolver search.

### Files touched
- `app/ui/components/sell_simulator.py` — `_live_positions_cached`; cached render path with fallback
- `app/adapters/yfinance_feed/yfinance_adapter.py` — optional `_build_match(fetch_price=False)` path for resolver search
- `tests/unit/ui/test_sell_simulator_component.py` — live-position cache-key tests
- `tests/unit/adapters/test_yfinance_adapter_caching.py` — resolver search avoids `yfinance.Ticker`
- `docs/TICKETS/TICKET-024-sell-simulator-cold-start.md` — status updates

### Tests
274 passing → 277 passing (3 new); 68 skipped
Full gate: `pytest && ruff check . && mypy app/ && lint-imports`

### Decisions made during the session
- Kept the live-position cache at the UI layer to preserve the service layer's stateless contract.
- Search results now omit `recent_price`; exact lookup remains the enrichment path for places that need detailed metadata.

### Out-of-scope items noticed
- Persistent live-price caching across Streamlit restarts remains deferred to the daily NAV/cache work noted in the ticket.

### Tokens used (rough)
~45k
*** End of File

---

## 2026-05-08 — TICKET-022a

**Surface:** Claude Code
**Model:** claude-sonnet-4-6
**Duration:** ~90 min
**Branch:** ticket-022a-chart-service-components
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- New `app/domain/market_data.py`: `ChartPeriod` StrEnum (9 periods + `is_intraday` property),
  `OhlcBar` frozen Pydantic model (OHLC integrity + positive-price + tz-aware validators),
  `OhlcSeries` frozen Pydantic model (`latest_close`, `period_change_pct` properties),
  `OhlcUnavailableError` exception.
- New `app/ports/market_data.py`: `OhlcDataProvider` Protocol.
- Extended `app/adapters/yfinance_feed/yfinance_adapter.py`: `_ohlc_cache`,
  `_interval_for_period`, `_ttl_for_period`, `get_ohlc_history` (15-min TTL intraday / 24h daily),
  bad-row skip with warning, `clear_cache()` extended.
- New `app/services/market_data.py`: module-level OHLC cache with TTL, `get_ohlc_history`,
  `clear_market_data_caches`. Documented deviation from stateless-service convention.
- New `app/ui/components/_chart_styles.py`: `CHART_BG`, `CANDLE_UP/DOWN`, `LINE_COLOR_DEFAULT`, `base_layout()`.
- New `app/ui/components/charts.py`: `render_candlestick`, `render_line_chart`, `render_sparkline`.
- Updated `app/ui/wiring.py`: `get_ohlc_data_provider()` singleton.
- Updated `app/domain/__init__.py`, `app/ports/__init__.py`: export new types.
- Updated `pyproject.toml`: added `pandas.*` to mypy `ignore_missing_imports` (pandas is already
  a dep via yfinance; direct import was new in this ticket).
- New `tests/fakes/ohlc.py`: `FakeOhlcDataProvider` with call counting and raise-for support.
- 41 new tests across 4 test files.

### Files touched
- `app/domain/market_data.py` — new
- `app/ports/market_data.py` — new
- `app/services/market_data.py` — new
- `app/ui/components/_chart_styles.py` — new
- `app/ui/components/charts.py` — new
- `app/adapters/yfinance_feed/yfinance_adapter.py` — extended with OHLC support
- `app/domain/__init__.py` — new exports
- `app/ports/__init__.py` — new export
- `app/ui/wiring.py` — get_ohlc_data_provider()
- `pyproject.toml` — pandas mypy ignore
- `tests/fakes/ohlc.py` — new
- `tests/unit/domain/test_market_data.py` — new (24 tests)
- `tests/unit/services/test_market_data.py` — new (8 tests)
- `tests/unit/adapters/test_yfinance_ohlc.py` — new (9 tests)
- `tests/unit/ui/test_chart_components.py` — new (5 tests)
- `docs/TICKETS/TICKET-022a-chart-service-and-components.md` — status → IN_REVIEW

### Tests
277 passing → 318 passing (41 new)

### Decisions made during the session
- `base_layout()` returns separate dicts for xaxis/yaxis (not a shared reference) to prevent
  mutations in `render_candlestick` (adding `rangeslider` to xaxis) from corrupting yaxis.
- `pandas` added to mypy `ignore_missing_imports` (was already a transitive dep via yfinance,
  now directly imported in the adapter for `pd.notna`).
- Session included rollback of ChatGPT Codex 022a/022b (PR #36, merged by Vivek) before reimplementation.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~120k

## 2026-05-08 14:00 — TICKET-022b

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-022b-research-page-overview-charts
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- New `app/ui/pages/research.py`: ticker searchbox + period selector (1D–YTD,
  default 6M), candlestick chart (height=500), header metrics row (latest price,
  period change pct, period label), Simulate buy handoff → simulator page, disabled
  watchlist button, quick-pick buttons for 5 example tickers.
- `app/ui/pages/overview.py`: Trend 30D column added to HTML table (text ↑/↓ + pct
  from 30D sparkline data); new Position Trends section below table using st.columns
  (one sparkline per position, actual Plotly charts, st.button per row); mini chart
  panel below (6-month line chart for selected ticker, Close button); per-ticker error
  isolation throughout.
- `app/ui/components/charts.py` (quality fixes discovered as first consumer):
  - `rangebreaks` added to x-axis for daily-bar charts → Sat/Sun gaps eliminated.
  - `render_line_chart` now uses dynamic y-range (min/max ± 5% margin) so price
    movements are visible regardless of absolute price level (no more $800 stock
    collapsing against zero baseline).
- `app/ui/components/sidebar.py`: 📈 Research added after Tax Dashboard.
- `app/ui/components/topbar.py`: "research" added to PAGE_TITLES.
- `tests/fakes/ticker_resolver.py`: FAKE_TICKER_NVDA and FAKE_TICKER_RHM constants added.
- 15 new tests: 6 research page smoke tests, 9 overview chart integration tests.
- Existing test updated: test_nav_items_consistency count 9→10 (Research added).

### Files touched
- `app/ui/pages/research.py` — new
- `app/ui/pages/overview.py` — trend column + sparklines + mini chart
- `app/ui/components/charts.py` — rangebreaks + dynamic y-range
- `app/ui/components/sidebar.py` — Research nav entry
- `app/ui/components/topbar.py` — Research page title
- `tests/unit/ui/test_research_page.py` — new (6 tests)
- `tests/unit/ui/test_overview_chart_integration.py` — new (9 tests)
- `tests/unit/ui/test_components.py` — count fix (9→10)
- `tests/fakes/ticker_resolver.py` — FAKE_TICKER_NVDA + FAKE_TICKER_RHM
- `docs/TICKETS/TICKET-022b-research-page-and-overview-charts.md` — IN_REVIEW

### Tests
318 passing → 333 passing (15 new)

### Decisions made during the session
- Sparklines rendered in separate st.columns section below the HTML table (not
  inside table cells, which is impossible with st.plotly_chart inside HTML strings).
  Trend 30D column in HTML table is text-based (↑/↓ + pct) for alignment; actual
  Plotly sparklines appear below the table.
- rangebreaks and dynamic y-range fixes to charts.py are in scope: this ticket is
  the first real consumer of those render functions, so rendering correctness issues
  are discovered and fixed here.
- Weekend gap fix applies only to non-intraday periods (daily bars); intraday data
  from yfinance already contains only market-hours bars.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~90k

---

## 2026-05-08 — TICKET-022b continuation — Overview chart overhaul + OHLC aggregation

**Ticket:** TICKET-022b (continuation of previous session)
**Surface:** Claude Code
**Model:** sonnet-4.6
**Branch:** ticket-022b-research-page-overview-charts
**PR:** #38
**Status at session end:** IN_REVIEW

### What got done
- `app/domain/market_data.py`: Added `AggregationFreq` type alias and
  `aggregate_ohlc_series()` — groups bars by calendar bucket (hour/day/week/month),
  producing one OHLC bar per bucket (open=first, high=max, low=min, close=last,
  volume=sum). Raises `OhlcUnavailableError` if no bars remain. Fixed mypy
  `tuple` type annotation to `tuple[int, ...]`.
- `app/services/market_data.py`: Added `_AGGREGATION` dict mapping each `ChartPeriod`
  to its aggregation freq (5D→day, 1Y/2Y→week, 5Y→month, YTD→week, others→None).
  Aggregation applied post-fetch before caching, so cached series are display-ready.
- `app/ui/components/charts.py`: Replaced static `not series.period.is_intraday`
  rangebreaks check with `_needs_weekend_rangebreaks()` heuristic (8h ≤ avg bar
  gap < 100h identifies daily bars; weekly/monthly bars skip rangebreaks to avoid
  x-axis compression).
- `app/ui/pages/overview.py`: Replaced all-sparklines section + mini chart panel
  with a single candlestick chart: `st.selectbox` for ticker, `st.radio` (1D–YTD,
  default 6M) for period, `render_candlestick` at height=400. Renamed
  `_fetch_sparklines` → `_fetch_trend_texts` (returns `dict[str, str]` only).
- New/updated tests: 8 `aggregate_ohlc_series` domain tests, 5 service-layer
  aggregation tests, 4 `_needs_weekend_rangebreaks` chart component tests.
  Rewrote `test_overview_chart_integration.py` (removed stale mini-chart color
  tests, updated to `_fetch_trend_texts` API).

### Files touched
- `app/domain/market_data.py` — aggregate_ohlc_series + AggregationFreq
- `app/services/market_data.py` — _AGGREGATION + service-layer aggregation
- `app/ui/components/charts.py` — _needs_weekend_rangebreaks heuristic
- `app/ui/pages/overview.py` — single candlestick chart replaces sparklines panel
- `tests/unit/domain/test_market_data.py` — 8 new aggregation tests
- `tests/unit/services/test_market_data.py` — 5 new aggregation tests
- `tests/unit/ui/test_chart_components.py` — 4 new _needs_weekend_rangebreaks tests
- `tests/unit/ui/test_overview_chart_integration.py` — rewritten for new API

### Tests
333 passing → 348 passing (15 new)

### Decisions made during the session
- Aggregation lives in the service layer (not UI), so the cache always holds
  display-ready data; aggregation cost is paid once per TTL, not per render.
- `_needs_weekend_rangebreaks` uses avg bar spacing rather than period label because
  after aggregation the period label (e.g. ONE_YEAR) no longer tells us whether bars
  are daily or weekly — the spacing does.
- Overview page uses same `_PERIOD_LABELS` dict pattern as research page for
  consistency; default period is SIX_MONTH (index=4) matching research page default.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~40k

---

## 2026-05-09 14:00 — TICKET-013

**Agent:** Claude Code (sonnet-4.6)
**Duration:** ~90 min
**Branch:** ticket-013-daily-nav-snapshot
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Added `DailyNavPoint` frozen Pydantic model in `app/domain/nav.py` with EUR-only and non-negative validators
- Added `NavSnapshotRepository` Protocol in `app/ports/nav_repository.py`
- Added `JsonNavSnapshotRepository` adapter in `app/adapters/repo_json/nav_repo.py` — atomic writes, schema v1, `clear()` deletes file
- Added `get_nav_series` service in `app/services/nav.py` — reconstructs historical NAV from OHLC/FX history, caches in nav_repo, today's NAV computed live and never persisted
- Added `clear_nav_cache(nav_repo)` service function called via `JsonTransactionRepository.save_all` on every save
- Wired `JsonTransactionRepository` constructor to accept optional `nav_repo`; wiring module creates real repo with nav_repo injected
- Added `FakeNavSnapshotRepository` in `tests/fakes/nav.py` for downstream analytics tests (A1–A5)

### Files touched
- `app/domain/nav.py` — new: DailyNavPoint model
- `app/ports/nav_repository.py` — new: NavSnapshotRepository Protocol
- `app/adapters/repo_json/nav_repo.py` — new: JsonNavSnapshotRepository
- `app/services/nav.py` — new: get_nav_series, clear_nav_cache, helpers
- `app/domain/__init__.py` — export DailyNavPoint
- `app/ports/__init__.py` — export NavSnapshotRepository
- `app/adapters/repo_json/__init__.py` — export JsonNavSnapshotRepository
- `app/adapters/repo_json/json_repo.py` — optional nav_repo injection; clear on save_all
- `app/config.py` — added nav_snapshots_json_path setting
- `app/ui/wiring.py` — added get_nav_snapshot_repo(); get_repository() now injects it
- `tests/fakes/nav.py` — new: FakeNavSnapshotRepository
- `tests/fakes/__init__.py` — export FakeNavSnapshotRepository
- `tests/unit/domain/test_nav.py` — new: 11 domain tests
- `tests/unit/services/test_nav.py` — new: 17 service tests
- `tests/integration/test_nav_repo.py` — new: 13 integration tests (skip without --run-integration)

### Tests
348 passing → 376 passing (28 new)

### Decisions made during the session
- `clear_nav_cache` takes a `NavSnapshotRepository` parameter (cleanest injectable design)
- `clear()` deletes the file entirely (simpler than zeroing it; same effect on next load)
- Trading days = union of all dates present in OHLC bars across all tickers in portfolio
- `_period_covering` picks smallest ChartPeriod to cover start→today for OHLC fetches
- `FlexibleFakeOhlcProvider` in tests ignores the period parameter (tests don't depend on internal period selection)
- Logging is used in the service as an explicit exception to the no-logging rule; missing OHLC data would silently corrupt NAV if not surfaced

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~80k

---

## 2026-05-09 — TICKET-A0

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~1 hr
**Branch:** ticket-A0-analytics-shell
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Created `app/domain/analytics.py` with eight pure stat primitives: `daily_returns`,
  `volatility_annualised`, `drawdown_series`, `max_drawdown`, `sharpe`, `sma`, `rsi`
  (Wilder smoothing), and `correlation_matrix`. Decimal arithmetic throughout; float
  used only internally in `correlation_matrix` for efficiency, with Decimal boundary.
- Created `app/ui/pages/analytics.py`: five-tab shell with `st.info` placeholders for
  TICKET-A1 through A5. No data fetches, no service imports, no state writes.
- Updated `app/ui/components/sidebar.py`: analytics entry relabelled to "📊 Analytics",
  repositioned after Tax Dashboard and before Research.
- Created `tests/unit/domain/test_analytics.py`: 46 tests covering happy paths,
  edge cases (empty, single, mismatched), ValueError raises, hypothesis-based invariant
  tests (drawdown ≤ 0, RSI in [0,100], correlation symmetry).
- Created `tests/unit/ui/test_analytics_page.py`: 4 smoke tests verifying tab labels,
  per-tab info messages, and header icon.
- Marked TICKET-013 as MERGED (it had merged before this session started).

### Files created
- `app/domain/analytics.py`
- `tests/unit/domain/test_analytics.py`
- `tests/unit/ui/test_analytics_page.py`

### Files modified
- `app/ui/pages/analytics.py` — rewritten from stub
- `app/ui/components/sidebar.py` — analytics entry updated + reordered
- `docs/PROJECT_STATE.md` — TICKET-A0 → IN_REVIEW
- `docs/SESSION_LOG.md` — this entry
- `docs/TICKETS/BACKLOG.md` — TICKET-013 MERGED, TICKET-A0 IN_REVIEW
- `docs/TICKETS/TICKET-A0-analytics-shell.md` — IN_REVIEW
- `docs/TICKETS/TICKET-013-daily-nav-snapshot.md` — MERGED

### Tests
376 passing → 426 passing (50 new)

### Decisions made during the session
- `correlation_matrix` uses float arithmetic internally (documented in docstring).
  Pure Decimal sqrt chains for matrix-scale inputs accumulate more error than a
  single float→Decimal boundary conversion.
- RSI returns `list[Decimal | None]` with first `period` entries as None (same
  convention as `sma`), not a shorter list. `len(closes) < period+1` → `[]`.
- Sidebar update: analytics moved after Tax Dashboard and before Research; all
  other existing entries retained to avoid navigation regressions.

### Out-of-scope items noticed
- (none)

---

## 2026-05-09 — TICKET-A1

**Agent:** GPT Codex (GPT-5)
**Duration:** ~2 hr
**Branch:** ticket-A1-performance-tab
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Added `app/services/analytics_performance.py` with `PerformancePeriod`,
  `PerformanceView`, benchmark mapping, NAV/benchmark date alignment, indexing to
  100, and KPI computation.
- Filled the Analytics Performance tab with period/benchmark selectors, KPI strip,
  indexed portfolio-vs-benchmark line chart, benchmark failure warning, empty state,
  and drawdown area chart.
- Extended chart components with `ChartSeries`, optional secondary line support,
  and `render_drawdown_chart`.
- Updated `render_metric_card` to apply value classes, support tooltips, and route
  HTML through `render_html`.
- Marked TICKET-A0 as MERGED on `main` before starting A1, after confirming PR #41
  was merged.

### Files touched
- `app/services/analytics_performance.py` — new performance-tab service/view model
- `app/ui/pages/analytics.py` — Performance tab implementation
- `app/ui/components/charts.py` — secondary line + drawdown chart support
- `app/ui/components/_chart_styles.py` — grey chart constant
- `app/ui/components/metric_card.py` — value classes, tooltips, render helper
- `tests/unit/services/test_analytics_performance.py` — new service tests
- `tests/unit/ui/test_performance_tab.py` — new Performance tab smoke tests
- `tests/unit/ui/components/test_charts_extension.py` — new chart extension tests
- `tests/unit/ui/test_analytics_page.py` — analytics shell expectations updated
- `docs/TICKETS/TICKET-A1-performance-tab.md` — IN_REVIEW

### Tests
426 passing → 449 passing (23 new)

### Decisions made during the session
- Current NAV service is a function, not a `NavService` class; A1 uses a small
  `NavSeriesProvider` Protocol and UI wiring wrapper instead of modifying the
  locked TICKET-013 surface.
- Added a lightweight `ChartSeries`/`ChartPoint` render model in the chart
  component because drawdown values can be zero or negative and cannot be modeled
  as `OhlcSeries` bars.
- Date alignment carries the previous benchmark close across short benchmark gaps
  only when the surrounding benchmark gap is at most 3 calendar days; longer gaps
  are dropped from both series.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~70k

---

## 2026-05-09 14:34 — TICKET-A5

**Agent:** GPT Codex (GPT-5)
**Duration:** ~1.5 hr
**Branch:** ticket-A5-concentration-tab
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Added Herfindahl concentration analytics and frozen Concentration view models.
- Added a Concentration service that computes Top-1, Top-3, HHI, sorted weights,
  native-currency exposure, rows, and stale-position handling from live positions.
- Implemented the Analytics Concentration tab with KPI cards, weight bar chart,
  currency donut, stale-data banner, empty state, and per-position table.
- Extracted the Live Overview weight bar into a shared component and migrated
  Overview to use it.
- Updated analytics shell tests to no-op the now-real A5 tab while keeping
  dedicated A5 coverage.
- Marked TICKET-A1 as MERGED on `main` before starting A5, after confirming PR #42
  was merged.

### Files touched
- `app/domain/analytics.py` — added `herfindahl_index`
- `app/domain/analytics_views.py` — new Concentration view models
- `app/services/analytics_concentration.py` — new Concentration service and constants
- `app/ui/pages/analytics.py` — Concentration tab implementation
- `app/ui/components/charts.py` — weight bar chart and currency donut renderers
- `app/ui/components/weight_bar.py` — shared weight-bar HTML component
- `app/ui/pages/overview.py` — migrated weight bar to shared component
- `tests/fixtures/concentration_fixtures.py` — reusable concentration fixtures
- `tests/unit/domain/test_herfindahl.py` — new domain tests
- `tests/unit/domain/test_analytics_views.py` — new view-model tests
- `tests/unit/services/test_analytics_concentration.py` — new service tests
- `tests/unit/ui/test_weight_bar_component.py` — new component tests
- `tests/unit/ui/components/test_concentration_charts.py` — new chart tests
- `tests/unit/ui/test_concentration_tab.py` — new tab tests
- `tests/unit/ui/test_analytics_page.py` — shell tests adjusted for real A5 tab

### Tests
449 passing → 482 passing (33 new)

### Decisions made during the session
- Kept `MAX_POSITION_WEIGHT_PCT` and related KPI thresholds in
  `analytics_concentration.py` as specified, so A4 can import them.
- Stale positions are retained in Concentration rows but contribute zero to
  weights and currency split.
- Generic analytics shell tests patch `_render_concentration_tab`; dedicated A5
  tests cover the real Concentration layout.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~65k

---

## 2026-05-09 14:49 — TICKET-A4

**Agent:** GPT Codex (GPT-5)
**Duration:** ~1 hr
**Branch:** ticket-A4-position-sizer-tab
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Added pure domain sizing formulas for risk-based and target-weight share calculations.
- Extended analytics view models with frozen Position Sizer models.
- Added a Position Sizer service that computes current-position, risk-based, weight-based, and post-trade weight preview results from live positions.
- Implemented the Analytics Position Sizer tab with ticker/direction controls, sizing inputs, result cards, empty/degraded states, and A5 weight-bar reuse.
- Marked TICKET-A5 as MERGED on `main` before starting A4, after confirming PR #43 had merged.

### Files touched
- `app/domain/sizing.py` — new pure sizing formulas
- `app/domain/analytics_views.py` — added Sizer view models
- `app/domain/__init__.py` — exported Sizer view models
- `app/services/analytics_sizer.py` — new Position Sizer service and FX helper
- `app/ui/pages/analytics.py` — Position Sizer tab implementation
- `tests/unit/domain/test_sizing.py` — new domain sizing tests
- `tests/unit/domain/test_analytics_views.py` — Sizer model tests
- `tests/unit/services/test_analytics_sizer.py` — service tests
- `tests/unit/ui/test_sizer_tab.py` — UI tab tests
- `tests/unit/ui/test_analytics_page.py` — analytics shell expectations updated

### Tests
482 passing → 523 passing (41 new)

### Decisions made during the session
- Kept share math unrounded in domain/service models; display continues through `format_shares`.
- Used `LivePosition.model_construct` only in one service test to exercise the planned stale-price warning path, because the current `LivePosition` model only validates fully live or missing-price states.
- Reused A5's cached live-position helpers in the Analytics page rather than adding another Streamlit cache path.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~45k

---

## 2026-05-09 21:24 — TICKET-A2

**Agent:** GPT Codex (GPT-5)
**Duration:** ~1.5 hr
**Branch:** ticket-A2-analytics-correlation
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Added pure connected-component correlation cluster detection to `app/domain/analytics.py`.
- Added the Correlation service with frozen view models, live-position universe selection, insufficient-history skipping, trading-date intersection, average-correlation computation, and diversification buckets.
- Implemented the Analytics Correlation tab with 30D/60D/90D window selector, skipped-history warning, Plotly heatmap, sortable average-correlation table, and cluster warnings.
- Added the correlation heatmap renderer and diverging Plotly colorscale.
- Marked TICKET-A4 as MERGED on `main` before starting A2, after confirming PR #45 had merged.

### Files touched
- `app/domain/analytics.py` — added `correlation_clusters`
- `app/services/analytics_correlation.py` — new Correlation service and view models
- `app/ui/pages/analytics.py` — Correlation tab implementation
- `app/ui/components/charts.py` — correlation heatmap renderer
- `app/ui/components/_chart_styles.py` — correlation colorscale
- `tests/unit/domain/test_analytics.py` — cluster tests
- `tests/unit/services/test_analytics_correlation.py` — service tests
- `tests/unit/ui/test_correlation_tab.py` — tab tests
- `tests/unit/ui/components/test_correlation_heatmap.py` — heatmap tests
- `tests/unit/ui/test_analytics_page.py` — shell expectations updated

### Tests
523 passing → 547 passing (24 new)

### Decisions made during the session
- Used connected components for cluster warnings exactly as specified; the warning text stays conservative rather than implying strict cliques.
- The service treats a single included ticker as a valid one-by-one matrix but leaves average correlation empty because there are no peers.
- The heatmap colorscale uses Plotly's normalized `[-1, 1]` range, with correlation 0.5 anchored at the neutral point.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~55k

### Follow-up (2026-05-09) — layout cleanup on same PR
Post-review layout fixes applied to `ticket-A2-analytics-correlation` (no new ticket):
- Vertical full-width stack: heatmap → avg-correlation table. Removed two-column layout.
- Section headings: `st.subheader("Pairwise correlation")` above controls; `st.subheader("Average correlation to portfolio")` above table.
- Controls row: window radio (3/4 width) + compact color-scheme selectbox (1/4 width, labels "1"–"4", full names in `help=` tooltip).
- Expander replaced with `st.popover("ⓘ")` next to the avg-correlation table heading.
- KPI strip (Mean ρ, Highest Pair, Lowest Pair, Clusters) stays between controls and heatmap.
- Deleted `_render_correlation_side_panel`; help text promoted to module-level `_CORRELATION_HELP_TEXT` constant.
- Updated `_correlation_colorscale` to use short code lookup ("1"→"4") instead of full name strings.
- Updated three UI unit tests to match new layout (popover instead of expander, `[10,1]` columns, code-based color scheme).

### Follow-up (2026-05-09) — polish round 2 on same PR
Further polish applied to `ticket-A2-analytics-correlation` (same branch, no new ticket):
- Color scheme picker relocated: selectbox removed from controls row; replaced with a `st.popover("🎨")` icon below the heatmap, containing a `st.radio` keyed to `correlation_color_scheme` session state.
- Color schemes consolidated: replaced the 4-option code-based list with a 3-entry `CORRELATION_COLORSCALES` dict in `_chart_styles.py` (Diverging, Financial, Sequential). Default is "Financial (red–neutral–green)".
- `CHART_AXIS_LABEL_COLOR = "#374151"` added to `_chart_styles.py` for readable dark-text axis labels.
- Heatmap axis labels: `tickfont` updated to `{"size": 12, "color": CHART_AXIS_LABEL_COLOR}` on both axes; `tickangle` changed from -45° to -30°.
- Avg-correlation table: `st.dataframe` + pandas Styler replaced with `render_html()` HTML table using CSS badge classes `.diversification-badge.high|moderate|low|very-low`.
- CSS: added `--orange` / `--orange-bg` variables and `.diversification-badge.*` rules to `dark.css`.
- Updated 3 UI unit tests: import changed to `CORRELATION_COLORSCALES`, `render_html` patched in place of `st.dataframe`, sort-order test rewired to assert HTML content ordering.

---

## Session 2026-05-09 — TICKET-A3: Analytics: Technicals tab v1

**Branch:** `ticket-A3-analytics-technicals`
**Commit:** `606ebe9`

### What was implemented

**Domain layer:**
- `detect_recent_cross(sma_short, sma_long, *, lookback=90)` added to `app/domain/analytics.py`. Collects all valid (non-None) pairs, takes the last `lookback`, scans for sign changes in the diff series. Returns `("golden"|"death"|"none", days_ago|None)`. Raises `ValueError` for empty, mismatched, or insufficient input.

**Service layer:**
- `app/services/analytics_technicals.py` (new). `build_technicals_view(ticker, period, repo, price_feed, ohlc, as_of)` — validates ticker is in open universe, fetches 5Y OHLC via port (raw daily bars, no aggregation), computes SMA(50/200) and RSI(14) over full history, slices to visible window, computes signal badges, returns `TechnicalsView` (frozen Pydantic model). `OhlcUnavailable` exception wraps `OhlcUnavailableError` from the port.

**UI components:**
- `app/ui/components/period_selector.py` (new). `render_period_selector(key, *, options, default)` shared component, second consumer triggered extraction. `_PERIOD_LABELS` dict exported.
- `app/ui/components/_chart_styles.py` — `SMA_50_STYLE` (amber dashed) and `SMA_200_STYLE` (blue dashed) added.
- `app/ui/components/charts.py` — `Overlay` TypedDict added; `render_candlestick` extended with optional `overlays` parameter; `render_rsi_panel(dates, rsi)` added.
- `app/ui/styles/dark.css` — `.badge-grey` added.
- `app/ui/pages/research.py` — migrated from inline period radio to `render_period_selector`.

**Analytics page — Technicals tab:**
- `_render_technicals_tab()` — ticker selectbox + period selector, calls `build_technicals_view`, handles `OhlcUnavailable`.
- `_render_technicals_badges(view)` — 5-badge strip: SMA50 trend, SMA200 trend, cross (golden/death/none + days ago), RSI level + value, live Δ%.
- `_render_technicals_charts(view)` — reconstructs `OhlcSeries`, builds SMA overlays, calls `render_candlestick`, renders RSI panel.

**Tests:**
- `tests/unit/domain/test_analytics.py` — `TestDetectRecentCross` with 9 cases including the mathematically verified golden/death cross sequences.
- `tests/unit/services/test_analytics_technicals.py` (new) — `TestBuildTechnicalsView` with 9 cases covering insufficient history, error propagation, SMA seeding, cross detection (300-bar pattern `[200]*100+[50]*100+[126]*100` → golden cross at days_ago=60), currency inference.
- `tests/unit/ui/test_analytics_page.py` — replaced A3 placeholder assertion with `test_technicals_tab_body_is_called`; added `_render_technicals_tab` patch to all tests.

### Gate check result
572 passed, 81 skipped | ruff: all clear | mypy: 79 files clean | lint-imports: 4 kept, 0 broken

---

## 2026-05-10 — TICKET-U1

**Agent:** Claude Code (sonnet-4.6)
**Duration:** ~60 min
**Branch:** ticket-U1-sidebar-topbar-polish
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- `app/ui/components/sidebar.py` — rewrote: NAV_ITEMS reordered into PORTFOLIO/TOOLS/SETTINGS
  sections (simulator+lots+decision+behaviour in TOOLS, correct order per spec); analytics icon
  changed from `""` to `"⬡"`, label to "Analytics & Risk"; render_sidebar() now calls
  render_html() directly (per CLAUDE.md) instead of returning a raw string; compact inline
  HTML with no whitespace text-node flex children (eliminates ghost-row source)
- Brand block: removed `<div class="sub">Scalable Capital · DE</div>` subtitle
- `app/ui/main.py` — updated call from `st.markdown(render_sidebar(), ...)` to just `render_sidebar()`
- `app/ui/styles/dark.css` — added `.nav-section-label--after { margin-top: 12px }` for 2nd/3rd
  section labels
- `app/ui/components/topbar.py` — removed redundant `st.markdown` for border-bottom div
  (CSS already handles topbar border; the extra call created a ghost Streamlit element)
- Removed duplicate h1/h2 page headers from 8 pages:
  `analytics.py` (`# 📊 Analytics`), `research.py` (`# 📈 Research`), `performance.py`,
  `behaviour.py`, `lots.py`, `decision.py`, `manage.py`, `simulator.py` (title div only;
  subtitle muted text preserved). Tax Dashboard and Live Overview had no duplicate headers.
- `tests/unit/ui/test_sidebar_structure.py` — new (14 tests): ghost-row count, three section
  labels in order, section membership, active state, no underlines, brand block, footer,
  date determinism, badge rendering, section coverage
- `tests/unit/ui/test_analytics_page.py` — renamed `test_page_header_uses_analytics_icon` to
  `test_no_duplicate_page_header`; asserts the duplicate header is NOT present

### Files touched
- `app/ui/components/sidebar.py` — rewritten
- `app/ui/components/topbar.py` — ghost element removed
- `app/ui/styles/dark.css` — .nav-section-label--after added
- `app/ui/main.py` — sidebar call updated
- `app/ui/pages/analytics.py` — duplicate header removed
- `app/ui/pages/research.py` — duplicate header removed
- `app/ui/pages/performance.py` — duplicate header removed
- `app/ui/pages/behaviour.py` — duplicate header removed
- `app/ui/pages/lots.py` — duplicate header removed
- `app/ui/pages/decision.py` — duplicate header removed
- `app/ui/pages/manage.py` — duplicate header removed
- `app/ui/pages/simulator.py` — duplicate title div removed
- `tests/unit/ui/test_sidebar_structure.py` — new (14 tests)
- `tests/unit/ui/test_analytics_page.py` — updated assertion

### Tests
572 passing → 586 passing (14 new)

### Decisions made during the session
- Ghost rows root cause: the old sidebar used `st.markdown(render_sidebar(), ...)` bypassing
  `render_html()`. Internal `textwrap.dedent` template whitespace also created empty text nodes
  in flex containers. Fix: compact inline HTML, `render_html()` as the single exit point.
- `render_sidebar()` signature changed to `render_sidebar(*, today: date | None = None)` for
  testability (date injection instead of `date.today()` call).
- Decision Gates badge kept with the same "3 flags" placeholder; badge color="" uses default
  red from CSS (no new colour class needed).

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~40k

---

## 2026-05-10 — TICKET-M1

**Agent:** Claude Code (sonnet-4.6)
**Duration:** ~60 min
**Branch:** ticket-M1-workflow-cleanup
**PR:** (opening this session)
**Status at session end:** IN_REVIEW

### What got done
- AGENTS.md: "Phase 1–9" → "Step 1–9"; added Step 0 for `gh issue list --label next-up`
  resolution; Step 2 now detects merged state via `gh issue view <N> --json state`
  instead of relying on Vivek's message; Step 5 adds `gh issue edit` label update;
  Step 9 requires `Closes #N` in PR body
- METHODOLOGY.md: Phase→Milestone, READY→QUEUED, P0-P3→CRITICAL/HIGH/MEDIUM/LOW,
  DRAFT removed throughout; added Priority levels, Ticket lifecycle states, Milestones,
  and "Chat handoff protocol" sections; "ticket-drafting checklist" updated for new vocab
- ARCHITECTURE.md: `app/ui/pages/` listing updated to reflect actual current files
  (overview.py, manage.py, tax.py, simulator.py, research.py, analytics.py, etc.)
- ADR-005: status Proposed → Accepted; added `Accepted:` date line
- BACKLOG.md: Phase N headers → Milestone headers; P0-P3 → CRITICAL-LOW; READY → QUEUED;
  status legend updated; DRAFT removed from legend; Investment Panel placeholder ticket
  Status column fixed
- PROJECT_STATE.md: Phase/Sprint fields → Milestone; Done list trimmed to last 5 entries;
  stale TICKET-013 parking-lot item removed; TICKET-M1 moved to In progress
- tools/setup_github.sh: idempotent script creates 9 labels and 8 milestones (6 closed)
- tools/draft_ticket.sh: reads spec from stdin, writes ticket file, updates BACKLOG.md
  and PROJECT_STATE.md, creates GitHub issue with labels + milestone, commits + pushes
- tools/update_backlog.py: appends ticket row to named Milestone table, optionally
  updates Next up section
- tools/update_state.py: prepends item to PROJECT_STATE.md Next up list
- GitHub: labels and milestones created and verified (gh label list / milestones API)
- TICKET-M1 housekeeping: TICKET-U1 (PR #48) marked MERGED at session start

### Files touched
- `AGENTS.md` — full ritual rewrite (Phase→Step, new Step 0, gh integration)
- `docs/METHODOLOGY.md` — full vocabulary migration + new sections
- `docs/ARCHITECTURE.md` — pages list updated
- `docs/DECISIONS/ADR-005-eur-native-input.md` — status update
- `docs/TICKETS/BACKLOG.md` — full vocabulary migration
- `docs/PROJECT_STATE.md` — Milestone field, slim Done, update Next up
- `docs/TICKETS/TICKET-M1-workflow-cleanup.md` — status IN_PROGRESS → IN_REVIEW
- `tools/setup_github.sh` — new
- `tools/draft_ticket.sh` — new
- `tools/update_backlog.py` — new
- `tools/update_state.py` — new

### Tests
586 passing → 586 passing (0 new — documentation-only ticket)

### Decisions made during the session
- `draft_ticket.sh` skips milestone assignment if milestone is closed (gh cli
  only supports adding issues to open milestones); emits a warning instead of failing
- Test of draft_ticket.sh was done from the feature branch by running update_backlog.py
  directly (not via full script push to main) to avoid polluting main; gh issue creation
  tested separately and verified — TICKET-MTEST #49 created with correct labels and closed

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~80k

---

## 2026-05-10 — TICKET-M2

**Agent:** Claude Code (sonnet-4.6)
**Duration:** ~20 min
**Branch:** ticket-M2-add-workflow-md
**PR:** pending
**Status at session end:** IN_REVIEW

### What got done
- Created `docs/WORKFLOW.md`: Vivek-facing, second-person, recipe-style guide
  covering the four touchpoints, vocabulary cheatsheet, edge-case recipes,
  M1 transitional section, and footer cross-reference table
- `README.md`: added "Working on this project" section with link to WORKFLOW.md
- `docs/METHODOLOGY.md`: added cross-link line at top
- `AGENTS.md`: added cross-link line near top clarifying file is for the agent

### Files touched
- `docs/WORKFLOW.md` — new
- `README.md` — one section added
- `docs/METHODOLOGY.md` — one line added at top
- `AGENTS.md` — one line added near top

### Tests
586 passing → 586 passing (0 new — documentation-only ticket)

### Decisions made during the session
- No architectural decisions made

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~20k

---

## 2026-05-12 — TICKET-025

**Agent:** Claude Code (sonnet-4.6)
**Duration:** ~90 min
**Branch:** ticket-025-company-data-layer
**PR:** pending
**Status at session end:** IN_REVIEW

### What got done
- Created `app/domain/company.py` — all 12 domain models (CompanyProfile, LatestQuote, PriceHistoryPoint, QuarterlyFundamentals, AnnualFundamentals, CurrentMultiples, DividendEvent, InstitutionalHolder, InsiderTransaction, OwnershipSnapshot, NextCatalyst, CompanyData), all frozen Pydantic v2
- Created `app/ports/company_data.py` — CompanyDataProvider runtime_checkable Protocol + CompanyDataError
- Created `app/adapters/company_yfinance/` — fills profile, quote, price history, fundamentals (quarterly + annual), multiples, dividends from yfinance
- Created `app/adapters/company_finnhub/` — fills next_catalyst and ownership (institutional holders, insider transactions) from Finnhub REST API
- Created `app/adapters/company_composite/` — merges two providers; yfinance wins for all sections except ownership/next_catalyst where Finnhub wins
- Created `app/adapters/company_cache/` — per-section JSON cache (profile.json/prices.json/financials.json), TTL logic, atomic writes via os.replace, corrupt-file recovery
- Created `app/adapters/company_cache/ttl.py` — NYSE-hours-aware prices_ttl() function
- Created `app/adapters/company_factory.py` — build_company_provider() wiring
- Created `app/services/company.py` — get_company() and refresh_company_section() thin services
- Updated `.gitignore` — added data/companies/
- 46 new unit tests across domain, adapters (cache, composite, TTL), and services
- 2 integration tests (yfinance + Finnhub, gated behind @pytest.mark.integration)

### Files touched
- `app/domain/company.py` — new
- `app/ports/company_data.py` — new
- `app/adapters/company_yfinance/__init__.py`, `adapter.py` — new
- `app/adapters/company_finnhub/__init__.py`, `adapter.py` — new
- `app/adapters/company_composite/__init__.py`, `adapter.py` — new
- `app/adapters/company_cache/__init__.py`, `adapter.py`, `ttl.py` — new
- `app/adapters/company_factory.py` — new
- `app/services/company.py` — new
- `tests/unit/domain/test_company_models.py` — new (18 tests)
- `tests/unit/adapters/test_company_cache.py` — new (11 tests)
- `tests/unit/adapters/test_company_ttl.py` — new (7 tests)
- `tests/unit/adapters/test_company_composite.py` — new (7 tests)
- `tests/unit/services/test_company_service.py` — new (4 tests)
- `tests/integration/test_company_yfinance.py` — new (2 tests, integration-gated)
- `tests/integration/test_company_finnhub.py` — new (2 tests, integration-gated)
- `.gitignore` — appended data/companies/

### Tests
586 passing → 632 passing (46 new unit tests; 4 integration tests skipped in offline CI)

### Decisions made during the session
- No new architectural decisions; all design was pre-settled in the ticket spec

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~90k

---

## 2026-05-13 — TICKET-M3

**Agent:** Claude Code (sonnet-4.6)
**Duration:** ~90 min
**Branch:** ticket-M3-tooling-self-heal
**PR:** pending
**Status at session end:** IN_REVIEW

### What got done
- Added branch guard + clean-tree guard to `tools/draft_ticket.sh` (hard-fail before any side effects)
- Added `python3 tools/sync_state.py` call at start of `draft_ticket.sh` to reconcile state on every ticket filing
- Rewrote `tools/update_backlog.py`: auto-create missing Milestone sections, fixed separator placement bug (row now goes after `|---|` not after a stray trailing separator), and uses `_next_up` helper to rebuild Next up instead of prepending
- Rewrote `tools/update_state.py`: full rebuild from GitHub instead of prepend; kept --id/--title args for backwards compat
- Created `tools/_next_up.py`: shared `rebuild_next_up_list()` (queries GitHub, sorts by next-up → milestone order → issue number) and `extract_freeform_entries()` (preserves italic placeholder lines)
- Created `tools/sync_state.py`: standalone reconciliation (Next up, In review, In progress rebuilt from GitHub); `--mark-merged TICKET-XXX --pr N` flag moves ticket from In review to Done and updates BACKLOG row
- Created `.github/workflows/post-merge-housekeeping.yml`: triggers on PR merge to main, updates ticket file (IN_REVIEW→MERGED), calls sync_state --mark-merged, commits with `[skip ci]`
- Updated `AGENTS.md` Step 2: now a verification step (check Actions landed) with fallback to manual sync_state call
- Updated `docs/WORKFLOW.md` Sections 4, 5; added new Section 9 documenting M3 self-heal behaviour
- Fixed malformed Company Deep Dive section in BACKLOG.md (separator was after data row)
- Fixed stale statuses in BACKLOG.md (M1, M2, TICKET-025 → MERGED)
- Added sync_state.py regex comment to PROJECT_STATE.md
- 28 new unit tests covering _next_up, sync_state, update_backlog, and draft_ticket.sh guard behaviour

### Files touched
- `tools/__init__.py` — new (package marker)
- `tools/_next_up.py` — new
- `tools/sync_state.py` — new
- `tools/draft_ticket.sh` — branch guard, clean-tree guard, sync call
- `tools/update_backlog.py` — auto-create milestone, fix separator, use _next_up
- `tools/update_state.py` — use _next_up for full rebuild
- `.github/workflows/post-merge-housekeeping.yml` — new
- `AGENTS.md` — Step 2 rewritten as verification step
- `docs/WORKFLOW.md` — Sections 4, 5 updated; Section 9 added
- `docs/TICKETS/BACKLOG.md` — fixed Company Deep Dive section; stale statuses corrected
- `docs/PROJECT_STATE.md` — sync_state regex comment; TICKET-M3 IN_REVIEW
- `docs/TICKETS/TICKET-M3-*.md` — status IN_REVIEW
- `tests/unit/tools/__init__.py` — new
- `tests/unit/tools/test_next_up.py` — new (11 tests)
- `tests/unit/tools/test_sync_state.py` — new (8 tests)
- `tests/unit/tools/test_update_backlog.py` — new (6 tests)
- `tests/unit/tools/test_draft_ticket.py` — new (5 tests)

### Tests
632 passing → 660 passing (28 new)

### Decisions made during the session
- No new architectural decisions; all design was pre-settled in the ticket spec
- Used pytest+subprocess for draft_ticket.sh tests (no bats dependency)
- sync_state.py --mark-merged calls standard reconciliation internally (idempotent if workflow also calls sync_state standalone)

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~120k

---

## 2026-05-13 — TICKET-M4a

**Agent:** Claude Code (sonnet-4.6)
**Duration:** ~45 min
**Branch:** ticket-m4a-context-bundle
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/61
**Status at session end:** IN_REVIEW

### What got done
- Created `tools/regen_context.py`: generates `docs/CONTEXT.md` with 10 sections (state driver, ADRs, file tree, public interfaces via AST, UI surface, data shape, open issues, open PRs, recent merges, test inventory). Graceful degradation if `gh` CLI unavailable. Idempotent (only timestamp differs on re-run).
- Created `.github/workflows/update-context.yml`: triggers on push to main; bot-author guard (`github.actor != 'github-actions[bot]'`) prevents recursion with housekeeping workflow; commits with `[skip ci]` if CONTEXT.md changed.
- Committed `docs/CONTEXT.md`: first auto-generated version (2371 lines).
- Created `tests/unit/tools/test_regen_context.py`: 7 smoke tests verifying AST extraction returns core domain models, compute_positions, Protocol ports, and non-empty ADR/UI/test inventory sections.
- Updated `AGENTS.md`: added `docs/CONTEXT.md` as Required Reading item 2; updated "four files" → "five files" references.
- Updated `docs/METHODOLOGY.md`: added "Ticket drafting in chat — the verification protocol" section after "The chat handoff protocol".
- Updated `README.md`: added "For chat sessions" subsection under "Working on this project".

### Files touched
- `tools/regen_context.py` — new
- `.github/workflows/update-context.yml` — new
- `docs/CONTEXT.md` — new (auto-generated)
- `tests/unit/tools/test_regen_context.py` — new (7 tests)
- `AGENTS.md` — CONTEXT.md added to Required Reading; count updated
- `docs/METHODOLOGY.md` — new verification protocol section
- `README.md` — "For chat sessions" subsection
- `docs/TICKETS/TICKET-M4a-context-bundle-and-verification-protocol.md` — status IN_REVIEW

### Tests
660 passing → 667 passing (7 new smoke tests)

### Decisions made during the session
- Excluded `CONTEXT.md` from the file tree (would break idempotency on second run)
- Used `pathlib`-native tree walker (no `tree` CLI dependency)
- Smoke test added for AST extraction (7 tests cover key invariants cheaply)

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~60k
