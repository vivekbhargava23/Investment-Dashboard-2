# TICKET-R4 — Unify period selector and route Performance through it

**Status:** QUEUED
**Priority:** MEDIUM
**Estimated session length:** 45 min
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Milestone:** UI polish

---

## Problem

Two parallel period systems exist:

- `ChartPeriod` (`domain/market_data.py:14`) — used by charts, surfaced via `render_period_selector` (`app/ui/components/period_selector.py`).
- `PerformancePeriod` (`services/analytics_performance.py:29`) — used only by the Performance tab, includes `ONE_WEEK` and `MAX`. Translated to `ChartPeriod` via `_chart_period()` (`analytics_performance.py:212`).

Page UIs are inconsistent:

- Research: uses `render_period_selector` ✅
- Analytics Technicals tab: uses `render_period_selector` with `options=TECHNICALS_PERIODS` ✅
- Overview Position Chart: raw `st.radio` (`overview.py:353`) ❌
- Analytics Performance tab: raw `st.radio` over `PerformancePeriod` (`analytics.py:182`) ❌

This means three slightly-different period UIs and a translation layer maintained by hand.

## Solution

Keep `ChartPeriod` as the single domain-side enum. Make the selector handle the Performance tab's needs by allowing its option set to include `ONE_WEEK` and `FIVE_YEAR` (as the "MAX" proxy).

### Component change

Extend `_PERIOD_LABELS` in `period_selector.py` with `ONE_WEEK` (`"1W"`):

```python
_PERIOD_LABELS: dict[ChartPeriod, str] = {
    ChartPeriod.ONE_DAY: "1D",
    ChartPeriod.FIVE_DAY: "5D",
    ChartPeriod.ONE_WEEK: "1W",   # NEW — added to ChartPeriod
    ChartPeriod.ONE_MONTH: "1M",
    ...
}

PERFORMANCE_PERIODS: list[ChartPeriod] = [
    ChartPeriod.ONE_WEEK,
    ChartPeriod.ONE_MONTH,
    ChartPeriod.THREE_MONTH,
    ChartPeriod.SIX_MONTH,
    ChartPeriod.ONE_YEAR,
    ChartPeriod.FIVE_YEAR,  # "MAX" label override
]
```

Allow per-period label overrides via an optional `label_overrides` dict on `render_period_selector` so the Performance tab can render `FIVE_YEAR` as `"MAX"` without polluting the global label map.

### Service change

`get_performance_view` and helpers accept `ChartPeriod` directly. Delete `PerformancePeriod` and `_chart_period()`. The `_requested_days` mapping moves to use `ChartPeriod` keys.

### Page wiring

- `overview.py:353` — replace the raw `st.radio` with `render_period_selector("overview_chart_period", default="1Y")`.
- `analytics.py:182` — replace with `render_period_selector("performance_period", options=PERFORMANCE_PERIODS, default="6M", label_overrides={ChartPeriod.FIVE_YEAR: "MAX"})`.

## Acceptance criteria

- [ ] `ChartPeriod.ONE_WEEK` added with value `"1w"`. Adapter (`yfinance_adapter.py::_interval_for_period`) handles it (use `1d` interval, period `"5d"` or `"1mo"` and trim — verify with yfinance behaviour).
- [ ] `PerformancePeriod` removed; all call sites use `ChartPeriod`.
- [ ] `_chart_period()` removed from `analytics_performance.py`.
- [ ] `render_period_selector` supports `label_overrides`.
- [ ] Overview Position Chart and Performance tab both use `render_period_selector`.
- [ ] Performance tab still displays `1W / 1M / 3M / 6M / 1Y / MAX` (with MAX rendering 5Y data, same as today).
- [ ] All tests pass; ruff / mypy / lint-imports clean.

### Manual smoke

- Overview Position Chart: period selector matches Research's look.
- Performance tab: pill row still says `1W / 1M / 3M / 6M / 1Y / MAX`; switching periods updates the chart as before.
- KPI tiles on Performance tab still show correct day counts.

## Out of scope

- Aggregation toggle — TICKET-R2.
- Changing the actual period definitions (1Y still means 365 days, etc.).

## Notes

- Assumes the yfinance adapter can resolve `ONE_WEEK` to a 7-day daily-bar fetch. If yfinance's `period="1w"` is invalid, the adapter can fetch `period="1mo", interval="1d"` and trim to last 7 trading days inside the adapter — keep the domain enum clean.
- The `PerformancePeriod.MAX → ChartPeriod.FIVE_YEAR` semantic is preserved; the label is the only thing that changes.
- If `PerformancePeriod` is referenced in saved session state (e.g. `performance_period` key), back-compat reads should map old string values to the new `ChartPeriod` ones.
