# Analytics tabs — drafting handoff

> **Purpose of this file:** Hand-off context from the planning chat of 2026-05-08 into one or more fresh chat sessions whose job is to **draft the 6 analytics tickets** (A0 + A1–A5) into READY ticket files. This file plus `PROJECT_STATE.md` plus `AGENTS.md` plus the existing `TICKET-022b-research-page-and-overview-charts.md` (as a format reference) is everything the drafting chat needs.

> **What this file is NOT:** an implementation guide. The drafting chat produces **ticket files**, not code. Implementation happens in a separate Claude Code / ChatGPT Codex session, after Vivek moves a ticket from DRAFT → READY.

---

## What's already locked (do not re-debate)

These were decided in the planning chat. The drafting chat must respect them.

1. **The Analytics page is a 5-sub-tab container.** Sub-tab keys: `performance`, `correlation`, `technicals`, `sizing`, `concentration`. Default landing tab: `performance`.

2. **One Analytics page, one sidebar entry, five `st.tabs()` inside.** Not five sidebar entries. The sub-tab structure mirrors `st.tabs()` semantics — same as how the existing pages are structured.

3. **Six tickets, drafted independently, implementable in any order after A0.**

   | ID | Title | Depends on |
   |---|---|---|
   | A0 | Analytics page shell + analytics stats library | TICKET-013 (NAV cache), 022a (chart components) |
   | A1 | Performance tab v1 (equity curve, benchmark toggle, KPIs) | A0, 013 |
   | A2 | Correlation tab v1 (heatmap, avg-corr table) | A0, 022a (OHLC service) |
   | A3 | Technicals tab v1 (per-ticker chart with MA + RSI signals) | A0, 022a |
   | A4 | Position Sizer tab v1 (risk-based + weight-based methods) | A0, 006 (valuation) |
   | A5 | Concentration tab v1 (weights, currency, top-N) | A0, 006 |

4. **Price Targets is deferred to post-Panel work.** It needs persistence for `portfolio_targets` we don't have, and overlaps with Panel-managed state. Not in v1 analytics.

5. **TICKET-013 (Daily NAV snapshot) is a hard prerequisite for A1.** It's already drafted as READY. A2/A3/A4/A5 do not need NAV; only A1 does.

6. **The shared analytics stats library (introduced in A0) is `app/domain/analytics.py`.** Pure functions, no I/O, fully unit-tested. Functions: `daily_returns`, `volatility_annualised`, `drawdown_series`, `max_drawdown`, `sharpe`, `sma`, `rsi`, `correlation_matrix`. Each consumed by 1–3 sub-tabs.

7. **Charts use existing `render_candlestick`, `render_line_chart`, `render_sparkline`** from TICKET-022a. **No custom SVG.** Where existing chart components don't fit (heatmap, bar chart of weights, RSI panel), use Plotly directly via the same module pattern as `app/ui/components/charts.py`.

8. **No new persistence in v1 analytics tickets** beyond what TICKET-013 introduces. No `portfolio_targets`, no `portfolio_settings`. Defaults are constants in `app/services/analytics.py`.

---

## What the drafting chat does

**For each of A0 through A5, in order**, the drafting chat:

1. Reads this file + `PROJECT_STATE.md` + `AGENTS.md` + `TICKET-022b-research-page-and-overview-charts.md` (as the format reference).
2. Drafts ONE ticket file matching the structure of TICKET-022b (Status / Priority / Drafted by / Depends on / problem statement / architectural decisions / acceptance criteria / files likely touched / out of scope / test cases / notes).
3. Outputs the ticket file as a **single markdown code block** Vivek can paste into `docs/TICKETS/`.
4. Outputs a **one-line BACKLOG.md update** for that ticket.
5. Stops. Waits for Vivek to say "next ticket" or to start a new chat for the next one.

**Do not draft multiple tickets in one response.** One ticket per turn keeps each draft focused and reviewable.

**Do not write any code.** This chat is for drafts only. Implementation happens elsewhere.

---

## Per-ticket prompts (one paragraph each — the drafting chat expands these)

### A0 — Analytics page shell + analytics stats library

Create the Analytics page in `app/ui/pages/analytics.py`. Add it to the sidebar between Tax Dashboard and Research (icon `📊`). The page renders five `st.tabs()`: Performance / Correlation / Technicals / Position Sizer / Concentration. Each tab body is `st.info("Coming in TICKET-AX")` for now. Also create the shared stats library at `app/domain/analytics.py` with pure functions: `daily_returns(closes: list[Decimal]) -> list[Decimal]`, `volatility_annualised(returns: list[Decimal]) -> Decimal` (×√252), `drawdown_series(navs: list[Decimal]) -> list[Decimal]` (peak-to-trough %), `max_drawdown(navs) -> Decimal`, `sharpe(returns, risk_free: Decimal = 0) -> Decimal`, `sma(closes, period: int) -> list[Decimal | None]`, `rsi(closes, period: int = 14) -> list[Decimal]` (Wilder smoothing), `correlation_matrix(returns_by_ticker: dict[str, list[Decimal]]) -> dict[str, dict[str, Decimal]]`. Domain layer rules apply: zero I/O, `Decimal` only, frozen models. Each function gets exhaustive unit tests including edge cases (empty list, single value, NaN handling, mismatched-length series for correlation). This ticket is the foundation for A1–A5; nothing user-visible changes beyond the empty page existing.

### A1 — Performance tab v1

Implement the Performance sub-tab. Layout: KPI strip across the top (Period Return, Alpha vs Benchmark, Max Drawdown, Annualised Volatility, Sharpe Ratio — 5 metric cards using existing `MetricCard`), period selector (`1W / 1M / 3M / 6M / 1Y / MAX` as `st.radio` horizontal), benchmark selector (`SPY / EUNL / None` as `st.selectbox`, default `SPY`), then a dual-line chart (portfolio NAV indexed to 100 + benchmark indexed to 100) using `render_line_chart` extended to support a second series — extend the chart component if needed, in scope for this ticket since A1 is the first consumer. Below that, a drawdown area chart (red fill below zero) showing peak-to-trough % over the same period. Data: portfolio NAV from `nav_service.get_nav_series` (TICKET-013), benchmark from `OhlcDataProvider` (TICKET-022a). All metric calculations come from `app/domain/analytics.py` (TICKET-A0). Service-level orchestration in `app/services/analytics_performance.py`. Acceptance includes: KPIs colour-coded (green/red/amber per existing pattern), period switch refetches both series, drawdown panel never shows DD > 0 (sanity), Sharpe handles negative returns (no `—` placeholder — render the negative number with neutral colour). Out of scope: time-weighted vs money-weighted return, contribution-to-return per position, realised-vs-unrealised split — those are A1.x follow-ups.

### A2 — Correlation tab v1

Implement the Correlation sub-tab. Layout: window selector (`30D / 60D / 90D` as `st.radio`, default 30D), then two artifacts side by side using `st.columns([2, 1])`. Left column: N×N heatmap of pairwise Pearson correlation of daily returns, where N = number of owned positions. Use Plotly `Heatmap` directly (no existing chart component fits) — colour ramp red for high correlation, green for low, neutral for diagonal. Cells display the correlation value rounded to 2 decimals; diagonal shows `—`. Right column: a sortable table "Average correlation to portfolio" (Ticker / Name / Avg Correlation / Diversification Bucket badge) sorted descending by avg correlation. Bucket thresholds: `<0.2` high diversifier (green), `<0.4` moderate (amber), `<0.6` low (amber), `≥0.6` very low (red). Below both: an auto-warning card that fires when ≥3 positions have pairwise correlation > 0.6 — listing the cluster, suggesting they may move together. Cluster detection: simple union-find over edges where corr > 0.6, any cluster of size ≥ 3 emits a flag. Data: historical closes per position from `OhlcDataProvider`; convert to daily returns via `analytics.daily_returns`; build matrix via `analytics.correlation_matrix`. Service: `app/services/analytics_correlation.py`. Acceptance includes: matrix scales to N positions without code changes (current portfolio is 13), window switch recomputes everything, diagonal always `—`, sort is stable across recomputes. Out of scope: hierarchical clustering reorder, rolling-correlation chart between two pickable tickers — those are A2.x follow-ups.

### A3 — Technicals tab v1

Implement the Technicals sub-tab. Layout: ticker selector (`st.selectbox` listing every owned position; persist selection to `st.session_state["technicals_ticker"]`), period selector reusing the same `_PERIOD_LABELS` pattern from `app/ui/pages/research.py` (default 6M). Then a signal badge strip across the top: "Above 50 DMA" / "Below 200 DMA" / "Golden Cross" / "RSI 67 (neutral)" / "Live: $123.45 (+12.3%)" — five badges, colour-coded per state. Then a candlestick chart (use existing `render_candlestick`) with two overlaid lines: 50-day SMA (amber dashed) and 200-day SMA (blue dashed). Below the candlestick, an RSI panel (Plotly line chart, height 80px) with reference dashed lines at 30 and 70, shaded band between them. Use existing chart styles from `app/ui/components/_chart_styles.py`. Indicators come from `analytics.sma` and `analytics.rsi` (TICKET-A0). Service: `app/services/analytics_technicals.py`. Acceptance includes: ticker switch refetches without flicker, MA lines only render once enough history exists (50 and 200 days respectively), Golden/Death Cross badge agrees with the line crossing on chart, RSI line never exits 0–100. Out of scope: MACD, Bollinger bands, configurable indicators, crosshair tooltip — those are A3.x follow-ups. **Important**: this tab overlaps stylistically with the Research page from TICKET-022b; the difference is Research is for any ticker (owned or not, simple chart, simulate-buy handoff), Technicals is for owned positions only with indicator overlays for analysis. Make this distinction clear in the ticket so the implementation agent doesn't accidentally rebuild Research.

### A4 — Position Sizer tab v1

Implement the Position Sizer sub-tab. Layout: two-column grid using `st.columns([1, 1])`. Left column (inputs): ticker selector + Buy/Sell toggle, then a "Current Position" card showing weight, value, price, lot count. Below the card, two methods of sizing as separate input groups. Method 1 (Risk-Based): `st.number_input` for Risk % (0.1 – 5, step 0.1, default 1.0) and Stop Loss % (1 – 30, step 0.5, default 8.0). Method 2 (Weight-Based): `st.number_input` for Target Weight % (1 – 40, step 0.5, default 15.0). Right column (results): three result cards. Method 1 result (green-bordered): shares to trade, trade € (in EUR), risk € + risk %, stop price. Method 2 result (blue-bordered): shares to buy/sell (signed), Δ€ (signed), current weight, target weight. Below: a "New Weight After Method 1" card with horizontal progress bar — current weight as a faded background bar, new post-trade weight as a solid foreground bar coloured green/amber/red by bucket (`>35%` red, `25-35%` amber, `≤25%` green), with a vertical red marker at 35% (configurable max-position-weight). Math is non-trivial — define `MAX_POSITION_WEIGHT = 35` and `BAR_SCALE_MAX = 40` as module-level constants in the service. All FX conversions go through a helper `to_base_eur(amount: Decimal, currency: Currency, fx_rate: Decimal) -> Decimal` to avoid the inline-conversion-in-three-places anti-pattern noted in the design reference. Service: `app/services/analytics_sizer.py`. Pure-math functions go in `app/domain/sizing.py` (no I/O). Acceptance includes: switching ticker updates all numbers atomically, risk-based shares math `(totalValue × riskPct/100) / (price × stopPct/100)` matches a hand-computed expected, weight-based delta is signed and the badge says "buy" vs "sell" accordingly, post-trade weight bar is capped at 100% and the 35% marker is always visible. Out of scope: trade-ticket export to Manage Portfolio (handoff like the Sell Simulator does — that's A4.x), trailing stop, persistence of risk-pct/stop-pct defaults. **Important**: this tab is a calculator, not an executor. Clicking buttons does not record a trade. Recording happens through Manage Portfolio.

### A5 — Concentration tab v1

Implement the Concentration sub-tab. Layout: KPI strip at the top with three cards — Top-1 Position % (largest single position), Top-3 Concentration % (sum of top 3), Herfindahl Index (sum of squared weights, ×10,000 for readability — a rough single-number diversification score where lower is better). Then two artifacts side by side using `st.columns([1, 1])`. Left: position weights as a horizontal bar chart (Plotly, sorted descending by weight), with a vertical reference line at `MAX_POSITION_WEIGHT = 35%` (same constant as A4 — share via `app/services/analytics.py` or similar). Right: currency exposure as a donut chart (EUR / USD / JPY split, by EUR value at face value — i.e. how much of the portfolio is denominated in each currency). Below both: a sortable table listing every position with weight, value, currency, thesis status. Position weight bars in the table use the same `weight-bar` mini-bar pattern from the Live Overview positions table — ideally extracted into a shared component (in scope for this ticket since A5 is the first second consumer of that pattern). Data is purely from `compute_live_positions` + `compute_portfolio_summary` (TICKET-006). No new domain logic beyond the Herfindahl helper in `app/domain/analytics.py` (TICKET-A0). Service: `app/services/analytics_concentration.py`. Acceptance includes: adding a position updates everything without code changes, weight bars sum visually to ~100% (within rounding), the 35% reference line is always visible even if no position approaches it, donut percentages sum to 100%. Out of scope: sector breakdown (needs sector tags from Panel), geography breakdown, factor exposure — those are A5.x follow-ups.

---

## Drafting checklist (the chat must walk this for each ticket)

For each ticket, before declaring it READY:

- [ ] **Bench-test the spec against the real workflow.** Open the actual data the user has — 13 positions in `data/portfolio.json` — and trace what the tab would actually show. If a calculation needs data that doesn't exist (e.g. sector tags), note it and make sure the tab works without it for v1.
- [ ] **No documented approximations.** No "use X as a proxy; Y not supported in v1." If something can't be done properly in v1, leave it out entirely and put it in "Out of scope."
- [ ] **No silent fallbacks.** If FX is unavailable for a date, the relevant card surfaces a banner, not a `1.0`. If OHLC is missing for one ticker, that one is shown as "data unavailable" in the chart, not omitted silently from a sum.
- [ ] **Test cases include at least one real-world failure mode.** "Tests pass" is necessary, not sufficient. Add a test that would observably fail if the rule were violated.
- [ ] **Files NOT to modify is explicit if the ticket is risky.** Specifically for A1 (extends `render_line_chart`), A5 (extracts weight-bar into shared component) — both touch existing files. The ticket must spell out which files those are and which existing tests must continue to pass unchanged.
- [ ] **Out of scope section is concrete.** Lists specific things the implementation agent might be tempted to add and explicitly forbids them.

---

## What's not in this handoff (and why)

- **The chart-component extension for A1 (second-line on `render_line_chart`).** That's an implementation decision; the drafting chat just needs to flag it as in-scope. The implementation agent figures out the API at code time.
- **Exact metric formulae beyond what's in `app/domain/analytics.py`.** The stats library (drafted in A0) is the contract; sub-tab tickets just consume it.
- **Performance budgets** (e.g. "page must render in <500ms"). We don't optimise for performance until we have a real bottleneck. Adding performance criteria up-front is premature.

---

## After all 6 tickets are drafted

Vivek will:
1. Move each ticket from DRAFT → READY in `BACKLOG.md`.
2. Pick A0 first; a Claude Code or Codex session implements it.
3. Once A0 is merged, A1–A5 can be picked up in any order. A1 still needs TICKET-013 merged first.

Recommended implementation order: **013 → A0 → A5 → A4 → A2 → A3 → A1.** Reason: this order goes from cheapest (A5 Concentration is just current portfolio sliced) to most data-heavy (A1 Performance needs the full NAV reconstruction working at scale). A1 last gives the NAV cache time to be battle-tested against the simpler tabs first.
