# TICKET-A1 — Analytics: Performance tab v1

**Status:** IN_REVIEW
**Priority:** P1
**Estimated session length:** 2.5 – 3 hr
**Drafted by:** Vivek + Claude (chat 2026-05-08)
**Implemented by:** _pending_
**Depends on:** **TICKET-A0** (Analytics shell + `app/domain/analytics.py`), **TICKET-013** (Daily NAV snapshot service — hard prerequisite), TICKET-022a (`OhlcDataProvider`, `render_line_chart`), TICKETs 001 (domain), 006 (valuation), 007 (Streamlit shell)

> **After this ticket merges, the Performance tab fills in.** A KPI strip across the top (Period Return / Alpha / Max Drawdown / Annualised Volatility / Sharpe), a period selector and benchmark selector, a dual-line indexed-to-100 chart of portfolio vs benchmark, and a drawdown area chart below. All of it consumes `app/domain/analytics.py` from A0 and the NAV series from TICKET-013. **Render-only — no new persistence.**

---

## Problem

A0 delivered the empty Performance tab placeholder and the stats library it consumes. This ticket fills the tab with the actual answer to "how is my portfolio doing over time?" — the question Live Overview can't answer because Live Overview is a snapshot, not a series.

The page exists to answer five questions at a glance:

1. **What's my return over the selected period?** — Period Return KPI.
2. **Am I beating a passive index?** — Alpha vs Benchmark KPI.
3. **What's the worst drawdown I've sat through?** — Max Drawdown KPI + drawdown panel.
4. **How volatile am I?** — Annualised Volatility KPI.
5. **Is the return justifying the volatility?** — Sharpe Ratio KPI.

The chart layer (dual-line indexed-to-100 + drawdown area) gives the visual story behind the KPIs.

A1 is the most data-heavy of the five sub-tabs. It needs the full NAV reconstruction at scale (TICKET-013) and a benchmark series (`OhlcDataProvider`). That's why the handoff doc recommends implementing it last among A1–A5: the simpler tabs battle-test the foundation first.

---

## Architectural decisions implemented by this ticket

These were decided in the planning chat 2026-05-08 (see `docs/ANALYTICS_DRAFT_HANDOFF.md`).

### 1. Layout: input row → KPI strip → dual-line chart → drawdown panel

```
[ Period: 1W  1M  3M  6M  1Y  MAX     ]   [ Benchmark: [SPY ▼]                     ]

[ Period Return ]  [ Alpha ]  [ Max DD ]  [ Annualised Vol ]  [ Sharpe ]

[ Dual-line chart, height 360                                                       ]
[   Portfolio (indexed 100) — blue                                                  ]
[   Benchmark (indexed 100) — grey                                                  ]

[ Drawdown panel, height 180                                                        ]
[   Red area below zero, peak-to-trough %                                           ]
```

Period selector: `st.radio("Period", options=[...], horizontal=True, key="performance_period", index=3)` — `index=3` is `6M`.

Benchmark selector: `st.selectbox("Benchmark", options=["SPY", "EUNL", "None"], index=0, key="performance_benchmark")`.

KPI strip: 5 columns via `st.columns(5)`, each rendering an existing `MetricCard` component.

### 2. Period options and their meaning

```python
class PerformancePeriod(str, Enum):
    ONE_WEEK = "1W"
    ONE_MONTH = "1M"
    THREE_MONTH = "3M"
    SIX_MONTH = "6M"
    ONE_YEAR = "1Y"
    MAX = "MAX"
```

`MAX` means "from the earliest NAV snapshot available". The other periods are calendar-day windows (e.g. `1W` = today minus 7 calendar days; the NAV series is filtered to that window and the first/last NAVs become the indexing endpoints).

If the requested window starts before the first available NAV snapshot (e.g. user picks `1Y` but only has 6 months of NAV history), the tab renders normally using whatever data is available, and the period selector caption shows: `"1Y (showing 187 days available)"`. **No silent truncation without telling the user.**

### 3. Indexing-to-100 is computed at the service layer, not the chart

The dual-line chart is a generic two-series line chart. It does not know about indexing. The service module (`analytics_performance.py`) computes:

```python
portfolio_indexed = [(nav / portfolio_navs[0]) * Decimal(100) for nav in portfolio_navs]
benchmark_indexed = [(close / benchmark_closes[0]) * Decimal(100) for close in benchmark_closes]
```

— and hands two equal-length series to `render_line_chart`. **The chart component remains pure rendering**, no domain logic.

### 4. `render_line_chart` is extended to accept a second series

A1 is the first consumer of a multi-line line chart. The existing `render_line_chart(series, ...)` from TICKET-022a takes one series. **In scope for this ticket:** extend it to accept an optional second series:

```python
def render_line_chart(
    series: ChartSeries,
    *,
    secondary_series: ChartSeries | None = None,
    height: int = 300,
    primary_color: str = THEME_BLUE,
    secondary_color: str = THEME_GREY,
) -> None: ...
```

Backwards compatibility: every existing caller (TICKET-022b's mini chart on Live Overview, Research page) passes only `series` and gets the same single-line behaviour. **No existing call site changes.** The Live Overview tests and Research page tests must continue to pass unchanged.

If the implementer feels the chart component should grow into a list-of-series API instead (`series_list: list[ChartSeries]`), that's a refactor — out of scope for A1. Two-series-via-keyword-arg is the chosen shape; revisit when there's a third consumer.

### 5. Benchmark date alignment

Portfolio NAV is dated by trading-day-relevant timestamps from the NAV cache (TICKET-013). The benchmark (SPY / EUNL) returns daily closes from `OhlcDataProvider`. **The two series may not align day-for-day** — weekends, exchange holidays differ across markets.

The service layer aligns both series on the **portfolio NAV's date set** (the authoritative one for the user's portfolio). For each NAV date, look up the benchmark close on the same date; if missing, fall forward to the next available benchmark close (max 3 days forward). If still missing after 3 days, that NAV date is dropped from both series for that render. Document the choice in the docstring.

The KPI calculations and the chart use the same aligned series. They are computed once and reused. The service returns a single `PerformanceView` model wrapping both.

### 6. KPI definitions and colour rules

| KPI | Definition | Colour |
|---|---|---|
| **Period Return** | `(portfolio_navs[-1] / portfolio_navs[0]) - 1` as % | Green if > 0, red if < 0, neutral if 0 |
| **Alpha vs Benchmark** | `period_return_portfolio - period_return_benchmark` as percentage points | Green if positive, red if negative, **amber if abs(alpha) < 0.5pp** (essentially flat) |
| **Max Drawdown** | `analytics.max_drawdown(portfolio_navs)` as % | Always red (drawdown is by definition ≤ 0). If 0 (impossible-but-rendered for `MAX_DD == 0`), neutral |
| **Annualised Volatility** | `analytics.volatility_annualised(daily_returns(portfolio_navs))` as % | Neutral always (volatility isn't directionally good or bad) |
| **Sharpe Ratio** | `analytics.sharpe(daily_returns(portfolio_navs))` (rounded to 2 decimals) | Green if > 1, amber if 0–1, **neutral if < 0** (do not colour negative Sharpe red — see decision §11) |

`MetricCard` colour conventions follow the existing pattern in Live Overview / Tax Dashboard. Reuse, don't reinvent.

### 7. If benchmark is "None": Alpha shows `—`, others render normally

When `Benchmark == "None"`:
- The dual-line chart renders only the portfolio line (no second series passed to `render_line_chart`).
- The Alpha KPI renders `"—"` with a tooltip: `"Select a benchmark to see alpha"`.
- All other KPIs render normally (they're portfolio-only metrics).

This gives the user a "just my portfolio" view without forcing a benchmark choice. The `None` option is the third selectbox value, not a checkbox.

### 8. Drawdown panel uses Plotly directly (not `render_line_chart`)

The drawdown panel is an **area chart with red fill below zero**, not a line chart. `render_line_chart` doesn't fit. The implementer adds a new component:

```python
def render_drawdown_chart(
    series: ChartSeries,           # x = dates, y = drawdown fractions (≤ 0)
    *,
    height: int = 180,
) -> None: ...
```

— in `app/ui/components/charts.py`, alongside the existing chart functions. Style it consistent with the rest: same background, same axis font, red fill (use `CANDLE_DOWN` from `_chart_styles.py`), zero-line dashed.

This is the second new chart helper added by this ticket (alongside the `render_line_chart` extension). Both are in scope; both stay in `charts.py`.

### 9. Service layer: `app/services/analytics_performance.py`

```python
def get_performance_view(
    period: PerformancePeriod,
    benchmark: Literal["SPY", "EUNL", "None"],
    *,
    nav_service: NavService,                        # from TICKET-013
    ohlc_provider: OhlcDataProvider,                # from TICKET-022a
) -> PerformanceView: ...
```

Returns a frozen Pydantic model:

```python
class PerformanceView(BaseModel):
    model_config = ConfigDict(frozen=True)

    period: PerformancePeriod
    benchmark_label: Literal["SPY", "EUNL", "None"]

    # Aligned series (same dates, same length) — empty list if no data
    dates: list[date]
    portfolio_indexed: list[Decimal]                # indexed to 100
    benchmark_indexed: list[Decimal] | None         # None when benchmark == "None"
    portfolio_navs_raw: list[Decimal]               # un-indexed, for the drawdown calc

    # KPIs (None where uncomputable, e.g. alpha when benchmark is None)
    period_return_pct: Decimal | None
    alpha_pct: Decimal | None
    max_drawdown_pct: Decimal
    volatility_annualised_pct: Decimal | None       # None if < 2 returns
    sharpe: Decimal | None                          # None if < 2 returns or zero variance

    # Metadata for the "showing N days available" caption
    requested_period_days: int
    available_days: int
```

The service's job: fetch raw series, align dates, compute everything via `app/domain/analytics.py`, return the view. **Zero `streamlit` imports in the service.** The page imports the service and renders the view.

### 10. Empty / insufficient state handling

| Condition | Page behaviour |
|---|---|
| NAV cache returns empty (no snapshots yet) | Whole tab renders an `st.info("Performance data is being collected. Check back after the next NAV snapshot.")`. No KPIs, no charts. |
| NAV cache returns < 2 snapshots | Same as empty — period return is undefined with one point. |
| Benchmark fetch fails (`OhlcUnavailableError`) | Banner: `st.warning("Benchmark data unavailable: {reason}. Showing portfolio only.")`. Treat as `Benchmark == "None"` for this render. |
| Volatility / Sharpe uncomputable (e.g. < 2 returns, zero variance) | KPI card shows `"—"` with tooltip explaining why. **Not** a fake `0.0`. |
| `available_days < requested_period_days` (e.g. user picks 1Y but only 187 days exist) | Period selector caption: `"1Y (showing 187 days available)"`. Charts and KPIs render against what's available. |

### 11. Sharpe colour rule: neutral for negative, not red

A negative Sharpe means the portfolio underperformed the risk-free rate, but it's a *measurement*, not a *failure mode*. Colouring it red would conflate it with Period Return red (which means "you lost money"). Different signals deserve different colours.

Sharpe colour rule: `> 1` green, `0 ≤ s ≤ 1` amber, `< 0` neutral grey. The handoff doc was explicit: "Sharpe handles negative returns (no `—` placeholder — render the negative number with neutral colour)."

### 12. No persistence; selectors live in `st.session_state` only

`st.session_state.performance_period` and `st.session_state.performance_benchmark` persist *within a session*. They reset to defaults (`6M`, `SPY`) on app restart. **No JSON persistence** of the user's preferred period or benchmark in this ticket.

If the user wants their period sticky across sessions, that's a follow-up (likely Panel-driven, not a one-off persistence file).

### 13. No streamlit caching on the service call

`get_performance_view(period, benchmark, ...)` is called on every page render. It hits:
- The NAV cache (TICKET-013) — already disk-cached.
- `OhlcDataProvider.get_history(benchmark, ...)` — already service-level cached.

Both inputs are cached at their source. Adding `@st.cache_data` here would create a third cache layer with its own invalidation rules. **Not worth it for v1.** Profile first; if computing the view (which is pure math over already-cached arrays) becomes a bottleneck, then cache.

---

## Acceptance criteria

### `app/services/analytics_performance.py` — new module

- [ ] Defines `PerformancePeriod` enum with values `ONE_WEEK / ONE_MONTH / THREE_MONTH / SIX_MONTH / ONE_YEAR / MAX`.

- [ ] Defines frozen Pydantic model `PerformanceView` matching decision §9 exactly. All fields typed, no `Any`.

- [ ] Exports `get_performance_view(period, benchmark, *, nav_service, ohlc_provider) -> PerformanceView`.

- [ ] The function:
  - Calls `nav_service.get_nav_series(start_date=...)` to fetch raw NAVs over the requested period (use `MAX` to mean "no start_date filter").
  - If benchmark != `"None"`, calls `ohlc_provider.get_history(symbol_for(benchmark), period=..., interval=Daily)` and extracts close prices.
  - Aligns the two series on the portfolio NAV's date set per decision §5 (forward-fill up to 3 days; drop dates with no benchmark data after that).
  - Computes indexed-to-100 series at the service layer per decision §3.
  - Computes all KPIs via `app/domain/analytics.py`. Wraps `analytics.volatility_annualised` / `analytics.sharpe` in `try / except ValueError` and returns `None` for those KPIs when the underlying call raises.
  - Computes `max_drawdown_pct` via `analytics.max_drawdown(portfolio_navs_raw)` — **on the raw NAVs, not the indexed series** (drawdown is scale-invariant, but the contract is on raw NAVs for clarity).
  - Returns the populated `PerformanceView`.

- [ ] **Symbol mapping** is internal to the service: `SPY` → `"SPY"`, `EUNL` → `"EUNL.DE"` (Frankfurt-listed iShares Core MSCI World), `None` → no fetch. Keep the mapping in a module-level constant `_BENCHMARK_SYMBOLS: dict[str, str]`.

- [ ] **Layer rules:** no `import streamlit`, no direct adapter imports. Only domain (`app.domain.analytics`), services (`nav_service`, `OhlcDataProvider` via the port), and `pydantic`/`decimal`/`datetime`.

- [ ] **Date-alignment helper** is a private function `_align_on_dates(nav_series, benchmark_series, max_forward_fill_days=3)` with its own unit tests.

### `app/ui/pages/analytics.py` — fill the Performance tab

- [ ] Replace the existing `st.info("Coming in TICKET-A1")` with the full Performance tab body.

- [ ] **Input row** (top of the tab body):
  - Two columns: period selector on the left (~70%), benchmark selector on the right (~30%).
  - Period: `st.radio("Period", options=list(PerformancePeriod), horizontal=True, key="performance_period", index=3, format_func=lambda p: p.value)` (`index=3` = `SIX_MONTH`).
  - Benchmark: `st.selectbox("Benchmark", options=["SPY", "EUNL", "None"], index=0, key="performance_benchmark")`.
  - If `view.available_days < view.requested_period_days`, render `st.caption(f"{period.value} (showing {view.available_days} days available)")`.

- [ ] **KPI strip**:
  - Five columns via `st.columns(5)`.
  - Each column renders a `MetricCard` (existing component) with the value, format string, and colour from decision §6.
  - When a KPI value is `None`, the card shows `"—"` with the tooltip from decision §10.

- [ ] **Dual-line chart**:
  - Build a `ChartSeries` from `view.dates` + `view.portfolio_indexed`.
  - If `view.benchmark_indexed` is not `None`, build a second `ChartSeries` from same dates + `view.benchmark_indexed`.
  - Call `render_line_chart(portfolio_series, secondary_series=benchmark_series, height=360)`.

- [ ] **Drawdown panel**:
  - Compute `drawdown = analytics.drawdown_series(view.portfolio_navs_raw)` — at the **page** level (it's cheap and avoids bloating `PerformanceView` with a derived-but-not-shared field). If you prefer it in the service, that's also acceptable; pick one and document.
  - Build a `ChartSeries` from `view.dates` + drawdown values.
  - Call `render_drawdown_chart(series, height=180)`.

- [ ] **Empty state**: when `view.dates` is empty (cf. decision §10), render the empty-state info banner and skip everything else.

- [ ] **Benchmark fetch failure**: caught at the service boundary, surfaced via a flag on `PerformanceView` (e.g. `benchmark_fetch_error: str | None`). Page renders `st.warning(...)` with the error reason and proceeds as if `Benchmark == "None"` for this render.

### `app/ui/components/charts.py` — extend `render_line_chart`, add `render_drawdown_chart`

- [ ] `render_line_chart` gains a keyword-only parameter `secondary_series: ChartSeries | None = None` and `secondary_color: str = THEME_GREY` (constant from `_chart_styles.py`).

- [ ] When `secondary_series` is `None`, behaviour is byte-for-byte identical to before (verify by running the existing TICKET-022b tests unchanged).

- [ ] When `secondary_series` is provided, render both lines on the same axes. Both lines share x-axis values; assert that lengths match in a guard clause and raise `ValueError("primary and secondary series must have equal length")` if not.

- [ ] Add `render_drawdown_chart(series, *, height=180)`:
  - Plotly area chart with red fill (`CANDLE_DOWN`) below the zero line.
  - Zero-line dashed (`THEME_GREY`).
  - Y-axis as percentage (`tickformat=".1%"`).
  - Same background, font, padding as the existing chart family.

- [ ] Both functions return `None` (Streamlit chart functions render in place; matching the existing pattern).

### `tests/unit/services/test_analytics_performance.py` — new tests

- [ ] **Happy path**: build a fake `NavService` returning a known 30-day NAV series, a fake `OhlcDataProvider` returning a known SPY close series of the same dates; call `get_performance_view(SIX_MONTH, "SPY", ...)`; assert KPIs match hand-computed values, dates match, both indexed series start at exactly `Decimal(100)`.

- [ ] **Benchmark = "None"**: `view.benchmark_indexed is None`, `view.alpha_pct is None`, every other field populated.

- [ ] **Benchmark fetch failure**: fake provider raises `OhlcUnavailableError`; assert view returned with `benchmark_fetch_error` set, `alpha_pct is None`, portfolio fields populated.

- [ ] **Insufficient NAV data (0 snapshots)**: assert `view.dates == []`, all KPIs `None` or `Decimal(0)` per the contract in decision §10. Document the chosen contract.

- [ ] **Insufficient NAV data (1 snapshot)**: same — period return undefined, treated as "no data" per the contract.

- [ ] **Sharpe is negative**: construct returns where mean is negative; assert `view.sharpe < 0` (not `None`, not zero, not the absolute value).

- [ ] **Volatility uncomputable (1 return only)**: 2-NAV series produces 1 return; `analytics.volatility_annualised` raises; service catches; `view.volatility_annualised_pct is None`.

- [ ] **Date alignment forward-fill**: portfolio has NAV on Mon Tue Wed; benchmark has close on Mon Wed (Tuesday is a benchmark-market holiday); assert Tuesday's benchmark value is forward-filled from Monday. Provide concrete dates and values.

- [ ] **Date alignment drop**: portfolio has NAV on Mon Tue Wed Thu Fri; benchmark only has Mon and Fri (4-day gap > max_forward_fill_days=3); assert Tue–Thu are dropped from `view.dates` and from both indexed series. The KPIs are computed on the remaining 2 dates (or treated as insufficient — pick one and document).

- [ ] **Indexed-to-100 invariant**: for any non-empty NAV series, `view.portfolio_indexed[0] == Decimal(100)` exactly. Same for benchmark when present.

- [ ] **Max drawdown ≤ 0 invariant**: across hand-built test inputs, assert `view.max_drawdown_pct <= Decimal(0)` always. (This is the "drawdown panel never shows DD > 0" sanity check from the handoff doc.)

### `tests/unit/ui/test_performance_tab.py` — new tests

These are smoke tests; mock `streamlit` and the service.

- [ ] **Empty state**: mock `get_performance_view` to return a view with `dates == []`; assert `st.info` is called with the empty-state text; assert `render_line_chart` and `render_drawdown_chart` are not called.

- [ ] **Full render**: mock service to return a populated view; assert `st.columns(5)` is called once for the KPI strip; assert `render_line_chart` is called with the correct `secondary_series`; assert `render_drawdown_chart` is called once.

- [ ] **Benchmark = None render**: mock view with `benchmark_indexed is None`; assert `render_line_chart` is called with `secondary_series=None`; assert the Alpha card renders `"—"`.

- [ ] **Benchmark fetch error**: mock view with `benchmark_fetch_error == "rate limit"`; assert `st.warning` is called once with a message containing `"rate limit"`.

- [ ] **"Showing N days available" caption**: mock view where `available_days < requested_period_days`; assert the caption is rendered.

- [ ] **Sharpe colour for negative value**: mock view with `sharpe = Decimal("-0.42")`; assert the `MetricCard` for Sharpe is called with the neutral / grey colour, not red.

### `tests/unit/ui/components/test_charts_extension.py` — extension tests

- [ ] **Backwards compatibility**: existing `render_line_chart(series)` behaviour unchanged. Verify by calling without `secondary_series` and asserting the produced figure has exactly one trace (the test mocks `st.plotly_chart` and inspects the figure passed in).

- [ ] **Two-series case**: call with `secondary_series`; assert produced figure has exactly two traces with the expected colours.

- [ ] **Length-mismatch guard**: call with primary length 5 and secondary length 4; assert `ValueError` raised with the documented message.

- [ ] **`render_drawdown_chart` happy path**: call with a known series including positive, negative, and zero values (well — drawdown should never be positive, but test the guard); assert the figure's `fill="tozeroy"` (or whatever Plotly attribute makes the area shading work) is set, and the colour matches `CANDLE_DOWN`.

- [ ] **`render_drawdown_chart` zero-line dashed**: assert a dashed horizontal line at y=0 is part of the figure's shapes / annotations.

### Lints / quality

- [ ] `pytest` — all new tests pass; **all existing TICKET-022a/022b chart tests still pass unchanged** (this is the backwards-compatibility check for the `render_line_chart` extension).
- [ ] `ruff check .` — passes.
- [ ] `mypy app/` — passes (strict on `app/services/analytics_performance.py`).
- [ ] `lint-imports` — passes:
  - `app/services/analytics_performance.py`: imports `app.domain.analytics`, `app.domain.market_data` (for `OhlcDataProvider`), `app.services.nav_service`, `pydantic`, `decimal`, `datetime`. **No `streamlit`, no adapter imports.**
  - `app/ui/pages/analytics.py`: imports `app.services.analytics_performance`, `app.ui.components.charts`, `app.ui.components.metric_card`, `app.ui.wiring`, `streamlit`.
  - `app/ui/components/charts.py`: import graph unchanged (still `plotly`, `_chart_styles`).

### State updates (per `AGENTS.md` Phase 8b)

- [ ] `docs/SESSION_LOG.md` appended with a new entry.
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-A1 → IN_REVIEW under "In review 👀").
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-A1 row → IN_REVIEW).
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.

---

## Files created

```
app/services/analytics_performance.py
tests/unit/services/test_analytics_performance.py
tests/unit/ui/test_performance_tab.py
tests/unit/ui/components/test_charts_extension.py
```

## Files modified

```
app/ui/pages/analytics.py               ← Performance tab body fills in
app/ui/components/charts.py             ← render_line_chart gains secondary_series; render_drawdown_chart added
docs/PROJECT_STATE.md                   ← TICKET-A1 → IN_REVIEW
docs/SESSION_LOG.md                     ← new session entry
docs/TICKETS/BACKLOG.md                 ← TICKET-A1 row → IN_REVIEW
```

## Files NOT to modify

- `app/domain/analytics.py` — locked by TICKET-A0. **If a needed primitive is missing, stop and report; do not add it inline in the service.**
- `app/services/nav_service.py` — TICKET-013's surface. Read-only consumer here.
- `app/services/market_data.py` — TICKET-022a's surface. Read-only consumer here.
- `app/ui/pages/overview.py`, `app/ui/pages/research.py` — they depend on the existing `render_line_chart` signature; their tests are the regression guard for backwards compatibility.
- `app/ui/pages/manage.py`, `app/ui/pages/tax.py` — out of scope.
- `pyproject.toml` / `requirements.txt` — no new dependencies.

---

## Out of scope

- **Time-weighted vs money-weighted return distinction.** Current Period Return is point-to-point on the NAV series, which is closest to time-weighted but conflates contributions/withdrawals when there are intra-period flows. **A1.x follow-up.**
- **Contribution-to-return per position.** Decomposing Period Return into per-position attribution is its own page-sized feature. **A1.x follow-up.**
- **Realised-vs-unrealised split** of the gain figure. The Period Return is total return; splitting realised from unrealised needs FIFO replay over the window. **A1.x follow-up.**
- **Multiple benchmarks at once** (e.g. "compare to SPY and EUNL simultaneously"). The chart component will eventually need a list-of-series API for this, but A1 is two-series-via-keyword-arg. **Future.**
- **Custom benchmark** (user-typed ticker). The selectbox is fixed to `SPY / EUNL / None`. Extending it to a free-form ticker selector adds validation complexity (resolver round-trip, error states) for marginal value at v1.
- **Persistence** of the user's selected period or benchmark across app restarts. In-session only.
- **Sharpe with non-zero risk-free rate** in the UI. The library supports it; the page passes `risk_free=Decimal(0)`. Adding a "risk-free rate" input field is overkill for v1.
- **Rolling Sharpe / rolling volatility chart.**
- **Logarithmic y-axis** on the dual-line chart.
- **Annotations on the chart** (e.g. "you bought NVDA here"). Lot-event overlays are their own feature.
- **CSV export** of the performance series.
- **Mobile-specific layout.**
- **`@st.cache_data` on the service call** (see decision §13).

---

## Test cases (manual review checklist for the PR)

- [ ] Open Analytics → Performance tab. Page renders without errors.
- [ ] Default state: period `6M`, benchmark `SPY`. KPIs populate within the same render that draws the page.
- [ ] All five KPI cards show numeric values (no `"—"`) given a NAV series with > 1 year of data and a working SPY fetch.
- [ ] Switch period to `1W`. KPIs and both charts update. The dual-line chart x-axis tightens to ~7 days.
- [ ] Switch period to `MAX`. Charts span the full NAV history. Caption (if shown) reads `"MAX (showing N days available)"`.
- [ ] Switch benchmark to `EUNL`. Second line on the dual-line chart updates; Alpha KPI recomputes.
- [ ] Switch benchmark to `None`. Second line disappears from the chart; Alpha card shows `"—"` with tooltip.
- [ ] Switch back to `SPY`. Second line returns. No flicker, no stale value.
- [ ] Drawdown panel: every visible value is at or below the zero line. No part of the red area extends above zero. (This is the "drawdown panel never shows DD > 0" sanity check.)
- [ ] Period switch refetches both series — verified by checking that the timestamps on the chart x-axis change (or by the network panel if you want to be thorough).
- [ ] Sharpe negative case: artificially induce a negative-return period (e.g. force `1W` to a known-bad week if data permits) → Sharpe shows the negative number with neutral colour, not red, not `"—"`.
- [ ] No regressions on Live Overview's mini chart (Research page mini chart) — backwards-compatibility check for the `render_line_chart` extension.
- [ ] No regressions on the Analytics shell: other four tabs still show `"Coming in TICKET-AX"`.
- [ ] Refresh the app. Period and benchmark reset to defaults (`6M` / `SPY`) — the in-session-only contract.

---

## Notes (architectural and methodological — for future AI sessions)

### Why benchmark date alignment uses portfolio dates as authoritative

The portfolio NAV's date set is authoritative because it's grounded in user actions: a NAV exists on a day because there's a snapshot for that day. Aligning the other way — using benchmark dates as authoritative and forward-filling the portfolio NAV — would mean inventing portfolio NAVs on dates the portfolio didn't snapshot. That's a fabrication, not an alignment.

The 3-day forward-fill for missing benchmark closes is a small lie of convenience: "we assume the benchmark didn't move much over the long weekend." For typical benchmarks (SPY, EUNL) closed for short market holidays, this is harmless. If the gap exceeds 3 days (closures, data outage), we drop the date entirely rather than fabricate further.

### Why the chart component grows by keyword arg, not by list-of-series

Three options for a multi-series API:

1. **Keyword arg `secondary_series`** (chosen). Simple, backwards-compatible, two consumers max before revisit.
2. `series_list: list[ChartSeries]`. More flexible but breaks every existing call site, requires migrating colour-per-series logic, larger PR.
3. New function `render_dual_line_chart`. Clean separation, but doubles the chart-component count without much benefit, and the second function would share 80% of code with the first.

Option 1 is the smallest, most surgical change. When the third consumer arrives (probably a "compare two stocks" feature in Research), that's the trigger to refactor to option 2. Not before.

### Why the drawdown helper isn't called from the service module

`analytics.drawdown_series` is called from the page, not the service. Two reasons:

1. **It's derivable from `portfolio_navs_raw`** (already on the view), so it would be redundant data on `PerformanceView`.
2. The service should return *facts*, not *visualisations*. Drawdown the chart is a presentation concern; drawdown the KPI (`max_drawdown_pct`) is a fact, and that's on the view.

The trade-off: the page calls a domain function directly. That's an exception to the "page → service → domain" rule. We accept it because the alternative is a `derived: list[Decimal]` field on the view that exists solely to feed one chart. Document the exception in the page module's docstring.

### Why no `@st.cache_data` on the service

Two layers of caching already protect us:

1. **NAV cache** (TICKET-013) — disk-cached, cheap to read.
2. **OhlcDataProvider cache** (TICKET-022a) — service-level cached.

The service's job between those caches and the page is pure math: align dates, compute returns, compute KPIs. On a 5-year MAX render with ~1,260 data points, that's microseconds. Adding `@st.cache_data` would mean defining cache key semantics (period + benchmark? + nav-snapshot-version? + ohlc-cache-version?), and the invalidation rules become the bug. Premature.

If the page render becomes slow in practice, profile first. The bottleneck is more likely to be the `OhlcDataProvider` first-fetch than the math.

### How A1 closes out the analytics page

A1 is the last sub-tab to land per the recommended order. Once it merges, the Analytics page is fully populated and the `app/services/analytics_*` family is complete. At that point, a future ticket can consider extracting shared bits (e.g. the period selector, if it appears in 2+ tabs) into reusable components — but only after seeing the actual repetition. **No speculative extraction.**
