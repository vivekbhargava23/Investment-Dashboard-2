# TICKET-RD7 — Concentration + effective-number-of-stocks block

**Status:** DRAFT
**Priority:** MEDIUM
**Milestone:** Dashboard Redesign
**Recommended model:** Sonnet — one small pure domain function + a presentation block; clear tests.
**Estimated session length:** 1.5 – 2 hr
**Drafted by:** Vivek + Claude (chat 2026-06-04)
**Depends on:** RD4 (explain-this-number component)

> **After this ticket merges, the dashboard says how many *independent* bets you actually hold.** A
> concentration block surfaces top-weights, the Herfindahl score, and a new "effective number of
> stocks" — each self-explaining via the RD4 component — so a book of 12 names that are really one
> AI-semis bet reads honestly (`REDESIGN_STRATEGY.md` §5, idea 3).

---

## Problem

Concentration data exists (`compute_concentration_view` → `ConcentrationView` with `top_1_pct`,
`top_3_pct`, `herfindahl`) but is shown as a bare Herfindahl number with no interpretation. The
user's real question — "how many separate bets is this, really?" — isn't answered. Herfindahl is
unintuitive; "effective number of stocks" is the legible version of the same math.

## Decision

Add one pure domain function for effective N (derived from the existing percent-weight Herfindahl,
keeping a single source of truth), then present the concentration metrics as a block where each
number explains itself through RD4's `render_explainable_metric`.

## Acceptance criteria

- [ ] New pure function `effective_number_of_stocks(weights_pct: list[Decimal]) -> Decimal` in
  `app/domain/analytics.py`, defined consistently with the existing `herfindahl_index` (for
  percent weights summing to 100: `Decimal(10000) / herfindahl`, i.e. `1 / Σ(frac²)`). Guard the
  empty / zero-Herfindahl case (return `Decimal(0)` or the count, documented). Fully unit-tested.
- [ ] A concentration block (component, e.g. `app/ui/components/concentration_block.py`) rendering,
  each via `render_explainable_metric` (RD4):
  - Top-1 weight, Top-3 weight, Herfindahl, and **Effective number of stocks** with the meaning
    "your N holdings behave like ~X independent bets."
  - A one-line supporting note using the already-computed average pairwise correlation
    (`correlation_matrix` / the correlation service) where available.
- [ ] Wire the block into the Analytics **concentration** tab, replacing the bare Herfindahl render.
  Structure it so the same block can later be dropped onto Portfolio Home (no page-specific coupling).
- [ ] Each metric's `ExplanationSpec` includes the actual weights used, so "how?" shows real inputs.

## Files likely touched

- `app/domain/analytics.py` — `effective_number_of_stocks` (+ export)
- `app/ui/components/concentration_block.py` — new
- `app/ui/pages/analytics.py` — use the block in the concentration tab
- `tests/unit/domain/test_analytics.py` — effective-N cases

## Out of scope

- ❌ Sector / currency / geography exposure — needs classification data; separate later ticket.
- ❌ Rebuilding the correlation heatmap — reuse what exists.
- ❌ Portfolio Home page itself — structural, later (the block is built to be reusable there).

## Tests

- [ ] `effective_number_of_stocks`: equal weights across N names → ≈ N; one dominant name → ≈ 1;
  empty input → documented guard value.
- [ ] Consistency: effective N derived from `herfindahl_index` matches `1/Σ(frac²)` on a hand example.
- [ ] `pytest && ruff check . && mypy app/ && lint-imports` all pass.
