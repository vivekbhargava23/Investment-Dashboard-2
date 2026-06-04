# TICKET-RD0 — Navigation & focus spine (focus ticker + retire Research)

**Priority:** HIGH
**Milestone:** Dashboard Redesign
**Recommended model:** Sonnet — cohesive changes in the nav layer; clear criteria.
**Estimated session length:** 2 hr
**Drafted by:** Vivek + Claude (chat 2026-06-04)
**Depends on:** —
**Consolidates:** old RD0 (focus context) + old RD2 (retire Research). Both live in `main.py` / nav, so they are one coherent session. (Router-error surfacing is NOT here — TICKET-ROBUST-1 already shipped that.)

> **After this ticket merges, the app has one persistent "focus ticker" and the redundant Research tab is gone.** This is the navigation spine for the two-surface redesign.

---

## Problem

Two nav-layer issues:

1. **No shared focus.** Every page keeps its own ticker state (`overview_chart_ticker`, the Company search, etc.). Selecting Micron in one place carries nowhere; each navigation is a full rerun that loses context.
2. **Research is redundant.** `app/ui/pages/research.py` is just "chart any ticker" — a strict subset of the Company page. It adds a sidebar entry and another island.

## Acceptance criteria

### Focus ticker

- [ ] New `app/ui/focus.py`: `get_focus_ticker()`, `set_focus_ticker(symbol)` (session state mirrored to `?ticker=`), and a pure `resolve_initial_focus(session, query, owned)` (query > session > first owned > None), unit-tested.
- [ ] `main.py` syncs `?ticker=` into session state alongside the existing `?page=` sync.
- [ ] `topbar.py` renders a focus selector (reuse `render_ticker_searchbox` + `get_ticker_resolver`) that calls `set_focus_ticker`.
- [ ] Company page uses `get_focus_ticker()` as its default and writes the global focus on selection; overview's "⚡ Sim" link and position-chart selection set the focus.
- [ ] Focus persists across page navigation.

### Retire Research

- [ ] Remove the `research` entry from `NAV_ITEMS` and fix `_SECTIONS` index ranges (the list shifts — recompute so PORTFOLIO/TOOLS/SETTINGS stay correct).
- [ ] Delete `app/ui/pages/research.py`; route legacy `?page=research` → `company`.
- [ ] Grep and update all `page=research` references (sim/watchlist handoffs). Confirm Company works for a non-owned ticker.

## Files likely touched

- `app/ui/focus.py` (new), `app/ui/components/topbar.py`, `app/ui/main.py`,
  `app/ui/components/sidebar.py`, `app/ui/pages/company.py`, `app/ui/pages/overview.py`,
  delete `app/ui/pages/research.py`, `tests/unit/ui/test_focus.py` (new).

## Out of scope

- ❌ Unified ticker searchbox on every picker — that's RD3.
- ❌ Router error surfacing / HTML escaping — already shipped by TICKET-ROBUST-1.
- ❌ The full two-surface restructure / Portfolio Home page — later.

## Tests

- [ ] `resolve_initial_focus` precedence; focus query-param round-trip.
- [ ] Sidebar `_SECTIONS` ranges cover all items, no gap/overlap; no `research` id remains.
- [ ] `pytest && ruff check . && mypy app/ && lint-imports` all pass.
