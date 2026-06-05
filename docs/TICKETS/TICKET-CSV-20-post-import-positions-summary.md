# TICKET-CSV-20 — Post-import positions summary ("show me the holdings")

**Priority:** MEDIUM
**Estimated session length:** 1.5 hr
**Recommended model:** Sonnet — read-only summary view built from existing services.
**Drafted by:** Vivek + Claude Code (session 2026-06-05)
**Implemented by:** TBD
**Milestone:** Investment Panel

---

## Problem

After an import, the workbench shows row-level *actions* (new / blocked / already imported)
but never answers the question the user actually has: **"what do I hold now?"** To see
resulting positions the user has to leave for the Live Overview. The user wants the importer
to surface the holdings the import produced — ticker, shares, cost — as a confirmation that
the import did what they expected.

## Solution

After a successful Apply, render a **Positions summary** card on the Import Workbench: the
current holdings (from the existing positions/valuation service over the post-apply book),
one row per ticker — shares, average cost (EUR), and the ISIN that maps to it. Read-only.

### Decisions already made — do not re-litigate

- Reuse the existing positions computation (the same service the Live Overview uses); do not
  re-derive FIFO in the UI.
- Cost basis only (book values). **No live prices / market value here** — that keeps the card
  offline-safe and avoids coupling the import flow to yfinance (L1 vs L2 separation,
  ARCHITECTURE). Live value stays on the Overview.
- Show it after Apply (and optionally always, reflecting the current book) — pick one and
  document it. Recommended: render after Apply succeeds, plus a persistent "current holdings"
  count line.

### Execution

1. Identify the existing service that returns positions from the book (the one Live Overview
   calls via wiring). Call it post-apply.
2. Render a compact table: Ticker · Shares · Avg cost (EUR) · ISIN · Tax kind. Use
   `app/ui/format.py` for money/number formatting.
3. Handle the empty book gracefully (no positions → friendly note).
4. Tests: a render-smoke test and, if a pure mapping helper is introduced
   (positions → table rows), a unit test for it.
5. Gate.

## Acceptance criteria

- [ ] After Apply, the workbench shows a holdings table (ticker, shares, avg cost EUR, ISIN,
      tax kind) built from the existing positions service.
- [ ] No live-price/network dependency in this card.
- [ ] Empty book renders without error.
- [ ] `pytest`, `ruff check .`, `mypy app/`, `lint-imports` clean.

## Files likely touched

- `app/ui/pages/import_workbench.py`, possibly a small pure helper + its test
- `tests/unit/ui/test_import_workbench.py`

## Out of scope

- Live market value / unrealized P&L (that's the Live Overview's job).
- Editing positions from this card (Manage Portfolio / Mappings own mutations).

## Notes / assumptions

- Assumes a positions service already exists and is reachable from the UI via `app/ui/wiring.py`
  (Live Overview uses it). Confirm its signature before drafting the call.
- Mapping ticker → ISIN/tax-kind for the table comes from the ISIN map; a ticker with no map
  entry (legacy orphan) should still render, with ISIN/kind shown as "—".
