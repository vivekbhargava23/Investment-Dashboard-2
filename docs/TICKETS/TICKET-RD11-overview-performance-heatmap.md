# TICKET-RD11 — Performance heatmap on Overview

**Priority:** HIGH
**Milestone:** Dashboard Redesign
**Recommended model:** Sonnet — one UI component over RD9's returns map; the data work is done by RD9.
**Estimated session length:** 1 – 1.5 hr
**Drafted by:** Vivek + Claude (Cowork session 2026-06-05)
**Depends on:** RD9 (returns-by-period service). Shares RD9's cached returns map with RD10.

> **After this ticket merges, the Overview shows a performance heatmap: rows = holdings, columns = 1D / 7D / 30D / YTD, each cell coloured by return magnitude with the % printed in-cell.** Mirrors the Claude Design "Performance Heatmap" card — the single best "what's moving" glance.

---

## Problem

There is no compact, at-a-glance view of each holding's performance across multiple windows.
The redesign's heatmap puts every holding's 1D/7D/30D/YTD returns in a coloured grid, sorted
by 30D, so leaders and laggards are obvious. The return numbers are exactly what RD9 produces,
so this ticket is rendering only.

## Acceptance criteria

- [ ] A new `app/ui/components/perf_heatmap.py` rendering a grid: one **row per held ticker**
      (label `TICKER (Company)`), one **column per window** in order `1D, 7D, 30D, YTD`.
- [ ] Rows sorted by **30D return descending**; tickers with `None` 30D sort to the bottom
      (consistent with the positions table's stale-last rule).
- [ ] Each cell is coloured on the **same diverging green↔red scale and ±14% clamp** as RD10
      (extract the shared scale into one place — e.g. a helper in `chart_theme`/`_chart_styles`
      — so treemap and heatmap can't drift). The return % is printed in the cell.
- [ ] `None` cells render neutral with `—` (em dash), never a fabricated `0.0%`.
- [ ] Hover (or cell title) shows `TICKER · <window>: <return>`.
- [ ] Reads the **same cached returns map** as the treemap (RD9 wrapper) — no second OHLC fetch.

## Files likely touched

- `app/ui/components/perf_heatmap.py` (new),
- a shared colour-scale helper (e.g. `app/ui/components/chart_theme.py` or `_chart_styles.py`)
  extracted/reused by both RD10 and RD11,
- `app/ui/pages/overview.py` (render call),
- `app/ui/styles/dark.css` (cell/grid classes if using an HTML grid),
- `tests/unit/ui/test_perf_heatmap.py` (new — ordering, None handling, colour mapping).

## Out of scope

- ❌ A period selector — the heatmap shows all four windows at once (that's its point). The
      selector belongs to the treemap (RD10).
- ❌ Click-to-open-position interactions beyond what already exists (hover/title is enough here).
- ❌ Computing returns — RD9.

## Test cases

1. Given three tickers with known returns, rows are ordered by 30D desc and each cell shows the
   expected formatted percent.
2. A ticker with `None` 30D sorts last regardless of its other windows.
3. A `None` cell shows `—` and a neutral colour, never `0.0%`.
4. Treemap and heatmap produce the **same colour** for the same return value (shared-scale
   regression — assert against the shared helper).
5. `pytest && ruff check . && mypy app/ && lint-imports` all pass.

## Notes

- **Verified (2026-06-05):** returns come from RD9's `compute_returns_by_period(...)` →
  `dict[str, dict[ReturnWindow, Decimal | None]]`. Company names via the same `name_lookup`
  the positions table uses. Formatting via `app/ui/format.py::format_pct`.
- Implementation choice (either is fine): a Plotly `go.Heatmap` with text annotations, or a
  CSS-grid of coloured cells driven by `dark.css` classes. If using the HTML grid, **preserve
  HTML-escaping** for the company name (the ROBUST-1 / RD1 rule) — escape via `html.escape`.
- The shared colour scale is the important bit: RD10 and RD11 must not each hard-code the
  clamp/scale. Land the shared helper here if RD10 didn't already, and have RD10 consume it.
- UI ticket → AGENTS.md Visual Verification (before/after screenshots) before the PR.
