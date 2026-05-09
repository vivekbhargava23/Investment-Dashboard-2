# TICKET-A3 — Analytics: Technicals tab v1

**Status:** IN_REVIEW
**Priority:** P1
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-09)
**Implemented by:** Claude Code (2026-05-09)
**Depends on:** TICKET-A0 (analytics page shell + `app/domain/analytics.py` with `sma` and `rsi`), TICKET-022a (`render_candlestick`, `OhlcDataProvider` port + adapter, `_chart_styles.py`), TICKET-006 (live positions for the ticker selector universe)

> **After this ticket merges, the Technicals sub-tab on the Analytics page renders a per-position candlestick chart with 50/200-day moving average overlays, an RSI panel below it, a signal badge strip, and a live-price badge.** This is the third user-visible analytics surface and the first consumer of `analytics.sma` and `analytics.rsi` from A0.

---

## Problem

For a position the user already holds, two practical questions come up between holding and selling: *"Is this position currently extended above its trend?"* and *"Is the recent move overbought or oversold?"* The Live Overview answers neither — it shows weight and unrealised gain, not trend or momentum. The Research page (TICKET-022b) shows clean candlesticks but no indicator overlays, because Research is for evaluating tickers (owned or not) before buying, not for analysing what's already in the book.

This ticket adds the Technicals sub-tab, replacing the `st.info("Coming in TICKET-A3")` placeholder from A0. The tab is **owned-positions only** (a deliberate distinction from Research) and adds three things Research doesn't:

1. **Trend overlays** — 50- and 200-day SMAs on the candlestick.
2. **Momentum panel** — RSI(14) with reference bands at 30 and 70.
3. **Signal badges** — at-a-glance summary of trend state, cross events, RSI level, and live price.

The user's portfolio is currently 13 positions; the design must work for any owned position with sufficient OHLC history, and degrade gracefully for positions where history is shorter than the indicator's lookback.

---

## Architectural decisions implemented by this ticket

### 1. Selector universe is "live positions only" — and explicitly NOT "any ticker"

The ticker selector lists every position with `qty > 0`, fetched via `compute_live_positions(...)`. Closed lots and unowned tickers are excluded.

This is the load-bearing distinction between Technicals and Research:

| Surface | Universe | Purpose |
|---|---|---|
| **Research page** (022b) | Any ticker (owned or not) | Pre-trade evaluation, simulate-buy handoff |
| **Technicals tab** (this ticket) | Owned positions only | Post-trade analysis: am I still in a healthy trend? |

If a future need arises to run technicals on an unowned ticker, that's a Research-page enhancement, not a Technicals-tab enhancement. **The implementation agent must not add a "search any ticker" affordance to this tab** — that would dissolve the distinction and produce two pages doing the same thing.

The selector is a single `st.selectbox`, alphabetical by ticker symbol. Selection persists in `st.session_state["technicals_ticker"]` so switching tabs and back doesn't reset it. If no positions are held, the tab shows `st.info("No open positions to analyse. Add a position via Manage Portfolio.")` and renders nothing else.

### 2. Period selector reuses the Research-page pattern, not a new one

Period options: `1M / 3M / 6M / 1Y / 2Y / 5Y` as `st.radio` horizontal. Default `6M`. The exact label list and `_PERIOD_LABELS` lookup is reused from `app/ui/pages/research.py` — extract it into `app/ui/components/period_selector.py` if the implementer judges the duplication worth eliminating (in scope for this ticket; second consumer triggers the extraction). If the existing labels list differs from this spec, defer to the existing list and document the divergence in the session log.

The period maps to a number of trading days for the OHLC fetch. The `OhlcDataProvider` already handles the period→days mapping; no new mapping is introduced here.

Selection persists in `st.session_state["technicals_period"]`, default 6M.

### 3. The 50/200 DMA "insufficient history" rule is explicit and visible

Both the SMA overlays and the related signal badges have a hard requirement: SMA(50) requires at least 50 closes; SMA(200) requires at least 200. The chart is shown over a user-selected period that may be shorter than 200 days, and the position itself may have been held for less than 200 trading days.

Two distinct cases must be handled:

**Case A — period shorter than the SMA lookback.** Example: user picks 1M (≈21 trading days) on a long-held position. SMA(50) and SMA(200) cannot be computed within the visible window. The OHLC fetch must request enough historical data to compute the SMA *before* the visible window starts, then the line is drawn across the visible window using SMA values seeded from earlier data. The fetch buffer is `max(SMA_LONG, 200) + visible_period_days`.

**Case B — position has fewer total trading days than the SMA lookback.** Example: a position bought 30 days ago. No amount of buffer fetches enough history; the SMA(50) line cannot be drawn anywhere in the chart. In this case:

- The 50 DMA line is **not rendered** on the chart (no fake / partial line).
- The "Above 50 DMA" badge is **rendered with state `insufficient history`** (greyed out, label reads `50 DMA: insufficient history (X / 50 days)`).

The badge is rendered, not hidden, deliberately. Hiding it would make the absence invisible — a silent failure mode where the user sees four badges and assumes that's all the analysis. Showing the disabled badge tells the user *this analysis exists but can't be computed yet*, which is honest.

The same rule applies to SMA(200) and to the Golden Cross / Death Cross badges (which require both SMAs).

### 4. RSI is unconditional (always renders), but is robust to short history

RSI(14) needs 15 closes minimum. For any owned position with fewer than 15 days of close history, the RSI panel renders with the message `"Insufficient history for RSI (need 15 days, have X)"` instead of a chart. No partial/seeded RSI is rendered — RSI on <14 days is meaningless.

For the typical case (position held > 15 days), the RSI panel always renders. Unlike the SMAs, RSI doesn't need a long buffer — Wilder smoothing stabilises within `period × 5 ≈ 70` days, which is well within any normal selected period. The fetch buffer for the RSI panel is `period_days + 70` to ensure stable values across the visible window.

### 5. Signal badges — exact set, exact states

Five badges, in this order, rendered as a horizontal strip at the top of the tab:

| # | Badge | States | Colour |
|---|---|---|---|
| 1 | Trend (50 DMA) | `Above 50 DMA` / `Below 50 DMA` / `50 DMA: insufficient history (X/50)` | green / red / grey |
| 2 | Trend (200 DMA) | `Above 200 DMA` / `Below 200 DMA` / `200 DMA: insufficient history (X/200)` | green / red / grey |
| 3 | Cross | `Golden Cross (N days ago)` / `Death Cross (N days ago)` / `No recent cross` / `insufficient history` | green / red / neutral / grey |
| 4 | RSI | `RSI 67 (overbought)` / `RSI 28 (oversold)` / `RSI 52 (neutral)` / `insufficient history` | red / green / neutral / grey |
| 5 | Live | `Live: $123.45 (+12.3% today)` / `Live: $123.45 (—)` if no day-open available / `unavailable` | green / red / neutral / grey |

Badge thresholds:

- **Cross:** "Golden Cross" if SMA(50) crossed above SMA(200) within the last 90 trading days; "Death Cross" if below. "No recent cross" if no cross in the last 90 days but both SMAs exist. The 90-day window is a constant `RECENT_CROSS_WINDOW = 90` in `app/services/analytics_technicals.py`.
- **RSI level:** `> 70` → "overbought" (red); `< 30` → "oversold" (green, contrarian buy signal); else "neutral" (grey).
- **Live price:** uses the same `PriceFeed` port already wired for Live Overview. The `(+12.3% today)` is computed as `(live_price - day_open) / day_open` if `day_open` is available from the OHLC provider's most recent bar; otherwise the percent is omitted (em-dash). Currency in the badge follows the position's *native* currency (USD for AAPL, EUR for RHM.DE), not the EUR-converted display value — the user is looking at the chart in the native currency, the badge must match.

The badge component is the existing one used elsewhere on the dashboard. If a "disabled / grey" state doesn't already exist on it, add it as a new variant in this ticket (in scope, second consumer of disabled badges after the diversification bucket grey state from A2).

### 6. Chart layout — candlestick on top, RSI panel below

Two stacked Plotly figures, not one combined figure with subplots. Reasoning: the existing `render_candlestick` helper from TICKET-022a returns a complete figure; combining into a subplot grid would require either (a) refactoring `render_candlestick` to optionally return a trace instead of a figure, or (b) duplicating its candlestick-construction logic. Both are larger changes than this ticket warrants. Two stacked figures with synchronised x-axes is the lower-cost path.

Layout:

```
┌─────────────────────────────────────────────────────────┐
│ Ticker: [AAPL ▾]    Period: ( ) 1M ( ) 3M (•) 6M ...    │
├─────────────────────────────────────────────────────────┤
│ [Above 50 DMA] [Above 200 DMA] [Golden Cross 12d ago]   │
│ [RSI 52 neutral] [Live: $187.42 (+1.2% today)]          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│         Candlestick + 50 DMA (amber) + 200 DMA (blue)   │
│         (height ~400px, render_candlestick + overlay)   │
│                                                         │
├─────────────────────────────────────────────────────────┤
│         RSI panel (height ~80px, line + 30/70 bands)    │
└─────────────────────────────────────────────────────────┘
```

The candlestick figure is built by extending `render_candlestick` with an optional `overlays` parameter — a list of `(name, x_values, y_values, style)` tuples. The function renders the candlesticks then adds each overlay as a `Scatter` trace. Adding overlay support to `render_candlestick` is in scope for this ticket; A3 is the first consumer of overlays. The signature change must be backwards-compatible: existing callers (Live Overview chart from TICKET-022b) pass no `overlays` and behaviour is unchanged.

The RSI panel is a new helper `render_rsi_panel(dates, rsi_values, *, height=80)` in `app/ui/components/charts.py`. It renders a Plotly line chart with reference dashed lines at 30 and 70 and a shaded grey band between them. No candlestick, no overlays — single trace.

### 7. Chart styles come from `_chart_styles.py`, not inline

Two new style constants are added to `app/ui/components/_chart_styles.py`:

- `SMA_50_STYLE` — colour amber, dash `"dash"`, width 1.5
- `SMA_200_STYLE` — colour blue, dash `"dash"`, width 1.5

The exact hex values follow the existing palette in that file. If the existing palette doesn't include an amber that contrasts with the candlestick reds and greens, the implementer picks one and documents the choice in the session log.

The RSI reference bands (30 / 70) and the shaded neutral band use existing neutral / accent constants from `_chart_styles.py`. No new constants needed for those.

### 8. Service-layer module: `app/services/analytics_technicals.py`

```python
def build_technicals_view(
    *,
    ticker: str,
    period: str,                          # one of the period labels
    repo: TransactionRepository,
    price_feed: PriceFeed,
    ohlc: OhlcDataProvider,
    as_of: date,
) -> TechnicalsView: ...
```

`TechnicalsView` is a frozen Pydantic model with:

- `ticker: str`
- `name: str` — display name for the chart title (looked up via the existing position metadata, same as Live Overview uses)
- `currency: Currency` — the position's native currency, drives the live-price badge formatting
- `visible_dates: list[date]` — date axis for both charts (after intersection with available OHLC)
- `ohlc: list[Bar]` — open/high/low/close/volume per visible date
- `sma_50: list[Decimal | None]` — aligned with `visible_dates`; `None` where SMA(50) cannot be computed
- `sma_200: list[Decimal | None]` — same shape
- `rsi: list[Decimal] | None` — aligned with `visible_dates`; `None` (the whole field) if total history < 15 closes
- `live_price: Decimal | None` — from `PriceFeed`; `None` on fetch failure
- `day_open: Decimal | None` — most recent OHLC bar's open
- `signals: TechnicalsSignals` — derived badge states (see below)
- `total_history_days: int` — total close-history days available; used for the "X / 50" insufficient-history label

`TechnicalsSignals` is a frozen Pydantic model with:

- `trend_50: Literal["above", "below", "insufficient"]`
- `trend_200: Literal["above", "below", "insufficient"]`
- `cross: Literal["golden", "death", "none", "insufficient"]`
- `cross_days_ago: int | None` — only set when `cross in {"golden", "death"}`
- `rsi_level: Literal["overbought", "oversold", "neutral", "insufficient"]`
- `rsi_value: Decimal | None` — only set when `rsi_level != "insufficient"`
- `live_change_pct: Decimal | None` — `None` if `live_price` or `day_open` is missing

The service:

1. Validates ticker is in the live universe (qty > 0). Raises `ValueError("Ticker T not in open positions")` if not — the UI catches this and re-renders the empty state.
2. Fetches OHLC with buffer = `period_days + 200` (ensures SMA(200) can be seeded for any visible window where total history allows it).
3. Computes `sma_50`, `sma_200`, `rsi` over the *full fetched range* using `analytics.sma` and `analytics.rsi`.
4. Slices to the visible period for charting.
5. Computes signal states based on the most recent visible day's values.
6. Detects recent crosses by scanning the last 90 trading days of the (sma_50, sma_200) pair for sign changes of `sma_50 - sma_200`.
7. Fetches live price + recent day-open for the live badge.
8. Returns `TechnicalsView`.

If OHLC fetch fails (network error, unsupported ticker), the service raises `OhlcUnavailable("ticker T: <reason>")` and the UI renders an error banner — no partial chart, no silent fallback to a flat line.

### 9. Cross detection algorithm — pure function in `app/domain/analytics.py`

```python
def detect_recent_cross(
    sma_short: list[Decimal | None],
    sma_long: list[Decimal | None],
    *,
    lookback: int = 90,
) -> tuple[Literal["golden", "death", "none"], int | None]: ...
```

- Computes `diff[i] = sma_short[i] - sma_long[i]` for indices where both are non-None.
- Scans the last `lookback` valid indices for a sign change.
- Returns `("golden", days_ago)` if the most recent change was negative-to-positive; `("death", days_ago)` if positive-to-negative; `("none", None)` if no change in the lookback.
- If fewer than 2 valid indices exist, raises `ValueError("insufficient SMA history for cross detection")` — the service catches this and sets `cross = "insufficient"` rather than propagating.
- Pure function, zero I/O, lives in `app/domain/analytics.py` alongside `sma` and `rsi`.

This is a primitive on SMA outputs; per A0's rule it belongs in the domain layer.

### 10. No new persistence, no new caching

OHLC fetches are cached at the adapter level (existing behaviour from TICKET-022a). Live price fetches are cached at the adapter level (existing behaviour from TICKET-006). No new cache layer. No `st.session_state` writes beyond the selector state (`technicals_ticker`, `technicals_period`).

---

## Acceptance criteria

### `app/domain/analytics.py` — additions

- [ ] New function `detect_recent_cross(sma_short, sma_long, *, lookback=90)` with signature exactly as in decision §9.
- [ ] Docstring states: input shape (`Decimal | None` per index for both lists, must be same length), `lookback` semantics, return tuple semantics, edge cases (fewer than 2 valid indices → `ValueError`; no cross in lookback → `("none", None)`).
- [ ] "Days ago" is counted from the most recent index, not absolute calendar — index distance from end of the input lists.
- [ ] If both inputs have all-None or empty → `ValueError`.
- [ ] Domain layer rules: zero I/O, `Decimal` only.

### `app/services/analytics_technicals.py` — new module

- [ ] Single public function `build_technicals_view(...)` with signature in decision §8.
- [ ] Frozen Pydantic `TechnicalsView` and `TechnicalsSignals` models with exact fields in decision §8.
- [ ] Module-level constants: `RECENT_CROSS_WINDOW = 90`, `RSI_OVERBOUGHT = Decimal(70)`, `RSI_OVERSOLD = Decimal(30)`, `SMA_SHORT_PERIOD = 50`, `SMA_LONG_PERIOD = 200`, `RSI_PERIOD = 14`.
- [ ] Custom exception `OhlcUnavailable(Exception)` with the underlying reason in `args[0]`.
- [ ] Validates the ticker is in the live universe (qty > 0); raises `ValueError` otherwise.
- [ ] OHLC fetch buffer = `period_days + max(SMA_LONG_PERIOD, 200)`.
- [ ] Indicator computation runs on the full fetched range, then slicing to the visible period happens for the chart-data fields.
- [ ] Signal states derived from the most recent visible day's values per the rules in decisions §3 / §4 / §5.
- [ ] Live-price `change_pct` is `None` when `day_open` is missing (no fallback to 0%).

### `app/ui/components/charts.py` — modifications

- [ ] `render_candlestick` extended with optional `overlays: list[Overlay] | None = None` parameter. `Overlay` is a typed dict / dataclass with fields `name: str`, `x: list[date]`, `y: list[Decimal | None]`, `style: dict`. Existing callers (Live Overview) pass nothing; behaviour unchanged.
- [ ] New helper `render_rsi_panel(dates: list[date], rsi: list[Decimal], *, height: int = 80) -> None` per decision §6.
- [ ] RSI panel: line trace + dashed reference at 30 + dashed reference at 70 + shaded grey band between 30 and 70. No legend (one trace).
- [ ] Both helpers call `st.plotly_chart(..., use_container_width=True)` internally.

### `app/ui/components/_chart_styles.py` — additions

- [ ] `SMA_50_STYLE` and `SMA_200_STYLE` constants per decision §7.

### `app/ui/components/period_selector.py` — new module (optional extraction)

- [ ] If extracted: `_PERIOD_LABELS` constant + `render_period_selector(key: str, default: str = "6M") -> str` helper. Both `research.py` and `analytics.py` (Technicals tab) import from here.
- [ ] If not extracted: the implementer inlines the period selector in `_render_technicals_tab` and documents the decision in the session log. Either path is acceptable; the criterion is "no behaviour change in the Research page period selector."

### `app/ui/pages/analytics.py` — modifications

- [ ] Replace the `st.info("Coming in TICKET-A3")` in the Technicals tab body with a call to `_render_technicals_tab(...)`.
- [ ] `_render_technicals_tab` reads `st.session_state["technicals_ticker"]` and `st.session_state["technicals_period"]`, renders the selectors, calls `build_technicals_view(...)`, then renders badges / chart / RSI panel per decision §6.
- [ ] Empty state: no open positions → `st.info(...)` per decision §1.
- [ ] Error state: `OhlcUnavailable` → `st.error("Could not fetch OHLC for {ticker}: {reason}")` and no chart.
- [ ] Other tab placeholders / implementations remain untouched.

### `tests/unit/domain/test_analytics.py` — additions

- [ ] New `TestDetectRecentCross` class.
- [ ] **Happy path — golden cross**: hand-built sma pair where short crosses above long at index `n-5`; assert `("golden", 5)`.
- [ ] **Happy path — death cross**: short crosses below long at index `n-12`; assert `("death", 12)`.
- [ ] **No cross in lookback**: short above long for the entire lookback window; assert `("none", None)`.
- [ ] **Cross outside lookback**: cross at index `n-100`, lookback 90, no other changes; assert `("none", None)`.
- [ ] **Most recent cross wins**: two crosses within lookback (golden at n-50, death at n-10); assert `("death", 10)`.
- [ ] **None values in the input**: leading None entries before SMAs are valid → ignored; first valid pair seeds the comparison.
- [ ] **Edge: fewer than 2 valid indices** → `ValueError`.
- [ ] **Edge: empty lists** → `ValueError`.
- [ ] **Edge: mismatched lengths** → `ValueError` with message naming the lengths (matches the convention from `correlation_matrix`).

### `tests/unit/services/test_analytics_technicals.py` — new module

- [ ] **Universe validation**: ticker not in open positions → `ValueError`.
- [ ] **Insufficient history for SMA(50)**: position with 30 days of OHLC, period 6M → `signals.trend_50 == "insufficient"`, `view.sma_50` is all None for the visible window, but the chart-data structure is still populated.
- [ ] **Insufficient history for SMA(200)** (but enough for SMA(50)): position with 80 days → `trend_50 ∈ {"above","below"}`, `trend_200 == "insufficient"`, `cross == "insufficient"` (cross needs both SMAs).
- [ ] **Insufficient history for RSI**: position with 10 days → `view.rsi is None`, `signals.rsi_level == "insufficient"`.
- [ ] **Live-price change_pct missing day_open**: ohlc most recent bar has no `open` (or `open is None`) → `signals.live_change_pct is None`.
- [ ] **OHLC fetch failure**: provider raises → service raises `OhlcUnavailable` with the original message in `args[0]`.
- [ ] **SMA values are seeded from before the visible window**: position with 250 days of history, period 1M (≈21 days) → first visible-date SMA(200) value is non-None (proves the buffer is being applied correctly).
- [ ] **Cross detection on a real sequence**: hand-built OHLC with a known golden cross at trading-day 60 from end → `signals.cross == "golden"` and `cross_days_ago == 60`.
- [ ] **Currency badge**: a USD-denominated position → `view.currency == Currency.USD`. A EUR-denominated position → `view.currency == Currency.EUR`.

### `tests/unit/ui/test_analytics_page.py` — modifications

- [ ] Existing test for A3 placeholder is replaced: instead of asserting `st.info("Coming in TICKET-A3")` is called, asserts `_render_technicals_tab` is invoked when the Technicals tab is active. Other placeholder assertions (A1/A2/A4/A5, whichever still exist as placeholders) remain.

### Lints / quality

- [ ] `pytest` — all new tests pass; existing tests still pass (in particular Live Overview's chart from 022b — `render_candlestick` extension must be backwards-compatible).
- [ ] `ruff check .` — passes.
- [ ] `mypy app/` — passes.
- [ ] `lint-imports` — passes:
  - `app/domain/analytics.py` continues to have zero I/O imports. `detect_recent_cross` is pure.
  - `app/services/analytics_technicals.py` imports only from `app.domain`, `app.ports`, `pydantic`, `decimal`, `datetime`. No `streamlit`, no `requests`, no `yfinance`.
  - `app/ui/pages/analytics.py` imports only `streamlit`, `app.services.analytics_technicals`, `app.ui.components.*`, `app.ui.wiring`.

### State updates (per `AGENTS.md` Phase 8b)

- [ ] `docs/SESSION_LOG.md` appended with a new entry.
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-A3 → IN_REVIEW under "In review 👀").
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-A3 row → IN_REVIEW).
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.

---

## Files created

```
app/services/analytics_technicals.py
tests/unit/services/test_analytics_technicals.py
app/ui/components/period_selector.py        ← only if extraction is chosen (decision §2)
```

## Files modified

```
app/domain/analytics.py                     ← add detect_recent_cross
app/ui/pages/analytics.py                   ← replace A3 placeholder with _render_technicals_tab
app/ui/components/charts.py                 ← extend render_candlestick with overlays + add render_rsi_panel
app/ui/components/_chart_styles.py          ← add SMA_50_STYLE, SMA_200_STYLE
app/ui/pages/research.py                    ← only if period_selector is extracted (decision §2)
tests/unit/domain/test_analytics.py         ← add TestDetectRecentCross class
tests/unit/ui/test_analytics_page.py        ← update A3 assertion
docs/PROJECT_STATE.md                       ← TICKET-A3 → IN_REVIEW
docs/SESSION_LOG.md                         ← new session entry
docs/TICKETS/BACKLOG.md                     ← TICKET-A3 row → IN_REVIEW
```

## Files NOT to modify

- `app/ui/pages/overview.py` — out of scope. The Live Overview chart from 022b uses `render_candlestick`; backwards compatibility is required, but the page itself is not edited.
- `app/ui/pages/manage.py`, `app/ui/pages/tax.py` — out of scope.
- `app/services/analytics_correlation.py` (if exists from A2) — out of scope. Reuse no logic from there; correlation is a different concern.
- `app/services/analytics_performance.py`, `app/services/analytics_sizer.py`, `app/services/analytics_concentration.py` — touched only by their respective tickets. Do not create empty stubs.
- `app/domain/analytics.py` existing functions (`daily_returns`, `volatility_annualised`, `drawdown_series`, `max_drawdown`, `sharpe`, `sma`, `rsi`, `correlation_matrix`, `correlation_clusters` if A2 merged) — extending the file is fine; do not modify existing functions.
- `app/ports/ohlc.py` and `app/adapters/ohlc_*` — the OHLC port and adapter stay as-is. If a buffer parameter is needed, pass it via the existing API, do not extend the port.
- `app/ports/price_feed.py` and adapters — unchanged.
- `pyproject.toml` / `requirements.txt` — no new dependencies.

---

## Out of scope

- **MACD, Bollinger Bands, Stochastic, ATR, OBV, any other indicator.** RSI + 2 SMAs only in v1. New indicators are A3.x follow-ups, each with its own ticket.
- **Configurable indicator parameters** (e.g. RSI(7) vs RSI(14)). Locked at the standard values for v1.
- **Crosshair tooltip** synchronised across the candlestick and RSI panels. Plotly defaults only.
- **Drawing tools** (trendlines, support/resistance levels). Not in v1.
- **Multi-ticker comparison view** ("AAPL vs MSFT side by side"). Single ticker only.
- **Volume panel.** Volume data is in `Bar` already, but no volume panel is rendered. Out of v1.
- **Alerting** ("notify me when RSI crosses 70"). No notification system exists; out of scope.
- **Timeframe other than daily.** No 4H, 1W, 1M bars. Daily only.
- **Simulate-buy / simulate-sell handoff** from this tab. The tab is for analysis. Trading goes through Manage Portfolio (existing) or the Sell Simulator (TICKET-012). Not in this tab.
- **Adding "any ticker" mode** to the selector. The owned-positions distinction from Research is load-bearing (decision §1). Do not add a free-text ticker input.
- **Caching the computed `TechnicalsView`** beyond the adapter-level OHLC cache. Recompute on every selector change.
- **Dark-mode-specific styling** for the new chart elements. The existing `_chart_styles.py` palette is theme-aware; new constants follow the same pattern.
- **Mobile-specific layout.**

---

## Test cases (manual review checklist for the PR)

- [ ] Open the dashboard → Analytics → Technicals tab. With no ticker selected, the default ticker is the alphabetically-first owned position. Tab loads without error.
- [ ] Switch the ticker selector to a different owned position. Chart, RSI panel, and all five badges update.
- [ ] Switch period 1M → 3M → 6M → 1Y → 2Y → 5Y. The candlestick window changes; SMA lines extend or contract; RSI panel updates.
- [ ] On a long-held position at 6M period: verify SMA(50) and SMA(200) lines are drawn across the entire visible window (proof that the buffer fetch is working — the lines should not be missing for the first 50/200 visible days).
- [ ] On a short-held position (<50 days): SMA(50) line is not rendered, "50 DMA: insufficient history" badge is grey and shows the day count `(X / 50)`.
- [ ] On a position with <200 days but >50 days: SMA(50) renders, SMA(200) doesn't; "200 DMA" badge and "Cross" badge both grey.
- [ ] On a position with <15 days: RSI panel shows "Insufficient history" message instead of a chart; RSI badge is grey.
- [ ] Look at a position with a recent golden cross (one of the user's actual positions if applicable). The "Golden Cross (N days ago)" badge fires with a sensible day count, and the visual line crossing on the chart agrees with the badge's day count.
- [ ] Live-price badge: shows the current price in the position's native currency (USD for AAPL, EUR for RHM.DE) and the day-change percent. If yfinance returns no `open`, the percent is em-dash, not 0.0%.
- [ ] Disconnect from the network (or simulate by stubbing the OHLC adapter to raise). Tab shows `st.error(...)` with the failure reason; no fake/empty chart.
- [ ] Switch to Research page, select the same ticker. Confirm Research still renders correctly (no regression from `render_candlestick` changes).
- [ ] Switch to Live Overview. Confirm the existing chart on Live Overview still renders correctly (backwards-compat regression check).
- [ ] If period_selector was extracted to a shared component: switch period on Research, then switch period on Technicals — both work independently (different session_state keys).
- [ ] No regressions on Manage Portfolio, Tax Dashboard, Performance / Correlation / Position Sizer / Concentration tabs.

---

## Notes (architectural and methodological — for future AI sessions)

### Why owned-positions only is non-negotiable

The Technicals tab and the Research page (TICKET-022b) sit in dangerous proximity: both render a candlestick chart with period selectors, both consume `OhlcDataProvider`, both could trivially be made to do the other's job. The distinction holds the design together:

- **Research** asks *"should I buy this?"* — pre-trade, free-text ticker, simulate-buy handoff.
- **Technicals** asks *"is what I own still acting healthy?"* — post-trade, owned-only, indicator overlays.

If the implementation agent is tempted to add a free-text "search any ticker" input to Technicals because "it's already 80% of Research", **stop** — the right answer is to keep them separate and improve Research independently if it needs improvement. Two pages converging into one is a refactor that needs an explicit ticket.

### Why insufficient-history badges render greyed-out instead of being hidden

Hidden = silent failure. The user looks at four badges and assumes the analysis is complete; they don't see that "Above 200 DMA" is missing because they never knew it should be there. Greyed = visible failure. The badge is present, the label says exactly why it's not computed, and the count `(X / 200)` tells the user how many more days they need to wait.

This is the same principle as the "no silent fallbacks" rule from `METHODOLOGY.md`. The user must be able to see what's known and what isn't.

### Why two stacked charts instead of a Plotly subplot grid

`render_candlestick` from TICKET-022a returns a complete figure. Combining into a 2-row subplot would require either:

1. Refactoring `render_candlestick` to return traces instead of a figure, breaking its existing callers.
2. Duplicating the candlestick-construction logic inline in this ticket.

Both are scope expansion. Two stacked figures with synchronised x-axes (Plotly does this for free when the dates are the same) is the cheaper path. If a future ticket needs true subplot synchronisation (e.g. shared crosshair), that's the trigger for the refactor — not this ticket.

### Why SMA / RSI / cross-detection are added to `app/domain/analytics.py`

`sma` and `rsi` already live there from A0. `detect_recent_cross` is a pure function over their outputs. Per A0's decision §4, the stats library is the single home for statistical primitives. Adding `detect_recent_cross` here continues the pattern — and makes it available to A1's drawdown analysis or any future tab that wants cross detection on other paired series (e.g. portfolio NAV crossing a benchmark MA).

### Why the live badge currency is the position's native currency, not EUR

The chart is in native currency (USD for AAPL, EUR for RHM.DE) because that's how the price actually quotes on the exchange. Showing the live badge in EUR while the chart is in USD would force the user to mentally translate every glance from chart to badge. The trade-off is the badge can't be compared across positions of different currencies — but the user is looking at one position at a time, so this isn't a real cost.

### What this ticket does NOT lock in for A4 / A5

- The `overlays` extension to `render_candlestick` is generic. A4 and A5 don't use candlesticks, so they don't consume this.
- The grey "disabled" badge state may be reused by A4 (insufficient-data position card) and A5 (currency-exposure donut when a position lacks currency tagging) — that's fine, the variant is in scope for those tickets to consume.
- `detect_recent_cross` is a generic SMA-pair primitive. If A4 or A5 want to flag e.g. weight crossing a threshold over time, they can use it; if not, it sits available.
