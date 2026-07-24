# TICKET-RD4 — Analytics split + explain-this-number

Verification of the per-tab `analytics/` package split and the reusable
explain-this-number component wired onto the Concentration tab's Herfindahl KPI.

Scenario: sandbox portfolio seeded with two USD positions (AAPL, MSFT) via
`tools/app_sandbox.sh` on port 8599. Live prices from yfinance.

- `performance_tab.png` — Performance tab renders through the new
  `app.ui.pages.analytics` package (KPIs, indexed line chart vs SPY, drawdown
  panel). Confirms the route is unchanged after the split.
- `concentration_tab.png` — Concentration tab. Top-1/Top-3 stay plain KPI tiles;
  Herfindahl now renders through `render_explainable_metric` with value + a
  one-line meaning + a `how?` popover button.
- `herfindahl_how_popover.png` — the `how?` popover open: HHI formula, the actual
  per-position weights (AAPL 63.2%, MSFT 36.8%), the source note, and the
  "Ask AI to explain this number" affordance (no inference backend this ticket).
