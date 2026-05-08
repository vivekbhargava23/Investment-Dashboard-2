# TICKET-013 — Daily NAV snapshot service

**Status:** READY
**Priority:** P1
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-08)
**Implemented by:** _pending_
**Depends on:** TICKETs 001 (domain models), 002 (FIFO engine), 003 (JSON repository), 004-005 (yfinance prices + FX), 006 (valuation service)

> **After this ticket merges, the dashboard has a daily portfolio NAV time series.** A new domain model (`DailyNavPoint`), a new port (`NavSnapshotRepository`), a JSON-backed adapter, and a service that, given a date range, returns the portfolio's EUR NAV per trading day — reconstructing missing days from historical OHLC + transaction history, and persisting the result so the next call is fast. This is the data foundation for the Performance, Risk, and Concentration analytics tabs.

---

## Problem

Every analytics view that has a time axis (equity curve, drawdown, return-vs-benchmark, rolling correlation) needs **daily portfolio NAV in EUR going back at least one year**. We currently have:

- The current portfolio's lots (`Transaction` repository → `compute_positions`)
- Live spot prices and FX (`yfinance` adapter)
- Historical OHLC per ticker (`OhlcDataProvider`, TICKET-022a)

What we don't have: a way to ask "what was the EUR value of this portfolio on 2025-08-14?" Computing it on the fly per render is O(positions × days × 2 fetches per day) — for ~13 positions over 365 days that's ~9,500 fetches if uncached, and even with the OHLC cache the reconstruction work is non-trivial. It also blocks any analytics page that wants to show "performance over the last 5 years."

This ticket builds the snapshot layer once, persists it, and lets analytics tabs treat NAV as a cheap lookup.

---

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-08.

### 1. Snapshots are reconstructed, not appended

A naive design would write today's NAV to disk every time the user opens the app, building the series day by day going forward. We reject that because:

- It only works going forward — the user sees a flat or empty curve until 90 days have passed.
- It can't survive "I just imported 2 years of historical Scalable transactions."
- Re-runs after a transaction edit (FIFO replay-on-edit, ADR-003) would silently produce inconsistent snapshots.

Instead: **snapshots are deterministic functions of (transaction history, historical OHLC, historical FX) for a given date.** The service reconstructs them on demand and caches the results.

### 2. Reconstruction algorithm

Given a target date `d`:

1. Replay all transactions with `transaction_date <= d` through the FIFO engine to get open lots as of `d`.
2. For each open lot's ticker, fetch the `Close` from historical OHLC for the most recent trading day on or before `d`. Cache hit if available; otherwise fetch.
3. Convert each position's value to EUR using the FX rate for `d` (closest available trading-day FX from yfinance — see decision #5 on FX).
4. Sum to get portfolio NAV in EUR.

Result: one `DailyNavPoint` for that day. Service operates over a **date range**, not per-day, so the OHLC/FX fetches batch.

### 3. New domain model: `DailyNavPoint`

```python
class DailyNavPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshot_date: date           # the calendar date this NAV represents
    nav_eur: Money                # portfolio EUR value at end of that trading day
    cost_basis_eur: Money         # sum of lot cost-basis-EUR for lots open on that day
    n_positions: int              # number of distinct tickers with open lots
    is_reconstructed: bool        # True if rebuilt from history; False if computed live (today)
```

Lives in `app/domain/nav.py`. `cost_basis_eur` is included so analytics can show realised-vs-unrealised splits without re-running FIFO.

### 4. New port: `NavSnapshotRepository`

Simple Protocol with three methods:

```python
class NavSnapshotRepository(Protocol):
    def load_range(self, start: date, end: date) -> list[DailyNavPoint]: ...
    def save_points(self, points: list[DailyNavPoint]) -> None: ...
    def clear(self) -> None: ...  # invalidation hook (used after FIFO replay-on-edit)
```

Lives in `app/ports/nav_repository.py`. The `clear` method is the hook for **invalidation on transaction edit** — see decision #6.

### 5. FX during reconstruction

We do **not** add a new ECB historical FX adapter. Reasons:

- yfinance's `EURUSD=X` and `EURJPY=X` tickers expose daily FX history via the same `OhlcDataProvider` interface we already use for prices. One source, one cache, one failure mode.
- ADR-004 says **cost basis EUR is frozen at transaction-date ECB FX**. That is *cost basis*, not *valuation*. Valuation EUR uses current FX (architectural invariant 3). Reconstructed daily valuations follow the valuation rule, not the cost-basis rule.

The reconstruction service treats `EURUSD=X` and `EURJPY=X` like any other ticker — fetched via the existing OHLC port. Service-layer cache covers them.

### 6. Invalidation: cache is dropped wholesale on FIFO replay

If the user edits or deletes a historical transaction, all subsequent NAV points are stale. Rather than computing the affected range, we follow the existing FIFO replay-on-edit philosophy (ADR-003): **drop the entire snapshot cache and let the next analytics page render rebuild lazily.**

This keeps the implementation simple and matches the existing mental model (edits trigger full FIFO replay; we extend that to "edits also drop the NAV cache"). The `NavSnapshotRepository.clear()` method is called from the `TransactionRepository`'s save path when a non-append edit is detected.

For the v1 of this ticket: **call `clear()` from the `TransactionRepository.save_all()` adapter unconditionally on every save.** This is over-cautious (a pure append doesn't strictly need invalidation) but it's correct, simple, and the cost is one fresh reconstruction next time analytics is opened. Optimisation is out of scope.

### 7. Storage format

JSON file at `data/nav_snapshots.json`, atomic-write pattern same as `JsonTransactionRepository`. Format:

```json
{
  "version": 1,
  "snapshots": [
    {"snapshot_date": "2025-05-08", "nav_eur": {"amount": "12345.67", "currency": "EUR"},
     "cost_basis_eur": {"amount": "10000.00", "currency": "EUR"},
     "n_positions": 13, "is_reconstructed": true}
  ]
}
```

Sorted ascending by date. One file per portfolio (we have one portfolio).

### 8. Today's NAV is computed live, not cached

The service has two code paths:

- **Historical** (`snapshot_date < today`): reconstruct from OHLC `Close` for that day, cache the result.
- **Today** (`snapshot_date == today`): call the existing `compute_live_positions` + `compute_portfolio_summary`, return a `DailyNavPoint` with `is_reconstructed=False`. **Do not cache.** Today's NAV moves with the market until close.

After market close, today's NAV becomes yesterday's reconstructed point on the next call. The service handles this transparently.

### 9. Trading-day calendar

We do not maintain our own trading calendar. The service asks the OHLC provider for a date range; whatever days come back are trading days. Weekends/holidays are absent from the reconstructed series. The Performance tab will plot points only on dates that exist (no gap-filling).

For sparse data (e.g. an exchange with low volume, or a single ticker), the service uses the **most recent close on or before the target date** for that ticker — so a portfolio with one ticker on the NYSE and one on Frankfurt doesn't get holes when one exchange is closed and the other isn't. This is implemented in domain logic, not in the adapter.

---

## Acceptance criteria

- [ ] `app/domain/nav.py` exists with `DailyNavPoint` (frozen Pydantic v2 model).
- [ ] `app/ports/nav_repository.py` exists with `NavSnapshotRepository` Protocol.
- [ ] `app/adapters/repo_json/nav_repo.py` implements the port. Atomic writes (temp file + fsync + os.replace), schema versioning, sorted-by-date storage.
- [ ] `app/services/nav.py` exposes:
  - `get_nav_series(start: date, end: date) -> list[DailyNavPoint]` — primary entry point. Returns one point per trading day in range. Reconstructs missing days, persists them, returns sorted ascending.
  - `clear_nav_cache() -> None` — drops the persisted snapshots file. Called from `TransactionRepository.save_all`.
- [ ] `JsonTransactionRepository.save_all` calls `clear_nav_cache()` after a successful save (the "drop cache on every save" rule from decision #6).
- [ ] Today's NAV is always computed live and never persisted (decision #8).
- [ ] FX during reconstruction uses `EURUSD=X` / `EURJPY=X` via the existing `OhlcDataProvider` (decision #5). No new FX adapter.
- [ ] Per-ticker failure isolation: if OHLC for one ticker is unavailable for a date, the service uses the most recent available close on or before that date (decision #9). If no close is available at all for a ticker on or before the target date, the position contributes zero to NAV for that date and a warning is logged (do not raise).
- [ ] Tests pass: `pytest`, `ruff check .`, `mypy app/`, `lint-imports`.
- [ ] Domain layer `app/domain/nav.py` has zero I/O imports (architecture rule).
- [ ] Service `app/services/nav.py` accepts ports as parameters (no globals).

## Files likely touched

- `app/domain/nav.py` — new
- `app/domain/__init__.py` — export `DailyNavPoint`
- `app/ports/nav_repository.py` — new
- `app/ports/__init__.py` — export `NavSnapshotRepository`
- `app/adapters/repo_json/nav_repo.py` — new
- `app/services/nav.py` — new
- `app/adapters/repo_json/json_repo.py` — wire `clear_nav_cache()` into `save_all` (decision #6)
- `tests/unit/domain/test_nav.py` — new
- `tests/unit/services/test_nav.py` — new (with `FakeOhlcDataProvider`, `FakeTransactionRepository`, `FakeNavSnapshotRepository`)
- `tests/integration/test_nav_repo.py` — new (real JSON file, atomic writes, schema versioning)
- `tests/fakes/nav.py` — `FakeNavSnapshotRepository` for downstream analytics tests

## Out of scope

- ❌ Performance / Risk / Concentration UI tabs. Those are TICKET-A1 / A2 / A5.
- ❌ Benchmark NAV (S&P 500, DAX). Benchmarks are fetched directly via OHLC in the analytics tabs; they don't go through this snapshot store.
- ❌ Realised-gain time series. Realised gains are derivable from `Transaction` history alone — no NAV reconstruction needed. Out of scope here.
- ❌ Granularity below daily (e.g. hourly intraday NAV). Daily only.
- ❌ Surgical cache invalidation (recompute only affected range after a transaction edit). v1 is wholesale clear-on-save; optimisation is a separate ticket if it ever matters.
- ❌ Performance / latency optimisation beyond "OHLC service cache covers it." If reconstruction is too slow with N positions × 365 days, that's a follow-up.

## Test cases

### Domain (`tests/unit/domain/test_nav.py`)

1. `DailyNavPoint` is frozen — assignment after construction raises.
2. `nav_eur` and `cost_basis_eur` must be EUR-currency `Money` instances (validator).
3. `n_positions >= 0` (validator); `nav_eur.amount >= 0` and `cost_basis_eur.amount >= 0` (validators).
4. Round-trip serialise → deserialise via Pydantic preserves `Decimal` precision.

### Service (`tests/unit/services/test_nav.py`)

5. **Happy path: empty cache, full reconstruction.** Given 2 transactions (one EUR, one USD), `OhlcDataProvider` returns 30 days of closes for both tickers + EURUSD=X. `get_nav_series(start, end)` returns 30 points, all `is_reconstructed=True`, sorted ascending, EUR amounts match a hand-computed expected.
6. **Cache hit path.** Same setup, but `FakeNavSnapshotRepository.load_range` already has 25 of 30 days. Service should reconstruct only the 5 missing days, persist them, and return the full 30. Verify only 5 ticker-day OHLC calls were made (call counter on the fake).
7. **Today is live, not cached.** `get_nav_series(today, today)` returns one point with `is_reconstructed=False` and never calls `save_points`.
8. **Per-ticker missing data: ticker has no OHLC for 2025-08-14 but has it for 2025-08-13.** Service uses the 2025-08-13 close for the 2025-08-14 NAV reconstruction (decision #9). One log warning; no exception.
9. **Per-ticker missing data: ticker has no OHLC anywhere on or before target date.** That ticker contributes zero to NAV for that date. One warning. Other tickers' contributions are intact. NAV is computed correctly from the remaining positions.
10. **Lot-edit invalidation.** Save a transaction, then call `get_nav_series` — it must reconstruct from scratch (cache was cleared by `save_all`). Verify by saving a second time and asserting `clear_nav_cache` was called twice on the fake.
11. **FX reconstruction.** A USD position on 2025-08-14: NAV's USD-side contribution = `shares × close_usd_2025-08-14 / EURUSD_close_2025-08-14`, in EUR. Hand-computed expected matches.
12. **Reconstruction is deterministic.** Calling `get_nav_series(d, d)` twice returns identical `DailyNavPoint`s (assuming OHLC fake returns same closes). Important for snapshot tests in downstream analytics tickets.

### Adapter (`tests/integration/test_nav_repo.py`)

13. Save → load round-trip preserves `Decimal` precision and date sort order.
14. Atomic write: simulate a crash mid-write (e.g. by patching `os.replace` to raise) — file on disk is the previous valid version, not garbage.
15. Schema versioning: a v0 file (no `version` key) raises a clear error. A v2 file (future-version) raises a clear "downgrade is not supported" error.
16. `clear()` removes the file (or empties it to `{"version": 1, "snapshots": []}` — pick one and document).

### End-to-end on fakes (`tests/unit/services/test_nav.py`)

17. Full flow with realistic 13-position, 90-day window: cold cache reconstructs all 90 days × 13 tickers + 1 FX series; warm cache returns from disk only.

## Notes

- **Mind the date arithmetic**: use `date` (not `datetime`) throughout the domain layer. The service may need `datetime` to talk to OHLC adapters; convert at the boundary.
- **No `datetime.now()` in domain.** Pass `as_of` explicitly to anything that needs "today" (architecture rule). The service is the only place that resolves "today" by calling `date.today()` or whatever the existing services already use.
- **Don't try to be smart about per-day cache invalidation.** The "clear on every save" rule is explicit in decision #6 and the service test #10. If the implementation agent sees an opportunity to be clever, that's out of scope — open a follow-up ticket.
- **The OHLC fake (`tests/fakes/ohlc.py`) already exists** from TICKET-022a. Reuse it; don't write a new one.
- This ticket has many test cases. They are all real failure modes from the design discussion. None of them is optional.
