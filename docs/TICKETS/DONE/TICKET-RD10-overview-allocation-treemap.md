# TICKET-RD10 — Allocation treemap on Overview (period-selectable)

**Priority:** HIGH
**Status:** IN_PROGRESS
**Milestone:** Dashboard Redesign
**Recommended model:** Sonnet — one new UI component over existing data + a Plotly figure; logic is thin once RD9 lands.
**Estimated session length:** 1.5 – 2 hr
**Drafted by:** Vivek + Claude (Cowork session 2026-06-05)
**Depends on:** RD9 (returns-by-period service) for the colour metric; live positions already available on Overview.

> **After this ticket merges, the Overview shows an allocation treemap — tiles sized by EUR value, coloured by return over a selectable period (1D / 7D / 30D / YTD).** Mirrors the Claude Design "Allocation Treemap" card.

---

## Problem

The Overview presents holdings only as a table. The redesign adds a treemap for instant
"where is my money and what's moving" reading: **tile size = live EUR value**, **tile colour =
return over the chosen period**. Vivek specifically asked that the colour period be selectable,
not hard-wired to 30D, and that switching it be instant (no recompute — RD9 caches all windows).

## Acceptance criteria

- [ ] A new `app/ui/components/treemap.py` rendering a Plotly treemap from live positions:
      one tile per held ticker, `value = live_value_eur` (EUR), label = `TICKER` with the
      company name as secondary text.
- [ ] Tile colour = the selected window's return from RD9's returns map, on a **diverging
      green↔red scale centred at 0** with a **fixed symmetric clamp** (cmin/cmax = ±14% by
      default, a module constant) so one outlier doesn't wash out the scale. Reuse the
      existing chart colour tokens (`chart_theme` / `_chart_styles`) rather than inventing
      hex values.
- [ ] A period selector drives the colour, rendered via the existing
      `app/ui/components/period_selector.py::render_period_selector` restricted to
      `[1D, 7D, 30D, YTD]`, defaulting to 30D. Changing it re-colours from the cached returns
      map with **no OHLC refetch and no return recompute**.
- [ ] Hover shows: ticker, company name, EUR value, weight %, and the selected-period return.
- [ ] Clicking a tile selects/opens that position consistent with how the positions table row
      click behaves today (reuse the existing mechanism; if none exists for "open position",
      hover-only is acceptable and a follow-up is noted — do not invent a drawer here).
- [ ] Positions with `None` return for the selected window render in a neutral colour (not
      green, not red) and say "n/a" in the hover, never a fabricated 0%.
- [ ] Stale positions (no `live_value_eur`) are excluded from the treemap (can't size them),
      consistent with how the positions table treats stale rows.

## Files likely touched

- `app/ui/components/treemap.py` (new),
- `app/ui/pages/overview.py` (period selector + cached returns map + render call),
- `app/ui/styles/dark.css` if any card chrome is needed,
- `tests/unit/ui/test_treemap.py` (new — figure data assembly, clamp, n/a handling).

## Out of scope

- ❌ The Position↔Sector toggle from the mock (treemap grouped by sector) — file as a
      follow-up (RD-later) once the position view is in.
- ❌ Performance heatmap — RD11 (shares RD9's returns map).
- ❌ Computing returns — owned by RD9.
- ❌ Custom-N period — RD9 ships the fixed window set.

## Test cases

1. Given three positions with known EUR values, the figure's `values` match `live_value_eur`
   and tile order/sizes follow value.
2. Given a position with +30% return and clamp ±14%, its colour maps to the scale max (fully
   green), not beyond; a −30% maps to the scale min (fully red).
3. A position with `None` 7D return renders neutral and hover text shows "n/a", with no `0%`.
4. A stale position (no live value) is absent from the figure.
5. `pytest && ruff check . && mypy app/ && lint-imports` all pass.

## Notes

- **Verified (2026-06-05):** `render_period_selector(key, *, options, default)` exists and
  takes a `ChartPeriod` option list + a label default ("30D"-style) — reuse it; do not build a
  new selector. `LivePosition` exposes `live_value_eur: Money | None`, `position.ticker`, and an
  `is_stale`-style check (`live_price_native is None or live_value_eur is None`). Company names
  come from the same `name_lookup` the positions table uses (`get_isin_map_repo()` wiring).
- Plotly is already a project dependency (candlesticks via `render_candlestick`); use
  `plotly.graph_objects.Treemap`. Follow `chart_theme.py` for light-theme consistency.
- The colour metric is a **native-price % change** (RD9) — currency-agnostic, so no FX needed
  for colour. Size is EUR (`live_value_eur`).
- UI ticket → AGENTS.md Visual Verification (before/after screenshots) before the PR.
