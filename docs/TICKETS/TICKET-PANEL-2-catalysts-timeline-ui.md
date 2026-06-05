# TICKET-PANEL-2 — Catalysts timeline on Overview (+ per-position variant)

**Priority:** HIGH
**Milestone:** Investment Panel
**Recommended model:** Sonnet — a focused rendering component over PANEL-1's service, plus a legend + table.
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (Cowork session 2026-06-05)
**Depends on:** PANEL-1 (catalysts data layer + service). Implements ADR-013's UI.

> **After this ticket merges, the Overview shows a portfolio-wide catalysts timeline** — upcoming events across all holdings, grouped into time bands, colour-coded by category and sized by impact, with a companion table — **and the same component renders a per-position timeline** for a single ticker. Mirrors the Claude Design Behavioral-Ledger "Catalysts" tab, adapted to a portfolio view.

---

## Problem

Vivek wants the catalysts timeline (the feature he liked from the design) on the Overview,
portfolio-wide, so date clusters across holdings are visible ("three earnings dates in late
May"). The design's version is per-position; the strongest adaptation is **portfolio-wide on
Overview + per-position in a drilldown**, both from the same component. PANEL-1 supplies the
data; this ticket renders it.

## Acceptance criteria

### Component

- [ ] A new `app/ui/components/catalysts_timeline.py::render_catalysts_timeline(events, *, as_of, mode)`
      where `mode ∈ {"portfolio", "position"}`.
- [ ] A **legend** of the six categories with their colours
      (earnings / macro / product / regulatory / dividend / lockup) and a `today · <as_of>`
      marker, matching the design's legend row.
- [ ] Events are **grouped into time bands** — `This week`, `This month`, `Next 3 months`,
      `Later` — using PANEL-1's `time_band(...)`. (Time bands chosen over a pixel-precise axis
      for scan-ability, per the Cowork design discussion.) Empty bands are omitted.
- [ ] Within each band, events render with: date, label, a **category colour** chip/dot, and an
      **impact-driven size/weight** (high > med > low). In portfolio mode each event also shows
      its ticker; portfolio-scope (macro) events are clearly marked as applying to the whole book.
- [ ] `date_confidence == "estimated"` events are visually distinct (e.g. hollow dot / "~"
      prefix / muted) so an estimated date is never mistaken for a confirmed one (ADR-013).
- [ ] A **companion table** below the timeline: Date · Event · (Ticker, portfolio mode) ·
      Category · Impact, sorted by date.
- [ ] The `updated` date from the document is surfaced (e.g. "catalysts as of <updated>") so
      staleness is visible.
- [ ] Empty state: when there are no upcoming events, a clear "No upcoming catalysts" message,
      not a broken/empty frame.

### Wiring on Overview

- [ ] Overview renders `mode="portfolio"` using `get_portfolio_catalysts(held_tickers, as_of=…,
      repo=get_catalysts_repo())`, where `held_tickers` is derived from the live positions
      already computed on the page.
- [ ] Result cached via `@st.cache_data` keyed on the transactions signature + `as_of` date +
      a signature of the catalysts file (the file is tiny — read once per session).

### Per-position variant

- [ ] The same component renders `mode="position"` for a single ticker via
      `get_position_catalysts(ticker, as_of=…, repo=…)`. Surface it where per-position detail
      already lives (e.g. the position/lot detail context, or the Company page) — reuse the
      existing drilldown surface; **do not invent a new drawer** if one isn't already present
      (if there's no suitable surface yet, ship portfolio mode on Overview and note the
      per-position placement as a fast follow).

## Files likely touched

- `app/ui/components/catalysts_timeline.py` (new),
- `app/ui/pages/overview.py` (render + cache),
- the per-position surface page (e.g. `app/ui/pages/company.py`) if one fits,
- `app/ui/styles/dark.css` (timeline/legend/band/table classes),
- `tests/unit/ui/test_catalysts_timeline.py` (new).

## Out of scope

- ❌ Editing catalysts in the app — read-only (ADR-013); curation is via Cowork PR.
- ❌ Auto-fetching dates — deferred (ADR-013).
- ❌ Other Behavioral-Ledger tabs from the design (Debate, Thesis & Tripwires, Scenarios,
      Sources, Journal) — separate future tickets if pursued.
- ❌ A pixel-precise date axis — we use time bands by design.

## Test cases

1. Given events spanning several bands, the component groups them correctly and omits empty
   bands, ordered `This week → Later`.
2. Portfolio mode: a `scope: portfolio` macro event appears once, marked as book-wide; a
   position event appears under its ticker.
3. An `estimated` event renders with the distinct treatment (assert the marker/class differs
   from a `confirmed` one).
4. The companion table is sorted by date and includes the ticker column only in portfolio mode.
5. Empty input → "No upcoming catalysts" message, no exception.
6. Company name / label HTML-escaped if rendered via HTML grid (ROBUST-1 rule).
7. `pytest && ruff check . && mypy app/ && lint-imports` all pass.

## Notes

- **Verified (2026-06-05):** consumes PANEL-1's `get_portfolio_catalysts` /
  `get_position_catalysts` and `time_band`. Held tickers come from the live positions the
  Overview already computes (`_cached_live_positions`). Colours should live alongside the other
  chart tokens (`chart_theme` / `_chart_styles`) — one source of category→colour, reused by the
  legend, dots, and table.
- The design's reference categories+colours (`ledger-detail.jsx::TabCatalysts`) were
  earnings/macro/product/regulatory; ADR-013 adds dividend + lockup. Keep the palette in the
  light theme (the dashboard is light per the design direction "stay close to current light
  theme").
- UI ticket → AGENTS.md Visual Verification (before/after screenshots) before the PR.
- **Assumption to confirm before implementing (METHODOLOGY §verification):** that a suitable
  per-position drilldown surface exists to host `mode="position"`. If not, portfolio mode ships
  first and per-position placement becomes a fast-follow ticket — do not build a new drawer
  purely to host it.
