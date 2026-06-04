# TICKET-RD1 — Overview & Tax HTML overhaul (components, drop thesis columns)

**Status:** DRAFT
**Priority:** HIGH
**Milestone:** Dashboard Redesign
**Recommended model:** Sonnet — cohesive refactor of two pages' HTML into reusable components.
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-06-04)
**Depends on:** —
**Consolidates:** TICKET-C6 (#111, inline-HTML cards → CSS components) + the redesign decision to remove the thesis/horizon columns. (HTML-escaping is NOT new work here — TICKET-ROBUST-1 already added it; this ticket must *preserve* it when moving HTML into components.)

> **After this ticket merges, Live Overview and Tax render through reusable CSS-class components instead of inline-styled f-strings — and the (now data-driven but unwanted) thesis/horizon columns are gone from the table.** This is also where the `positions_table` component is born, which RD2 (sorting) and RD6 (tranche expansion) build on.

---

## Problem

`overview.py` and `tax.py` build KPI cards and the positions table with big `render_html(f"""<div style="…">""")` blocks: inline CSS that bypasses `dark.css` and resists reuse (the same metric-card shape exists in both pages with subtly different inline styles). Separately, the thesis/horizon columns (now backed by `thesis_map` data after TICKET-THESIS-1) are not wanted on the overview.

## Acceptance criteria

### Componentize (was C6)

- [ ] Extend `app/ui/components/metric_card.py` to cover both pages' KPI tile shapes: `render_metric_card(*, label, value, sub_value=None, sub_color="default", size="md")`, single template, classes from `dark.css`.
- [ ] New `app/ui/components/positions_table.py` housing the table currently inlined in `overview.py::_build_positions_table_html` (accepts `live_positions`, `summary`, `trend_data`, `name_lookup`).
- [ ] Move styles into `dark.css` (`.metric-card[.sm/.lg]`, `.metric-label/value/sub[.green/.red/.grey]`, `.positions-table …`). No `style="…"` inline attributes remain in `overview.py` or `tax.py` (grep clean).
- [ ] Overview KPI tiles + tax tiles call `render_metric_card`; overview table calls the component.
- [ ] **Preserve the HTML-escaping ROBUST-1 added** — the new `positions_table` component must keep escaping data-derived strings (company `name`, `ticker`) via `html.escape`. Do not regress to raw interpolation.

### Drop thesis/horizon columns (redesign decision)

- [ ] The new positions_table component does **not** render the Thesis or Horizon columns, the thesis-pill row, or the "Thesis Status" KPI card. Remove the now-unused thesis rendering from overview.
- [ ] **Keep** the underlying `thesis_map` data layer and `get_thesis_repo` wiring intact (only the overview presentation is removed) — a future surface may use it.

## Files likely touched

- `app/ui/components/metric_card.py`, `app/ui/components/positions_table.py` (new),
  `app/ui/pages/overview.py`, `app/ui/pages/tax.py`, `app/ui/styles/dark.css`,
  `tests/unit/ui/test_positions_table.py` (new), metric-card tests.

## Out of scope

- ❌ Sortable columns — RD2 (adds sorting to this component).
- ❌ Inline tranche expansion — RD6 (builds on this component).
- ❌ Router error surfacing / introducing escaping — already shipped by ROBUST-1.
- ❌ Deleting the `thesis_map` data layer or `render_thesis_badge` component.
- ❌ Componentizing analytics-tab HTML — touched by RD4's split if needed.

## Tests

- [ ] Regression: a company name containing `<b>&"` still renders as literal text in the table (escaping preserved through componentization).
- [ ] Table HTML no longer contains "Thesis"/"Horizon" headers.
- [ ] `metric_card` renders both tile shapes; no inline `style=` left in overview/tax (grep test).
- [ ] `pytest && ruff check . && mypy app/ && lint-imports` all pass.
