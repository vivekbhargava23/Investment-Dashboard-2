# TICKET-RD6 — Inline tranches + tax-aware sell on the overview

**Priority:** HIGH
**Milestone:** Dashboard Redesign
**Recommended model:** Opus — surfaces FIFO + German tax math at the decision point; correctness is costly to get wrong.
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-06-04)
**Depends on:** RD1 (the `positions_table` component) + RD2 (sortable table) — rows become expandable on that component

> **After this ticket merges, you can see when you bought and what a sell would cost — without
> leaving the overview.** Expanding a position reveals its tranches (lots), and an inline estimator
> shows the FIFO lots a sell would consume plus the estimated realised gain and German tax — reusing
> the existing sell-simulator and tax engines, not reimplementing them.

---

## Problem

To see acquisition tranches or the tax consequence of a sale today, the user must leave the overview
for the standalone Sell Simulator page, type the ticker and a quantity, and read results on a
separate screen. The data is already on hand: each `LivePosition.position.open_lots` carries the
tranches, and `app/services/sell_simulator.py` + `app/services/tax_planning.py` already compute
FIFO consumption, realised gain, and tax. This ticket surfaces them in place.

## Decision

Reuse, don't rebuild. The expandable positions-table row (from RD1's component) reveals per-lot
tranche detail and a compact estimator that calls the **existing** `simulate_sell` entry point.
The standalone Sell Simulator page stays for now (deeper flow); this is the quick inline path.

## Acceptance criteria

- [ ] Expanding a position row shows its open lots, one line per tranche:
  acquisition date, shares, cost basis (EUR), current value/gain (EUR), and holding duration.
  Source: `LivePosition.position.open_lots` (no new fetch).
- [ ] An inline sell estimator within the expansion: the user enters shares (or a EUR amount), and
  the row shows, via `app/services/sell_simulator.py::simulate_sell` (build a
  `SellSimulationRequest`): the FIFO `LotConsumption` breakdown, estimated realised gain, and the
  estimated tax / Sparerpauschbetrag impact already produced by the simulation + tax engine.
- [ ] No FIFO or tax logic is reimplemented — call `simulate_sell` and the existing
  `app/services/tax_planning.py` functions (`compute_marginal_tax_for_realised_gains` /
  `compute_per_position_harvest_impact`) as the simulation already does.
- [ ] Graceful states: stale position (no live price) shows tranches but disables the estimator with
  a note; zero/invalid quantity shows a neutral prompt, never a crash.
- [ ] Reuses formatting helpers (`format_eur`, `format_pct`) for all monetary/percent output.

## Files likely touched

- `app/ui/components/positions_table.py` — expandable row + tranche detail (from RD1)
- `app/ui/components/inline_sell.py` — new (thin UI over `simulate_sell`); or a private helper in positions_table
- `app/ui/pages/overview.py` — pass what the estimator needs
- `tests/unit/ui/test_inline_sell.py` — new (pure glue: request building, result mapping)

## Out of scope

- ❌ Removing or redesigning the standalone Sell Simulator page — it stays.
- ❌ New tax rules — only surface what the existing engine returns.
- ❌ Moving the table to Portfolio Home — structural, later.
- ❌ Multi-leg / partial-across-tickers sells — single position at a time, as the simulator does.

## Tests

- [ ] Building a `SellSimulationRequest` from a row + entered quantity is correct (pure helper).
- [ ] Mapping a `SellSimulation` result to display rows (lot consumption, gain, tax) is correct.
- [ ] Stale position disables the estimator (no `simulate_sell` call).
- [ ] `pytest && ruff check . && mypy app/ && lint-imports` all pass.
