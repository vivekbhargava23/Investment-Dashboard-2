# TICKET-RD2 — Sortable positions table

**Status:** DRAFT
**Priority:** HIGH
**Milestone:** Dashboard Redesign
**Recommended model:** Sonnet — additive feature on an existing component + a pure sort function.
**Estimated session length:** 1 – 1.5 hr
**Drafted by:** Vivek + Claude (chat 2026-06-04)
**Depends on:** RD1 (the `positions_table` component must exist first)

> **After this ticket merges, the positions table sorts by any column.** Clicking a header sorts asc/desc (via `?sort=&dir=` query params, reusing RD0's pattern) while keeping the component's styling.

---

## Problem

The positions table (a component after RD1) is sorted once, by EUR value descending, with no interactivity. The user can't reorder by gain, weight, name, etc.

## Acceptance criteria

- [ ] A pure `sort_positions(positions, sort_key, direction) -> list[LivePosition]` in `positions_table.py`. Keys: `ticker`, `name`, `price`, `shares`, `cost`, `value`, `gain`, `weight`, `trend`.
- [ ] Column headers render as links toggling `?sort=<key>&dir=<asc|desc>`; clicking the active column flips direction; active column shows ▲/▼.
- [ ] Default (no params) = value descending (current behaviour) — regression guard.
- [ ] Stale rows (missing live price/value/gain) always sort to the bottom in both directions, never displacing real data.

## Files likely touched

- `app/ui/components/positions_table.py` (add sort), `app/ui/pages/overview.py` (read sort params),
  `tests/unit/ui/test_positions_table.py` (sort cases).

## Out of scope

- ❌ Pagination/virtualisation (≈13 rows).
- ❌ Inline tranche expansion — RD6.
- ❌ Moving the table to a Portfolio Home page — later.

## Tests

- [ ] `sort_positions` correct for each key, both directions; stale/None always last; default equals value-desc.
- [ ] `pytest && ruff check . && mypy app/ && lint-imports` all pass.
