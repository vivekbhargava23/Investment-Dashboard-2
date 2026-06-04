# TICKET-RD5 — NAV history backfill + capture

**Status:** DRAFT
**Priority:** HIGH
**Milestone:** Dashboard Redesign
**Recommended model:** Opus — reconstruction correctness over money/FX history; deterministic results matter.
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-06-04)
**Depends on:** TICKET-013 (daily NAV snapshot service — already merged)

> **After this ticket merges, the portfolio has a real daily NAV time series on disk.** A backfill
> reconstructs NAV from the first transaction date to today and persists it; re-running fills only
> missing days. This is the "start the clock early" data foundation for Wave B (scoreboard,
> drawdown, attribution) — start it now even though the charts come later.

---

## Problem

TICKET-013 built the NAV snapshot service (reconstruct-on-demand from transactions + historical
OHLC + FX, persisted to `data/nav_snapshots.json`). But that file currently holds **only 2 points**
(both `is_reconstructed`), because nothing has ever driven a full-range reconstruction. Every Wave B
view with a time axis (equity curve, drawdown, return-vs-benchmark, attribution) is dead without a
populated series. We need to (a) backfill history once and (b) keep it current.

## Decision

Use the existing `app/services/nav.py::get_nav_series(start, end)` — it already reconstructs and
persists. This ticket adds a thin driver that calls it over the full range and a documented refresh
path. No new reconstruction logic; no benchmark NAV (that's fetched directly in RD8).

Note the TICKET-013 invariant: `JsonTransactionRepository.save_all` clears the NAV cache on every
save. So backfill should be run after imports settle; document this interaction (running backfill
right after a large import is the intended sequence).

## Acceptance criteria

- [ ] New driver `app/scripts/backfill_nav.py` (CLI-runnable) that:
  - Resolves the **earliest `transaction_date`** across all transactions as the start, today as the end.
  - Calls `get_nav_series(start, today)` with real wired repos/providers, persisting the result.
  - Prints a summary: number of points written, date range covered, and any tickers that had OHLC
    gaps (using the per-ticker fallback already in the service).
- [ ] Idempotent: a second run reconstructs only missing days and writes zero new points if already current.
- [ ] If there are no transactions, exits cleanly with a clear message (no crash, no empty-range error).
- [ ] After running against real data, `data/nav_snapshots.json` contains one point per trading day
  across the range (verified manually in the PR — see test cases).
- [ ] A short note in the script docstring (and/or `tools/README.md`) on when to run it (after
  imports) and the cache-clear-on-save interaction.

## Files likely touched

- `app/scripts/backfill_nav.py` — new
- `app/scripts/__init__.py` — if needed
- `tools/README.md` — document the refresh command (optional but preferred)
- `tests/unit/scripts/test_backfill_nav.py` — new (on fakes)

## Out of scope

- ❌ Benchmark NAV (VWCE/S&P) — fetched directly in the scoreboard ticket (RD8), not stored here.
- ❌ The equity-curve / drawdown UI — Wave B.
- ❌ Scheduled/automatic capture infrastructure — manual command for now; note scheduling as a
  follow-up. (Reconstruct-on-demand already keeps things correct when analytics opens.)
- ❌ Surgical cache invalidation — TICKET-013's wholesale clear-on-save stands.

## Tests

- [ ] Backfill over a `FakeOhlcDataProvider` + `FakeTransactionRepository` produces the expected
  number of points for a known date range and known closes.
- [ ] Idempotency: second run with a warm cache writes zero additional points.
- [ ] Start date equals the earliest transaction date (not an arbitrary constant).
- [ ] No-transactions case exits cleanly.
- [ ] `pytest && ruff check . && mypy app/ && lint-imports` all pass.
