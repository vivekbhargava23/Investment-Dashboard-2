# TICKET-RD9 — Returns-by-period service (shared foundation for treemap + heatmap)

**Priority:** HIGH
**Status:** IN_PROGRESS
**Milestone:** Dashboard Redesign
**Recommended model:** Sonnet — well-scoped: pure return math in domain + a thin batching service over the existing OHLC provider, with clear tests.
**Estimated session length:** 1.5 – 2 hr
**Drafted by:** Vivek + Claude (Cowork session 2026-06-05)
**Depends on:** — (consumes the existing `get_ohlc_histories` service + `OhlcSeries` domain model)

> **After this ticket merges, there is one cached source of per-ticker returns over standard windows (1D / 7D / 30D / YTD).** RD10 (treemap colour) and RD11 (heatmap) both read from it, so the windows are computed once and reused.

---

## Problem

The redesigned Overview needs per-holding returns over several windows: the treemap colours
tiles by a selectable-period return, and the heatmap shows 1D/7D/30D/YTD side by side. There
is no single place that produces these today, and we do **not** want the treemap and heatmap
each recomputing returns (slow, and risks divergent numbers). We need one pure, tested
returns computation plus a thin batching/caching wrapper so switching the treemap period is a
re-colour with zero recompute.

## Acceptance criteria

### Domain (pure)

- [ ] In `app/domain/market_data.py` (or a focused new domain module), a pure function
      `period_return(series: OhlcSeries, window: ReturnWindow, *, as_of: date) -> Decimal | None`
      that returns the percent change over the window, or `None` when the series lacks enough
      history to cover it.
- [ ] A `ReturnWindow` enum/Literal covering `D1`, `D7`, `D30`, `YTD` (named windows, not raw
      day counts in callers).
- [ ] Window semantics, documented and tested: `D7`/`D30` are calendar-day lookbacks from
      `as_of` to the most recent bar on/before `as_of − N days`; `YTD` is from the last bar of
      the prior calendar year (or first bar of the current year) to `as_of`; `D1` is the last
      two available closes. Returns are `Decimal` percent (e.g. `Decimal("4.2")` = +4.2%).
- [ ] No `datetime.now()` in domain — `as_of` is passed in. Money/ratios use `Decimal`.

### Service

- [ ] `app/services/returns.py::compute_returns_by_period(tickers, *, as_of, provider, windows=ALL) -> dict[str, dict[ReturnWindow, Decimal | None]]`
      that fetches history once via `get_ohlc_histories(...)` and computes every requested
      window per ticker in a single pass.
- [ ] Per-ticker failures are omitted/`None`, never raised (consistent with
      `get_ohlc_histories` behaviour). A ticker with no series yields all-`None`.
- [ ] The period used for the underlying OHLC fetch is wide enough to satisfy the longest
      window (≥ 1Y / YTD).

### UI cache

- [ ] A `@st.cache_data(ttl=…)` wrapper in the Overview page (or a shared cache module) keyed
      on the transactions signature + `as_of` date (reuse `transactions_signature` /
      `app/ui/cache_keys.py`), returning the full returns map so the period selector re-colours
      from cache with no recompute.

## Files likely touched

- `app/domain/market_data.py` (or new `app/domain/returns.py`),
- `app/services/returns.py` (new),
- `app/ui/pages/overview.py` (cached wrapper) or `app/ui/cache_keys.py`,
- `tests/unit/domain/test_returns.py` (new), `tests/unit/services/` as needed.

## Out of scope

- ❌ Rendering anything — RD10 (treemap) and RD11 (heatmap) consume this.
- ❌ A user-configurable custom-N window (the selector ships the fixed set; custom N is a
      later enhancement).
- ❌ FX-adjusting returns into EUR. Returns are native-price percentage changes (a % move is
      currency-agnostic for the colour scale); EUR value is the treemap *size*, handled in RD10.

## Test cases

1. A synthetic `OhlcSeries` with a known close path yields the exact expected `D7`/`D30`/`YTD`
   percentages for a fixed `as_of`.
2. A series shorter than the window returns `None` for that window (not a wrong number, not a
   raise).
3. `YTD` on a series straddling Jan 1 measures from the prior-year-end close.
4. `compute_returns_by_period` with a ticker the provider can't serve omits/`None`s it and
   still returns the others.
5. `pytest && ruff check . && mypy app/ && lint-imports` all pass.

## Notes

- **Verified signatures (2026-06-05):** `app/services/market_data.py` exposes
  `get_ohlc_histories(tickers, period, *, provider, freq=None) -> dict[str, OhlcSeries]`
  (batch, per-ticker failures omitted) and `get_ohlc_history(...)`. `app/domain/market_data.py`
  defines `ChartPeriod` (StrEnum incl. `ONE_DAY`, `YEAR_TO_DATE`), `OhlcBar` (`.close: Decimal`),
  and `OhlcSeries` (`.bars`, `.latest_close`, and an existing percent-change property ~line 105).
  Confirm whether the existing `OhlcSeries` percent-change property already covers the full-span
  case before adding `period_return`; reuse it if so.
- The OHLC provider is obtained in the UI via `get_ohlc_data_provider()` (`app/ui/wiring.py`).
- This is the deliberate "compute all periods once" foundation Vivek asked for so the treemap
  period selector feels instant.
