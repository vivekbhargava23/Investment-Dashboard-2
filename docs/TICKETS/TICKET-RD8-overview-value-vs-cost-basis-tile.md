# TICKET-RD8 — Overview hero tile: value vs. cost-basis sub-line

**Priority:** MEDIUM
**Milestone:** Dashboard Redesign
**Recommended model:** Sonnet — pure presentation change on an existing component; values already exist on `PortfolioSummary`.
**Estimated session length:** 30 – 45 min
**Drafted by:** Vivek + Claude (Cowork session 2026-06-05)
**Depends on:** — (builds on the `metric_card` component from RD1)

> **After this ticket merges, the Total Portfolio Value KPI shows the invested amount alongside the live value** — the gain in € and %, *and* the cost basis it's measured against, in one tile. Mirrors the Claude Design hero tile.

---

## Problem

The Overview's Total Portfolio Value tile shows the live value and (per current build) a
gain figure, but does not surface the **cost basis** — the actual money put in. Vivek wants
the anchor number visible: "value is €X, that's +€Y (+Z%) vs €C cost basis." All three
numbers already exist on `PortfolioSummary` (`total_value_eur`, `total_cost_basis_eur`,
`total_unrealised_gain_eur`, `total_unrealised_gain_pct`) — this is presentation only.

## Acceptance criteria

- [ ] The Total Portfolio Value tile renders a sub-line of the form
      `+€6,430 (+15.4%) vs. €41,780 cost basis`, where the gain is `total_unrealised_gain_eur`,
      the percent is `total_unrealised_gain_pct`, and the cost basis is `total_cost_basis_eur`.
- [ ] Gain is coloured green when ≥ 0, red when < 0 (reuse the existing `metric_card`
      sub-colour mechanism — `sub_color`/equivalent — do not add new inline styles).
- [ ] The cost-basis portion is rendered in muted/secondary text (the "anchor", not the
      headline).
- [ ] All money/percent formatting goes through `app/ui/format.py` (`format_eur`,
      `format_pct`); no ad-hoc f-string number formatting in the page.
- [ ] Sign handling: a negative total shows `−€… (−…%)` with the minus on both, no `+`.
- [ ] No change to any other KPI tile.

## Files likely touched

- `app/ui/pages/overview.py` (compose the sub-line from `PortfolioSummary`),
- `app/ui/components/metric_card.py` (only if the existing sub-line API can't express a
  two-tone "coloured gain + muted cost basis" line; prefer composing within the page),
- `tests/unit/ui/` (sub-line content + colour + sign tests).

## Out of scope

- ❌ The sparkline in the design's hero tile (separate concern; NAV history sparkline is
  RD5 territory). This ticket is the numbers only.
- ❌ Treemap / heatmap (RD10 / RD11).
- ❌ Changing how cost basis or gain is computed — these come straight off `PortfolioSummary`.

## Test cases

1. Given a summary with value €48,210, cost €41,780, gain +€6,430 / +15.4%, the tile sub-line
   contains `+€6,430`, `(+15.4%)`, and `€41,780 cost basis`, and the gain span carries the
   positive/green class.
2. Given a net-loss summary (gain −€1,200 / −3.1%), the sub-line shows minus signs and the
   negative/red class — no stray `+`.
3. Grep guard: no inline `style="…"` introduced in `overview.py` for this tile.
4. `pytest && ruff check . && mypy app/ && lint-imports` all pass.

## Notes

- Verified against `app/domain/positions.py`: `PortfolioSummary` exposes `total_value_eur`,
  `total_cost_basis_eur`, `total_unrealised_gain_eur`, `total_unrealised_gain_pct`,
  `position_count`, `live_position_count`. No new domain fields needed.
- The current overview computes the summary via `_cached_portfolio_summary(tx_sig, as_of_iso)`.
  Reuse it; do not re-fetch.
- UI ticket → follow the AGENTS.md Visual Verification step (before/after screenshots via
  `screenshot-app`) before opening the PR.
