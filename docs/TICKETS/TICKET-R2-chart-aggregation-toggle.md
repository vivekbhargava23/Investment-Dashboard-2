# TICKET-R2 — Daily/Weekly/Monthly aggregation toggle on chart pages

**Status:** QUEUED
**Priority:** MEDIUM
**Estimated session length:** 1 hr
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Milestone:** UI polish

---

## Problem

Chart aggregation today is hardcoded in `services/market_data.py::_AGGREGATION` by period: 1Y/2Y → weekly, 5Y → monthly, others → daily. The user has no way to say "show me 1Y as daily" or "show me 6M as weekly", which are common analyst views. Each page (Research, Overview Position Chart, Analytics → Technicals) hits the same hardcoded mapping.

## Solution

Expose aggregation as a user-controlled parameter alongside the period selector. Default keeps the current behaviour so nothing regresses if the user doesn't touch the toggle.

### Domain / service changes

`services/market_data.py::get_ohlc_history` gains an optional `freq: AggregationFreq | None = None` parameter:

```python
def get_ohlc_history(
    ticker: str,
    period: ChartPeriod,
    *,
    provider: OhlcDataProvider,
    freq: AggregationFreq | None = None,  # None → use _AGGREGATION default
) -> OhlcSeries:
```

Cache key becomes `(ticker, period, freq)`. When `freq is None`, the lookup falls back to `_AGGREGATION[period]` (existing behaviour).

### UI component

Add `render_aggregation_toggle(key, period) -> AggregationFreq | None` in `app/ui/components/period_selector.py`:

- Returns `None` (= default) when "Auto" is selected.
- Returns one of `"day" | "week" | "month"` for explicit selection.
- Hides options that don't make sense for the period (e.g. `month` is hidden on 1D / 5D / 1M).

```python
def render_aggregation_toggle(key: str, period: ChartPeriod) -> AggregationFreq | None: ...
```

### Page wiring

Three pages get a small segmented control rendered next to the period selector:

- `app/ui/pages/research.py` — top input row, after `render_period_selector`.
- `app/ui/pages/overview.py` (Position Chart section, `:341`) — same.
- `app/ui/pages/analytics.py` (`_render_technicals_tab`) — between period selector and chart.

Each call site passes the toggle result through to `get_ohlc_history(..., freq=selected_freq)`.

## Acceptance criteria

- [ ] `get_ohlc_history` accepts `freq` and respects it (None = current default behaviour).
- [ ] Cache key includes `freq` so explicit and auto views don't collide.
- [ ] `render_aggregation_toggle` shows "Auto / Day / Week / Month" with options hidden where they don't make sense.
- [ ] Research, Overview Position Chart, and Technicals tab all render the toggle.
- [ ] Unit tests: `get_ohlc_history(freq="week")` on a 6M period returns a weekly-aggregated series.
- [ ] Unit tests: `freq=None` matches today's behaviour exactly.
- [ ] All tests pass; ruff / mypy / lint-imports clean.

### Manual smoke

- Research, `AAPL`, period 1Y: default shows weekly (current behaviour). Switching to "Day" shows daily bars. Switching to "Month" shows ~12 bars.
- Overview Position Chart: same toggle works on any owned ticker.
- Technicals tab: toggle persists per ticker; SMA overlays recompute against the new bar set.

## Out of scope

- Rangebreaks behaviour — TICKET-R1 owns that.
- Quarterly aggregation — not requested.
- Changing the `_AGGREGATION` defaults — only adding override.

## Notes

- `AggregationFreq` is already defined in `domain/market_data.py:108`.
- Cache size grows ~3x for periods where users will plausibly toggle. Acceptable for an in-memory session cache; revisit if memory becomes an issue.
- Assumes overlays (50/200 DMA, RSI on Technicals) are computed against the *aggregated* series. If the user switches to weekly, the SMA windows still mean "50 bars" — document this in the UI caption or rename to "50-period MA" inside Technicals when freq != "day".
