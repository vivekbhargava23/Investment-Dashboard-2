# TICKET-CSV-18 — Inline "Ignore" action in the Import Workbench

**Priority:** MEDIUM
**Status:** IN_PROGRESS
**Estimated session length:** 1 hr
**Recommended model:** Sonnet — UI wiring on one page, reuses existing repo + status plumbing.
**Drafted by:** Vivek + Claude Code (session 2026-06-05)
**Implemented by:** TBD
**Milestone:** Investment Panel

---

## Problem

To mark an ISIN as `ignored`, the user must leave the Import Workbench, go to the Mappings
page, find the row, and click Ignore — then come back and re-import. During an actual import,
the natural moment to say "I don't want this one, ever" is right there in the manual-review
panel where the unmapped ISIN is staring at them. Today that panel only offers Map (search +
Save); there is no inline Ignore.

## Solution

Add an **Ignore** button next to **Save** for each ISIN in the manual-review panel
(`_render_autoresolve_panel`, the "Map ISINs manually" expander in
`app/ui/pages/import_workbench.py`). Clicking it flips that ISIN's map entry to `status:
"ignored"` (creating the entry if needed), then re-plans so the row drops out of the view
(ignored rows are already silent after TICKET-CSV-14).

### Decisions already made — do not re-litigate

- Ignore writes through the same `IsinMapRepository.save` path the Mappings page uses; no new
  persistence logic.
- After Ignore, clear the cached plan (`st.session_state.pop(_KEY_PLAN, ...)`) and rerun so
  the workbench re-plans and the now-ignored row disappears (consistent with how manual Save
  already behaves).
- An ISIN ignored here is identical in every way to one ignored from the Mappings page —
  same `IsinMapping(status="ignored", ticker=None)`. Restore still lives on the Mappings page.

### Execution

1. In the manual-review row layout, add an **Ignore** button column alongside **Save**.
2. On click: build the entry (reuse a small helper or `IsinMapping(...status="ignored"...)`),
   `isin_repo.save(...)`, set a success feedback message, pop the plan, `st.rerun()`.
3. Tests in `tests/unit/ui/test_import_workbench.py` (or the mappings test if the helper is
   shared): clicking Ignore persists `status == "ignored"` for that ISIN.
4. Gate.

## Acceptance criteria

- [ ] Each unmapped ISIN in the workbench manual-review panel has an Ignore button.
- [ ] Clicking it persists the ISIN as `ignored` and the row disappears from the plan.
- [ ] No regression to the existing Map/Save flow.
- [ ] `pytest`, `ruff check .`, `mypy app/`, `lint-imports` clean.

## Files likely touched

- `app/ui/pages/import_workbench.py`, `tests/unit/ui/test_import_workbench.py`

## Out of scope

- Auto-suggesting which ISINs to ignore (TICKET-CSV-19).
- Bulk ignore. One row at a time.

## Notes / assumptions

- Depends on TICKET-CSV-14 (ignored status + silent workbench) being merged.
- Assumes the manual-review panel still uses `render_isin_mapper_row` + a Save button; confirm
  the layout columns before inserting the new button.
