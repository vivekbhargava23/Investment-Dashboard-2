# TICKET-027 — Snapshot tab: header strip, 5Y price chart, KPI tiles with sparklines, valuation band, next catalyst

**Status:** QUEUED
**Priority:** HIGH
**Estimated session length:** 1.5 – 2 hr
**Drafted by:** Vivek + Claude (chat 2026-05-13)
**Implemented by:** Claude Code (session TBD)
**Depends on:** TICKET-026 (Company page shell, chart theme module, wiring — must be merged first)

> **After this ticket merges, the Snapshot tab is fully functional.** Selecting a ticker shows a header strip with key company info + price + day change, a 5Y price chart with 200DMA overlay, 4 KPI tiles each backed by an 8-quarter sparkline, a valuation band showing current P/E within its 5Y range, and a next-catalyst countdown card. The chart style chosen during TICKET-026's PR review is applied to all charts. The temporary chart sampler from TICKET-026 is removed.

---

## Problem

TICKET-026 created the Company page shell with six tabs, but Snapshot (Tab 1) only has a placeholder and the temporary chart style sampler. The Snapshot tab is the most-viewed surface — it's the first thing a user sees after selecting a ticker. It needs to convey the essential story of a company in one screen: identity, price trend, financial health, valuation context, and what's coming next.

---

## Prerequisite: chart style decision

Before implementing this ticket, the agent must check which chart style was chosen during TICKET-026's PR review. The chosen style is whichever of `STYLE_CLEAN`, `STYLE_DARK`, or `STYLE_EDITORIAL` Vivek approved. Look for a comment on PR or a note in the ticket file. If no explicit choice was recorded, default to `STYLE_CLEAN` and note this in the PR description.

The agent then:
1. Sets the chosen style as the default in `chart_theme.py` (e.g. `DEFAULT_STYLE = STYLE_CLEAN`).
2. Removes the chart sampler code from the Snapshot tab placeholder.
3. Implements all Snapshot charts using `apply_style(fig, DEFAULT_STYLE)`.

---

## Acceptance criteria

### Remove chart sampler from Snapshot tab

- [ ] Delete the temporary chart style sampler code that TICKET-026 placed in the Snapshot tab.
- [ ] Add a `DEFAULT_STYLE` constant to `app/ui/components/chart_theme.py` pointing to the chosen style.

### Header strip (top of Snapshot tab)

- [ ] Rendered as a horizontal row via `st.columns`.
- [ ] **Left section:** Company name (large, bold), ticker symbol, ISIN (if available, smaller text), sector · industry · country (one line, muted).
- [ ] **Right section:** Current price (large), day change % (colored green/red with ↑/↓ arrow), exchange · currency label (e.g. "NYSE · USD").
- [ ] **Star toggle placeholder:** a disabled `⭐` icon in the header row with tooltip "Watchlist — coming in TICKET-031". Do NOT implement watchlist logic — just reserve the visual space. (C7 wires it.)
- [ ] Data sources: `CompanyData.profile` (name, sector, industry, country, ISIN, currency), `CompanyData.latest_quote` (price, day_change_pct).
- [ ] If `profile` is None (fetch error), show "Company data unavailable" in place of the header. Do not crash.
- [ ] If `latest_quote` is None, show "Price unavailable" where price would be.
- [ ] Use `format_eur` / `format_pct` from `app/ui/format.py` where applicable. For non-EUR prices, display in native currency (use `latest_quote.price.currency`).

### 5Y price chart with 200DMA overlay

- [ ] Line chart of daily close prices from `CompanyData.price_history` (up to 5 years).
- [ ] **200-day moving average** overlay: compute from the price_history points using a simple rolling mean. If fewer than 200 data points, show whatever SMA is computable (e.g. 50DMA if only 1 year of data) or omit the overlay with a note.
- [ ] **Period toggle** above the chart: 1Y / 3Y / 5Y (filter `price_history` by date range). Default: 5Y.
- [ ] Apply the chosen chart style via `apply_style()`.
- [ ] Use `styled_line_trace()` for both the price line and the SMA overlay (different accent colors).
- [ ] Hover tooltip: date, close price, SMA value.
- [ ] **"Show data" expander** below the chart: `st.expander("Show data")` containing a `st.dataframe` of the raw price history (date, close, volume) for the selected period.
- [ ] Chart height: 400px.
- [ ] If `price_history` is empty, show `st.warning("Price history unavailable")`.

### 4 KPI tiles with sparklines

Four metric cards in a `st.columns(4)` row. Each tile shows:
- A label
- A primary number (large)
- An 8-quarter sparkline behind/below the number (small inline chart showing the trend)
- A subtitle with context (e.g. "3Y CAGR" or "Latest quarter")

The four KPIs:

1. **Revenue Growth (3Y CAGR)**
   - Compute from `quarterly_fundamentals`: take the revenue from the latest quarter and the quarter 12 periods ago (3 years). CAGR = `(latest/earliest)^(1/3) - 1`. If fewer than 12 quarters available, use whatever span exists and label accordingly (e.g. "2Y CAGR").
   - Sparkline: last 8 quarters of revenue values.
   - Format: `+12.3%` (green if positive, red if negative).
   - If revenue data unavailable: show "N/A" with `st.caption("Revenue data unavailable")`.

2. **EBIT Margin (latest quarter)**
   - Compute: `operating_income / revenue` from the most recent quarter in `quarterly_fundamentals`.
   - Sparkline: last 8 quarters of EBIT margin.
   - Format: `18.5%`.
   - If either field is None: "N/A".

3. **Net Debt / EBITDA**
   - Compute: `net_debt / ebitda` from the most recent quarter (use TTM EBITDA = sum of last 4 quarters if available, else latest quarter annualized × 4).
   - Sparkline: last 8 quarters of this ratio.
   - Format: `2.1x`. Color: green if < 2, amber if 2–3, red if > 3.
   - If `net_debt` or `ebitda` is None: "N/A".

4. **FCF Yield**
   - Compute: TTM free_cash_flow (sum of last 4 quarters) / market_cap. Market cap from `profile.market_cap`.
   - Sparkline: last 8 quarters of quarterly FCF (not the yield — yield needs market cap which is point-in-time).
   - Format: `4.2%`.
   - If FCF or market_cap unavailable: "N/A".

- [ ] Sparklines: use plotly `go.Scatter` with `mode='lines'`, no axes, no grid, no labels — just the shape. Height ~40px, width ~120px. Apply accent color from the chart style. Render via `st.plotly_chart(fig, use_container_width=False, config={'displayModeBar': False})`.
- [ ] All computations happen in a helper module `app/ui/pages/_snapshot_helpers.py` (private module, not a public interface). The Snapshot tab's render function calls these helpers, never computes inline.
- [ ] Helper functions are pure: they take `CompanyData` and return display-ready values. No I/O, no Streamlit calls inside helpers.

### Valuation band

- [ ] Horizontal bar showing where the current trailing P/E sits within its own 5Y range.
- [ ] Data: `current_multiples.pe_trailing` for the current value. For the 5Y range, compute min/max P/E from historical data: iterate `quarterly_fundamentals`, compute trailing P/E at each quarter-end (price at that date from `price_history` ÷ TTM EPS from last 4 quarters of `eps_diluted`). This is the historical multiples computation noted in TICKET-025's "Out of scope" as belonging to the presentation layer.
- [ ] **Visual:** a horizontal bar (full width of a column), shaded gradient from green (cheap) to red (expensive). A marker dot at the current P/E position. Labels at min, current, and max.
- [ ] If current P/E is None or historical data insufficient (< 4 quarters of EPS): show `st.caption("Valuation band unavailable — insufficient earnings data")`.
- [ ] If P/E is negative (loss-making company): show `st.caption("P/E not meaningful — company is loss-making")`.
- [ ] Render as a plotly figure with `go.Bar` (horizontal, single bar for the range) + `go.Scatter` (marker for current value). Apply chart style.

### Next catalyst card

- [ ] If `CompanyData.next_catalyst` is not None: render a card showing:
  - Kind (e.g. "EARNINGS", "DIVIDEND") as a badge
  - Date
  - Days until the event (computed from today)
  - Detail string if available
  - Example: `"📅 Q1 FY26 Earnings · May 28 · in 15 days"`
- [ ] If `next_catalyst` is None: show `st.caption("No upcoming catalyst data available")`.
- [ ] Use `render_metric_card` from `app/ui/components/metric_card.py` if it fits, or a simple `st.container` with styled markdown.

### Layout (full Snapshot tab)

```
┌─────────────────────────────────────────────────────────┐
│  Header strip: Name / Ticker / Sector  |  Price / Δ%    │
├─────────────────────────────────────────────────────────┤
│  [1Y] [3Y] [5Y]                                        │
│  ┌─────────────────────────────────────────────────┐    │
│  │           5Y Price Chart + 200DMA               │    │
│  └─────────────────────────────────────────────────┘    │
│  ▸ Show data                                            │
├────────────┬────────────┬────────────┬──────────────────┤
│ Rev Growth │ EBIT Margin│ ND/EBITDA  │ FCF Yield        │
│  +12.3%    │   18.5%    │   2.1x     │  4.2%            │
│  ~~~~~~~~  │  ~~~~~~~~  │  ~~~~~~~~  │  ~~~~~~~~        │
├─────────────────────────────────────────────────────────┤
│  Valuation band: [green ●───────── red]  P/E 24.3x     │
├─────────────────────────────────────────────────────────┤
│  📅 Next catalyst: Q1 Earnings · May 28 · in 15 days   │
└─────────────────────────────────────────────────────────┘
```

---

## Files created

```
app/ui/pages/_snapshot_helpers.py
tests/unit/ui/test_snapshot_helpers.py
```

## Files modified

```
app/ui/pages/company.py          ← Snapshot tab: replace placeholder + sampler with real content
app/ui/components/chart_theme.py ← add DEFAULT_STYLE constant
```

## Files NOT to modify

- `app/domain/**` — no domain changes.
- `app/ports/**`, `app/adapters/**`, `app/services/**` — stable from TICKET-025.
- `app/ui/pages/research.py` — do not touch.
- `app/ui/components/charts.py` — existing chart components stay as-is. Snapshot uses `chart_theme.py` + direct plotly, not the existing `render_*` functions (which serve other pages).
- `app/ui/components/ticker_searchbox.py` — no changes.
- `app/ui/wiring.py` — already wired in TICKET-026.
- `app/ui/format.py` — already has `format_relative_time` from TICKET-026. If new formatters are needed (e.g. `format_multiple` for "24.3x"), add them, but do not modify existing functions.
- `pyproject.toml` / `environment.yml` — no new dependencies.

---

## Out of scope

- **Other tab content** — Financials (C4), Valuation (C5), Capital & Owners (C6). Only Snapshot is built here.
- **Watchlist logic** — the star icon is a visual placeholder only. TICKET-031 wires it.
- **Glossary tooltips** — no ⓘ icons in this ticket. TICKET-031 retrofits them.
- **Annotations on the price chart** (earnings dates, dividend ex-dates as vertical lines) — future enhancement. The cross-cutting visual rule says "annotations on time-series" but implementing this requires mapping `next_catalyst` + historical catalysts onto the chart. Defer to a polish ticket.
- **Peer comparison on the valuation band** — the band shows only the company's own 5Y range. Peer context comes in C5 (Valuation tab).
- **Interactive period toggle via URL params / session state persistence** — the period toggle resets on page navigation. Acceptable for v1.
- **Retrofitting chart style to existing pages** (Research, Analytics) — separate future ticket.

---

## Test cases (manual review checklist for the PR)

- [ ] Select "NVDA" on the Company page. Snapshot tab loads with all sections visible.
- [ ] Header shows "NVIDIA Corporation", "NVDA", sector/industry, price with day change.
- [ ] 5Y price chart renders with a visible 200DMA line. Toggle to 1Y — chart zooms in, SMA adjusts.
- [ ] 4 KPI tiles show numbers (not all "N/A" for a major ticker like NVDA). Sparklines are visible as small trend lines.
- [ ] Valuation band shows a horizontal bar with the current P/E marker. The position looks reasonable for NVDA.
- [ ] Next catalyst shows the next earnings date (if Finnhub data is available; otherwise shows "unavailable" — acceptable without Finnhub API key).
- [ ] Click "Show data" under the price chart. A table of dates and closes appears.
- [ ] Select a ticker with limited data (e.g. a small German stock like "RHM.DE"). Verify graceful degradation: some KPIs show "N/A", no crashes.
- [ ] Select a loss-making company if available. Verify P/E band shows "not meaningful" message.
- [ ] `pytest && ruff check . && mypy app/ && lint-imports` — all pass.

---

## Tests

### `tests/unit/ui/test_snapshot_helpers.py` — new tests

Test the pure helper functions in `_snapshot_helpers.py`:

- [ ] **Revenue CAGR:** given 12 quarters of revenue data, computes correct 3Y CAGR. Given 8 quarters, computes 2Y CAGR. Given < 2 quarters, returns None.
- [ ] **EBIT margin:** given a quarter with `operating_income=18, revenue=100`, returns `Decimal("0.18")`. Given `revenue=None`, returns None.
- [ ] **Net Debt / EBITDA:** given 4 quarters of EBITDA summing to 40 and `net_debt=80`, returns `Decimal("2.0")`. Given fewer than 4 quarters, annualizes correctly. Given negative EBITDA, returns None (ratio is meaningless).
- [ ] **FCF yield:** given TTM FCF = 10B and market_cap = 200B, returns `Decimal("0.05")`. Given no FCF data, returns None.
- [ ] **Historical P/E range:** given 20 quarters of EPS and matching price history, computes min/max/current P/E correctly. Given < 4 quarters, returns None.
- [ ] **SMA computation:** given 250 daily closes, 200-day SMA has correct length and values for a few spot checks.
- [ ] **Period filter:** given 5 years of price_history and period="1Y", returns only the last year's points.

---

## Notes

### Why the KPI computations live in `_snapshot_helpers.py`, not in the domain layer

These are presentation-layer computations: they combine domain data (fundamentals) with presentation decisions (which 4 metrics to highlight, how to compute CAGR over a specific window, how to handle missing quarters). They don't belong in `app/domain/company.py` (which is a data model, not a computation engine) and they don't belong in `app/services/company.py` (which is pass-through orchestration). A private UI helper module is the right home. If a future ticket needs these computations elsewhere (e.g. watchlist cards), they can be promoted to a service at that time.

### Why historical P/E computation is here, not in TICKET-025

TICKET-025's "Out of scope" explicitly says: "Historical multiples computation (P/E over 5Y) — the data plumbing is here; the computation is in C5 (Valuation tab) because it's a presentation-layer concern." However, the valuation band on the Snapshot tab also needs historical P/E (for the 5Y range). So the computation lands in `_snapshot_helpers.py` here and will be reused or extracted when C5 needs it.

### Assumption: `CompanyData.price_history` is sorted by date ascending

TICKET-025's yfinance adapter fetches via `.history(period="5y")` which returns chronologically sorted data. The helpers assume ascending date order.

### Assumption: quarterly_fundamentals is sorted by period_end ascending

Same assumption — the adapter stores them in chronological order.
