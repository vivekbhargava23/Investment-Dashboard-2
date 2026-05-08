# TICKET-022b — Research page + Live Overview chart integration

**Status:** IN_REVIEW
**Priority:** P1
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-06)
**Implemented by:** _pending_
**Depends on:** TICKETs 001 (domain), 006 (valuation), 007 (Streamlit shell), 008 (Live Overview), 020 (TickerResolver), 021 (smooth ticker autocomplete — reuses the searchbox component), **022a (chart service + components)**

> **After this ticket merges, the dashboard has charts wherever they earn their place.** A new top-level **Research** page lets the user type any ticker (owned or not) and see a candlestick chart, key metadata, and a "Simulate buy" handoff. The Live Overview's positions table grows a per-row sparkline column, and clicking a position opens an expandable "Mini Research" panel with a 6-month line chart and key metrics. Charts are the consumer; TICKET-022a was the producer.

---

## Problem

TICKET-022a built the foundation — `OhlcDataProvider` port, market-data service with caching, three Plotly render functions — but did not consume any of it from a user-facing page. This ticket does the consuming, in two places:

1. **Live Overview gains charts.** The positions table (TICKET-008) shows ticker, value, gain, gain%. It doesn't show *trajectory*. A 30-day sparkline per row + a click-to-expand 6-month line chart per position closes that gap. The user can scan the table and see at a glance which positions are trending which way.

2. **Research page is new.** Every panel session (cf. the future Panel work) surfaces 5–10 candidate tickers Vivek doesn't yet own. Today, evaluating them means switching to TradingView or Yahoo Finance — a context switch that breaks the "single source of truth" promise. The Research page lets the user paste a ticker, see a candlestick across configurable periods, and hand off to either Manage Portfolio (record a buy) or a future watchlist.

Splitting from 022a was deliberate: 022a is contained, testable, has zero UI risk; 022b is where styling judgment, page layout, and integration glue happen. Each PR stays small.

---

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-06.

### 1. Research is a new top-level sidebar page

Sidebar order after this ticket: **Live Overview → Manage Portfolio → Tax Dashboard → Research → Settings**. Research sits before Settings because it's a daily-use page (most days, Vivek doesn't change settings; many days, he wants to glance at a chart).

The page is added to `app/ui/main.py`'s page registry following the existing pattern. The icon is `📈` (matches the visual language of the existing pages).

### 2. Research page has three regions

```
[ Ticker searchbox        ]   [ Period selector: 1d 5d 1mo 3mo 6mo 1y 2y 5y ytd ]

[ Header: SYMBOL — Name (Exchange, Currency)                                  ]
[ Recent price • Period change • 52W high/low if available                    ]

[ Candlestick chart, height 500                                                ]

[ Action row: [Simulate buy]  [+ Add to watchlist (disabled, future)]         ]
```

Three regions: input (searchbox + period), header (metadata), body (chart + actions). No tabs. No expanders. Single-screen view. Period selector is a `st.radio` with `horizontal=True` for compactness.

### 3. The ticker searchbox from TICKET-021 is reused

The Research page does not have its own ticker input. It calls `render_ticker_searchbox(key="research_ticker", resolver=resolver)` from `app/ui/components/ticker_searchbox.py`. Same UX as Manage Portfolio. Same disk cache. **One way to enter a ticker, used everywhere.**

### 4. Live Overview integration: sparkline column + expandable detail

The positions table from TICKET-008 currently has columns: Ticker | Shares | Avg Cost | Current Price | Value (EUR) | Unrealised Gain | Gain%. We add a **Trend** column between Current Price and Value, rendering a `render_sparkline(series_30d)` per row. The 30-day window is short enough to load fast and informative for "is this trending up or down right now."

The whole table row becomes clickable: clicking a row sets `st.session_state.overview_selected_ticker` and a 6-month line chart panel renders below the table for that ticker. Clicking again (or clicking another row) toggles. This is the "Mini Research" panel — a faster path than navigating to the full Research page when the user just wants a quick chart of an owned position.

If a sparkline fails to load for one ticker (`OhlcUnavailableError`), the cell shows `—` and the row continues to render. **One bad ticker does not break the table.**

### 5. Period selector remembers user's last choice

`st.session_state.research_period` persists across re-renders (default `SIX_MONTH`). The Live Overview's mini chart is locked to 6-month and not user-configurable — keeping it simple. Only the Research page exposes the full period selector.

### 6. The "Simulate buy" handoff sets session state and navigates

Clicking **Simulate buy** on the Research page:
1. Captures the current ticker into `st.session_state.simulator_handoff = SellSimulationRequest(ticker=..., type="BUY", shares=None, ...)` — using the same handoff mechanism TICKET-012 establishes for sells.
2. Switches sidebar to Pre-trade Simulator (TICKET-012's page).
3. Pre-trade Simulator reads the handoff, pre-fills ticker, lets the user fill shares + price.

If TICKET-012 has not landed yet, the button is rendered but disabled with tooltip text "Available after TICKET-012". This keeps Research shippable independently while telegraphing the integration. **Reviewer should verify dependency state at merge time.**

### 7. Sparkline data is fetched per-row but cached at the service layer

The positions table renders N rows (N ≈ 12 today). Each calls `get_ohlc_history(ticker, ChartPeriod.ONE_MONTH)` which hits the service-level cache (TICKET-022a). First page load: N network calls, ~600ms each; on a fast connection, total ~2s before the table is fully drawn. Subsequent renders: instant.

**This is acceptable.** Streamlit pages don't need to be sub-second on first paint; they need to feel responsive on subsequent interaction. The TICKET-022a cache TTL (24h for daily bars) means N network calls per day, not per page load.

If first-paint latency becomes a real complaint, a follow-up ticket can add async pre-fetching at app startup. Not premature today.

### 8. Header metadata uses what's already cached

The Research page header renders `SYMBOL — Name (Exchange, Currency)` from a `TickerMatch` already on hand from the searchbox. **No extra network call.** Recent price and period-change pct come from the OHLC series itself (last bar's close, first bar's open) — also free.

52-week high/low: nice-to-have. yfinance's `Ticker.info` exposes these, but `info` is slow (~1s) and not yet wrapped in any port. **Defer.** Add a `# TODO(TICKET-022c): 52w high/low` comment.

### 9. No new domain types needed

Everything renders from `OhlcSeries` (TICKET-022a) plus `TickerMatch` (TICKET-020). This ticket is pure UI and integration glue.

---

## Acceptance criteria

### `app/ui/pages/research.py` — new page

- [ ] Module structure mirrors `overview.py` and `manage.py`: a single `render()` function called from `main.py`'s page router.

- [ ] Page header: `st.markdown("# 📈 Research")` followed by a one-line description: "Type any ticker to see its chart, regardless of whether you own it."

- [ ] **Input row** (top):
  - Two columns: searchbox on the left (~70%), period selector on the right (~30%).
  - Searchbox: `match: TickerMatch | None = render_ticker_searchbox(key="research_ticker", resolver=resolver)`.
  - Period selector: `period = st.radio("Period", options=list(ChartPeriod), horizontal=True, key="research_period", index=4)` — `index=4` is `SIX_MONTH`.
  - Format radio labels via `format_func` to show user-friendly strings: `"1D"`, `"5D"`, `"1M"`, `"3M"`, `"6M"`, `"1Y"`, `"2Y"`, `"5Y"`, `"YTD"`.

- [ ] **Header region** (renders only when `match` is not None):
  - `st.markdown(f"### {match.symbol} — {match.name}")`.
  - Sub-line: `st.caption(f"{match.exchange} • {match.currency.value}")`.
  - Once OHLC is fetched, show a metrics row: three `st.metric` widgets in columns:
    - "Latest" — `series.latest_close` formatted with currency symbol
    - "Period change" — `series.period_change_pct` formatted as `+X.XX%` / `-X.XX%`, using `delta_color="normal"` so up=green / down=red
    - "Period" — period label as user-readable string

- [ ] **Chart region**:
  - Wrapped in `try / except OhlcUnavailableError`. On exception: `st.warning(f"Chart unavailable: {e.reason}")`. No retry button (the user can change ticker / period to retry).
  - On success: `render_candlestick(series, height=500)`.

- [ ] **Action row**:
  - `col1, col2, _ = st.columns([1, 1, 3])`.
  - Col 1: button "Simulate buy". On click, set `st.session_state.simulator_handoff = ...` and `st.session_state.page = "simulator"` (or whatever the page-routing mechanism is). **If TICKET-012 hasn't landed:** `st.button("Simulate buy", disabled=True, help="Available after TICKET-012")`.
  - Col 2: button "+ Add to watchlist", `disabled=True`, `help="Watchlist coming in a future ticket"`.

- [ ] **Empty state** (when `match is None`):
  - `st.info("Type a ticker symbol or company name above to begin.")`.
  - Optionally: list 4–5 example tickers as quick-pick buttons (`AAPL`, `NVDA`, `RHM.DE`, `5631.T`, `VWCE.DE`). Clicking sets `st.session_state.research_ticker` to that match (using `resolver.lookup`). Skip if it complicates the page; nice-to-have.

### `app/ui/pages/overview.py` — sparkline column + mini chart

- [ ] **Add a Trend column** to the positions table. Implementation depends on how the existing table is rendered (TICKET-008). If it uses `st.dataframe`, the sparkline cell is harder; if it uses `st.columns` per row (likely, per the dark-themed CSS), each row gains a column.

  Read the existing `overview.py` first; do **not** rewrite the table layout. Add the new column following the existing pattern. If the existing pattern uses `render_html` (TICKET-008b), the sparkline cell is a `<div>` with `st.plotly_chart` rendered separately and absolutely-positioned via CSS — this is fragile, prefer the `st.columns` approach.

- [ ] For each row, attempt:
  ```python
  try:
      sparkline_series = get_ohlc_history(position.ticker, ChartPeriod.ONE_MONTH, provider=ohlc_provider)
      render_sparkline(sparkline_series, height=40, width=120)
  except OhlcUnavailableError:
      st.markdown("—")  # or the dark-theme equivalent
  ```

- [ ] **Click-to-expand mini chart**: each row gets a small `st.button("Chart", key=f"chart_btn_{ticker}")` (or the row itself becomes clickable if the existing CSS supports it). Clicking sets `st.session_state.overview_selected_ticker = ticker`.

- [ ] Below the table: if `st.session_state.overview_selected_ticker` is set, render a panel:
  ```
  [Symbol] — 6-month price
  [render_line_chart(series_6mo, height=300, color=...)]
  [Close]
  ```
  Color is green (`CANDLE_UP`) if 6-month change is positive, red (`CANDLE_DOWN`) if negative — matching the row's gain color.
  Close button clears the session_state key.

- [ ] **Per-row error isolation**: if `get_ohlc_history` raises for one ticker, only that row's sparkline shows `—`. Other rows render normally. Mini chart panel handles its own exceptions the same way.

### `app/ui/main.py` — register the Research page

- [ ] Add `"research"` to the page registry. Sidebar entry: `"📈 Research"`. Route to `app.ui.pages.research.render()`.

- [ ] Sidebar order: Live Overview → Manage Portfolio → Tax Dashboard → **Research** → Settings.

- [ ] Verify the sidebar's CSS (TICKET-007's dark theme) renders the new entry correctly with no manual styling needed.

### `app/ui/wiring.py` — already exposes `get_ohlc_data_provider` from TICKET-022a

- [ ] No changes needed. Verify the singleton is reachable from `research.py` and `overview.py`.

### Tests

#### `tests/unit/ui/test_research_page.py` — research page logic

These are smoke / call-shape tests, not full Streamlit rendering. Use `pytest-mock` to patch Streamlit + components.

- [ ] **Empty state renders when match is None**: mock searchbox to return None; verify `st.info` was called with the expected text.
- [ ] **Header renders when match is set**: mock searchbox to return a known `TickerMatch`; mock service to return a known series; verify markdown call contains the symbol and name.
- [ ] **Chart unavailable state**: mock service to raise `OhlcUnavailableError`; verify `st.warning` called with the reason.
- [ ] **Period selector default is SIX_MONTH**: assert the radio default index is the SIX_MONTH index.
- [ ] **Simulate buy handoff sets session_state**: click the button (mocked); assert `st.session_state.simulator_handoff` populated with the ticker. (Skip if TICKET-012 not landed; mark `@pytest.mark.skipif`.)

#### `tests/unit/ui/test_overview_chart_integration.py` — overview integration

- [ ] **Sparkline failure does not break the row**: mock OHLC service to raise for one ticker out of three; verify other two rows render sparklines (mocked render call counted), failed row renders the placeholder.
- [ ] **Click sets overview_selected_ticker**: simulate clicking a row's chart button; assert `st.session_state.overview_selected_ticker` is the expected ticker.
- [ ] **Mini chart renders only when ticker is selected**: with no selection, `render_line_chart` is not called; with a selection, it is called once.
- [ ] **Mini chart respects gain color**: positive 6-month change → line color is `CANDLE_UP`; negative → `CANDLE_DOWN`.

#### Manual review checklist (in PR template)

- [ ] Research page: type "AP" → searchbox dropdown shows APD; pick it. Chart renders within ~1s. Header shows "APD — Air Products and Chemicals (NYSE, USD)".
- [ ] Period buttons: click 1Y → chart updates to 1-year window. Click 1D → chart updates to intraday.
- [ ] Type a non-existent ticker (e.g., "XQYZ") → "Chart unavailable" warning, no crash.
- [ ] Live Overview: positions table shows sparklines for all in-portfolio tickers. Trend column visually distinguishes uptrend from downtrend (green vs red).
- [ ] Click a position row → 6-month line chart appears below the table. Click again or click Close → it disappears.
- [ ] Stale-position handling: if NVDA is showing as stale (live price unavailable from TICKET-006), the sparkline should still attempt to load (different data path). Verify both layers work independently.
- [ ] Visit Research, then come back to Live Overview → no regressions on existing KPI tiles or table.
- [ ] Sidebar shows the new Research entry in the correct position with the 📈 icon.
- [ ] Refresh button still works: clicking Refresh on Live Overview clears OHLC cache via `clear_market_data_caches`; next page load fetches fresh.

### Lints / quality

- [ ] `pytest` — all new tests pass (~9 new); existing tests still pass.
- [ ] `ruff check .` — passes.
- [ ] `mypy app/` — passes.
- [ ] `lint-imports` — passes:
  - `app/ui/pages/research.py` imports from `app.services.market_data`, `app.domain.market_data`, `app.ui.components.charts`, `app.ui.components.ticker_searchbox`, `app.ui.wiring`. **Not from adapters.**
  - `app/ui/pages/overview.py` adds imports from `app.services.market_data` and `app.ui.components.charts`. Existing import rules unchanged.

### State updates (per CLAUDE.md session-end ritual)

- [ ] `docs/SESSION_LOG.md` appended.
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-022b → IN_REVIEW).
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-022b row → IN_REVIEW).
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.

---

## Files created

```
app/ui/pages/research.py
tests/unit/ui/test_research_page.py
tests/unit/ui/test_overview_chart_integration.py
```

## Files modified

```
app/ui/pages/overview.py                ← add Trend column + click-to-expand mini chart
app/ui/main.py                          ← register Research page in sidebar + router
docs/TICKETS/BACKLOG.md                 ← TICKET-022b row → IN_REVIEW
```

---

## Out of scope

- **Watchlist persistence.** The "+ Add to watchlist" button is rendered disabled. Watchlist as a feature is its own ticket (TICKET-024 or similar) — likely paired with the Panel framework.
- **52-week high/low in the header.** Requires `Ticker.info` calls; deferred to TICKET-022c.
- **Compare-tickers overlay** (e.g., NVDA vs SPY normalised). Future enhancement; this ticket is single-ticker only.
- **Volume bars under the candlestick.** TICKET-022a captures volume in `OhlcBar` but doesn't render it. Could be added here as a Plotly subplot, but adds complexity and pixel real estate. Defer.
- **Drawing tools** (trend lines, support/resistance). Out of scope.
- **Streamlit `@st.cache_data` on render functions.** Service-level caching from TICKET-022a is sufficient; profiling will tell us if more is needed.
- **Mobile-specific layout.** Plotly is responsive; the rest of the dashboard isn't optimised for mobile and shouldn't be in this ticket.
- **Async pre-fetching** of sparklines at page load. First-paint latency on Live Overview will go from ~200ms to ~2s after this ticket lands. **Acceptable for v1.** A follow-up ticket can address this if it's actually annoying in practice.
- **Linking the Research page chart back to a Decision Log entry** (Panel work). Out of scope; comes later.

---

## Notes (architectural and methodological — for future AI sessions)

### Why Research is a top-level page, not a tab inside Overview

Two reasons:

1. **Information architecture.** Research and Live Overview answer different questions. Live Overview = "what do I own and how is it doing?" Research = "what about a thing I might own?" Mixing them into tabs implies they're variants of the same thing. They're not.
2. **Page state isolation.** The Research page has its own ticker input, period state, and cached series. Tabbing it inside Overview would conflate session_state keys and create coupling between unrelated UI flows.

The "mini chart" inside Overview is the right level of cross-page integration: a glance at a chart for an owned position, without leaving the page. Anything more (full candlestick, period selector) belongs on Research.

### Why we don't share the period selector across pages

Each page picks the period that's right for its purpose:
- Live Overview's sparkline: hard-coded `ONE_MONTH` (recent trend at a glance)
- Live Overview's mini chart: hard-coded `SIX_MONTH` (medium-term context)
- Research page: user-controlled, default `SIX_MONTH`

Tying them via a global setting would mean changing the period on Research silently changes Overview's mini chart on a later visit. Cognitive surprise. Each page's choice is local.

### Why the sparkline column might cause first-paint slowdown

Live Overview today loads in ~200ms. Adding 12 sparkline fetches at ~600ms each in serial is ~7s. **In practice it's much better** because:
1. yfinance's adapter cache hits for tickers already requested elsewhere this session.
2. `streamlit-caching` of the service layer means subsequent re-renders are instant.
3. Streamlit renders progressively — the user sees rows populate as data arrives.

But the first ever load of the day will be slow. We accept this. If it's intolerable, the fix is async pre-fetching at app start (a `threading.Thread` warming the cache). Easy follow-up; not needed today.

### Why we didn't make the row itself clickable

Streamlit doesn't have a native "clickable row" pattern. Options:
- A small button per row (chosen) — explicit, accessible, no surprise.
- An invisible button overlay on the row via CSS — fragile, breaks on theme changes, accessibility-questionable.
- Per-row `st.expander` — works but doubles the table's vertical space when expanded, not great UX.

The button per row is the simplest correct path. The button can be small (icon-only) to keep visual noise low.

### Pattern reuse — this is the template for future pages

Future pages that need charts (Performance, Watchlist, Panel-driven Company Card) follow the same structure:

1. Searchbox or ticker source (existing component).
2. Period selector if user-controlled.
3. Header metadata from cached metadata.
4. Chart from `get_ohlc_history` + render component.
5. Error handling around `OhlcUnavailableError`.

This is a deliberate convergence. After three pages all do it the same way, a future ticket can extract a `<TickerView>`-style higher-level component. Don't extract yet — too few examples to know the right abstraction.

### How to handle the "TICKET-012 not yet landed" edge case at PR review

The Simulate buy button checks at module-import time: try-import the simulator; if missing, render disabled. This keeps the PR mergeable independently of TICKET-012's status. The PR description must state explicitly: "Simulate buy is enabled if TICKET-012 is merged; otherwise disabled with tooltip. Verify TICKET-012 status at merge time and toggle by removing the import-guard if needed."

### Cost note

This ticket adds ~12 sparklines × 1 OHLC fetch on the first daily load = 12 yfinance hits per day. yfinance is unrated-limited but not unlimited. We're well within friendly use. No concerns.
