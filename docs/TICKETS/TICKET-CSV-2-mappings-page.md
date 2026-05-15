# TICKET-CSV-2 — Mappings page (ISIN → ticker UI)

**Status:** IN_PROGRESS
**Priority:** HIGH
**Estimated session length:** 1 hr
**Drafted by:** Vivek + Claude (chat session 2026-05-15)
**Implemented by:** TBD
**Milestone:** UI core

## Problem

After TICKET-CSV-1 lands, ISIN → ticker mappings live in `data/isin_map.json`. The CLI importer surfaces unmapped ISINs in its summary, but Vivek currently has to hand-edit the JSON to resolve them, then re-run the importer. This is tolerable for one round but painful as new instruments show up in future CSV exports.

This ticket adds a Streamlit "Mappings" page that lets Vivek resolve mappings in the browser. After saving a mapping, the next CSV import will pick up the previously-quarantined rows.

## Scope

A new page `app/ui/pages/mappings.py` registered in the sidebar (`app/ui/components/sidebar.py`) under a suitable group. Page reads from and writes to `data/isin_map.json` via the existing IsinMapRepository (added in CSV-1).

## UI layout

Single page, top-down:

1. **Header strip**: counts — "13 mapped · 2 unmapped" and a refresh button that reloads from disk (useful if Vivek just ran the importer in another terminal).

2. **Unmapped section** (only shown when there's at least one unmapped entry). Highlighted (use the existing warning/amber accent from `dark.css`). For each unmapped ISIN, one row:
   - ISIN (monospace, read-only)
   - Name from CSV (read-only, truncated with tooltip on hover for long names)
   - Ticker input — `st.text_input`, placeholder "e.g. NVDA, 5631.T"
   - "Save" button — on click: validates the ticker against the ticker resolver (`app/ports/ticker_resolver.py` via `get_ticker_resolver()` from wiring), flips status to `mapped`, writes the file, reruns the page.

3. **Mapped section** — a table (use `st.dataframe` or a hand-rolled grid, whichever fits the dark theme). Columns:
   - ISIN
   - Name
   - Ticker
   - Last seen in CSV
   - Edit button (per row)
   - Delete button (per row, with confirm)

   "Edit" turns the ticker cell into an input with Save/Cancel. "Delete" removes the entry from `isin_map.json` entirely (use case: Vivek mapped the wrong thing and wants to start over).

4. **Bottom section** — a small box explaining: "ISINs are auto-added to this page when you run `tools/import_scalable_csv.py`. Re-run the importer after mapping new ISINs to pull in their transactions."

## Validation rules on the ticker input

- Non-empty after strip.
- Must match the regex our existing tickers use (uppercase letters, digits, dot, dash — same shape `app/domain/models.py`'s `ticker_must_be_uppercase` accepts).
- The page calls `ticker_resolver.lookup(ticker)` (a synchronous lookup, not the autocomplete-style `resolve()`). If lookup returns a hit, save proceeds and a green confirmation shows the resolved name + exchange. If lookup returns None, show a warning ("Ticker not recognized by yfinance — saved anyway, but live prices may not work") and save anyway. **Do not block save on resolver failure** — the resolver can be offline or rate-limited and Vivek still needs to be able to map.

## Sidebar entry

Add to `app/ui/components/sidebar.py`. Sensible group: under "Manage" alongside the existing Manage Portfolio entry, or as a new top-level "Mappings" entry. Implementation agent picks based on existing sidebar structure — both are reasonable.

## Acceptance criteria

- [ ] New page `app/ui/pages/mappings.py` exists and is reachable from the sidebar.
- [ ] Page renders correctly when `data/isin_map.json` is missing (empty state with explanation).
- [ ] Page renders correctly when there are unmapped entries (highlighted section, save flow works).
- [ ] Page renders correctly with no unmapped entries (unmapped section is hidden, not shown empty).
- [ ] Saving a mapping writes `data/isin_map.json` and updates the UI on rerun.
- [ ] Editing an existing mapping (changing the ticker) writes the new value.
- [ ] Deleting a mapping removes its entry from `data/isin_map.json` after confirmation.
- [ ] Ticker validation rejects empty strings and obviously-malformed inputs (lowercase, special chars beyond `.` and `-`).
- [ ] Ticker resolver lookup is attempted but not required — page works when offline.
- [ ] Concurrent writes are tolerated: if Vivek edits a mapping while the importer is also running, the last write wins and the file remains valid JSON (the existing IsinMapRepository handles atomic writes per CSV-1).
- [ ] Tests pass: `pytest tests/unit/test_mappings_page.py` (Streamlit page tests use the same pattern as existing page tests — check for one if there's a precedent in `tests/unit/`, otherwise smoke-test the page module imports cleanly and its main render function is callable).
- [ ] Lints pass: `ruff check . && mypy app/ && lint-imports`

## Files likely touched

- `app/ui/pages/mappings.py` (new)
- `app/ui/components/sidebar.py` (add entry)
- `app/ui/main.py` (register page in the navigation map)
- `app/ui/wiring.py` (add `get_isin_map_repo()` if not already there from CSV-1 — depending on what CSV-1 wired up)
- `tests/unit/test_mappings_page.py` (new) — light smoke tests + validation logic test
- `app/ui/CLAUDE.md` (update if it lists pages)

## Out of scope

- **Bulk-edit / CSV import of mappings.** Single-row UI only.
- **Auto-resolve via yfinance ISIN lookup.** Manual entry. (Could be added later as a "Suggest" button per row.)
- **A separate "deleted/archived ISINs" history.** Delete is hard delete.
- **Re-running the importer from this page.** Vivek runs the CLI when he's ready. The page is mapping-only.
- **Showing per-ISIN transaction counts.** Nice-to-have but adds DB scan; defer.

## Test cases

1. Empty `isin_map.json` → page renders with explanation, no crash.
2. 3 mapped + 2 unmapped → header shows correct counts, unmapped section shows 2 rows, mapped table shows 3.
3. Type ticker into unmapped row, click Save → file written, entry flips to mapped, row moves from unmapped section to mapped table on rerun.
4. Click Edit on mapped row, change ticker, Save → file updated.
5. Click Delete on mapped row, confirm → entry removed.
6. Ticker resolver returns None → save still proceeds with a warning visible.
7. Ticker resolver raises (network down) → save still proceeds; exception is caught and reported as warning, not surfaced as an error.

## Notes

### Why this is a separate ticket from CSV-1

CSV-1 is import + data model + CLI. CSV-2 is UI. Mixing them violates "one logical change per PR" — they touch entirely separate layers and have separate failure modes. Doing them separately also means Vivek can use the CSV-1 importer the moment it merges, even before the UI exists (hand-edit JSON for the first run).

### Streamlit page module conventions

Follow the existing `app/ui/pages/*.py` pattern. Each page exposes `def render() -> None`. Wiring is fetched at the top of `render()` via `app/ui/wiring.py` getters (so tests can swap implementations). No I/O in module top-level code.

### Visual consistency

Use existing components (`metric_card` for counts, badge styles for status, `dark.css` accent colors). Do not introduce new colors or fonts. If a layout doesn't fit the existing component set, prefer plain `st.dataframe` + `st.text_input` over inventing a new component.
