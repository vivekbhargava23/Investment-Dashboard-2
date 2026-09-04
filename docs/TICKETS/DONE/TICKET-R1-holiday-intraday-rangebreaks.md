# TICKET-R1 — Holiday and intraday rangebreaks for OHLC charts

**Status:** IN_PROGRESS
**Priority:** MEDIUM
**Estimated session length:** 1 hr
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Milestone:** UI polish

---

## Problem

OHLC candlestick charts (`app/ui/components/charts.py::render_candlestick`) currently strip Saturday–Sunday gaps via `_weekend_rangebreaks()`, but two gap classes remain visible:

1. **Holiday gaps on daily-bar periods (1M, 3M, 6M).** Christmas, Thanksgiving, Good Friday, Tag der Deutschen Einheit, etc. render as blank candle slots on charts for US and DE-listed tickers.
2. **Overnight gaps on the 1D intraday chart.** The 5-minute bars span ~6.5 trading hours, but the x-axis renders the ~17 overnight hours, producing a long visual gap each session boundary.

The 1Y / 2Y / 5Y / YTD charts already aggregate to weekly/monthly bars (`services/market_data.py::_AGGREGATION`), so they swallow these gaps. The fix targets only the daily and intraday bar paths.

## Solution

Add two range-break helpers next to `_weekend_rangebreaks` in `charts.py`:

- `_holiday_rangebreaks(series: OhlcSeries) -> list[dict]` — returns Plotly `rangebreaks` entries of the form `{"values": [iso_date, ...]}` for each missing trading day inside the series window. Compute "missing" as: the set of weekdays between `series.bars[0].timestamp.date()` and `series.bars[-1].timestamp.date()` minus the set of dates that actually appear in `series.bars`. Plotly accepts ISO date strings.
- `_intraday_overnight_rangebreaks(series: OhlcSeries) -> list[dict]` — returns `[{"bounds": [end_hour, start_hour], "pattern": "hour"}]` where `end_hour` and `start_hour` are derived from the min/max bar `hour` observed in the series (use UTC; default to `[22, 13]` covering the NYSE/XETRA overlap if detection is ambiguous). FX tickers (currency=Currency in `_FX_CANONICAL`) skip this — they trade 24h.

Wire both into `render_candlestick` (and `render_line_chart` / `render_drawdown_chart` for consistency):

```python
if _needs_weekend_rangebreaks(series):
    breaks = _weekend_rangebreaks() + _holiday_rangebreaks(series)
    layout["xaxis"]["rangebreaks"] = breaks
elif series.period.is_intraday:
    layout["xaxis"]["rangebreaks"] = _intraday_overnight_rangebreaks(series)
```

The "weekend" branch already gates on daily-bar spacing, so it's the right entry for adding holidays.

## Acceptance criteria

- [ ] `_holiday_rangebreaks` and `_intraday_overnight_rangebreaks` added to `charts.py` with unit tests in `tests/unit/ui/test_charts.py`.
- [ ] Daily candlestick views (1M / 3M / 6M) show no blank slots for actual non-trading dates inside the window.
- [ ] 1D intraday chart shows no overnight gap; bars flow contiguously across session boundaries.
- [ ] FX tickers (`EURUSD=X`, etc.) on a 1D view keep continuous bars (no intraday rangebreaks applied).
- [ ] Aggregated views (1Y/2Y/5Y/YTD) unchanged — still skip rangebreaks entirely.
- [ ] All tests pass; ruff / mypy / lint-imports clean.

### Manual smoke

- Research page, ticker `AAPL`, period `3M`: no blank slots on Christmas Day 2024, July 4 2024.
- Research page, ticker `RHM.DE`, period `6M`: no blank slot for German Unity Day / Easter Monday.
- Research page, ticker `AAPL`, period `1D`: bars flow Mon→Fri without overnight gap.
- Research page, ticker `EURUSD=X`, period `1D`: bars are continuous (no rangebreaks applied).

## Out of scope

- Per-exchange holiday calendars from `pandas_market_calendars` (heavier dependency; the "missing weekdays in window" heuristic is enough for v1).
- Aggregation behaviour for 1Y+ periods — already handled in `services/market_data.py`.
- A user-facing Daily/Weekly/Monthly toggle — see TICKET-R2.

## Notes

- Assumes `OhlcSeries.bars` is sorted ascending (validated by the model already).
- Assumes intraday timestamps are UTC (yfinance adapter normalises to UTC at `yfinance_adapter.py:373`).
- The "missing weekdays" derivation is intentionally based on the data itself rather than a calendar lookup. This keeps the domain layer pure and avoids adding a holiday-table dependency.
