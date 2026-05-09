# TICKET-A5 — Analytics: Concentration tab v1

**Status:** READY
**Priority:** P1
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-09)
**Implemented by:** _pending_
**Depends on:** TICKET-006 (`compute_live_positions`, `compute_portfolio_summary`), TICKET-A0 (page shell + `app/domain/analytics.py`), TICKET-007 (`MetricCard`), TICKET-008 (positions table weight-bar pattern — to be extracted)

> **After this ticket merges, the Concentration sub-tab on the Analytics page is fully functional.** It shows three KPI cards (Top-1 %, Top-3 %, Herfindahl Index), a horizontal bar chart of position weights with a 35% reference line, a donut chart of currency exposure, and a sortable per-position table that reuses the same weight-bar pattern from Live Overview. No historical data, no NAV reconstruction, no OHLC — purely a slice of `compute_live_positions` output. This is the simplest of the five analytics sub-tabs and the right place to start.

---

## Problem

The Analytics page currently has five empty tabs (post TICKET-A0). The Concentration tab answers a single question: **how concentrated is the portfolio right now, and where?** Specifically:

- What % of the portfolio is in the largest single position?
- What % is in the top three?
- How diversified is the portfolio overall (a single-number score)?
- Is any single position breaching the 35% concentration cap we want to flag?
- What's the currency split (EUR / USD / JPY)?

All of these are functions of *current* positions only — no time series, no OHLC, no NAV cache. The data comes entirely from `compute_live_positions` and `compute_portfolio_summary` (TICKET-006), already in production. The only new domain logic is a `herfindahl_index` helper.

This ticket is also the **first second consumer of the Live Overview's weight-bar mini-component**, which means we extract the weight-bar pattern into a shared component as part of this ticket. (A4 and A5 will both reuse it; A4 ships after.) The extraction is in scope here because we are now violating "rule of three / second consumer triggers extraction" — A5 is consumer #2.

---

## Architectural decisions implemented by this ticket

These were locked in the planning chat 2026-05-08 (see `docs/ANALYTICS_DRAFT_HANDOFF.md` § A5) and refined in the drafting chat 2026-05-09.

### 1. Data source: live positions only

The Concentration tab reads exclusively from `compute_live_positions(...)` and `compute_portfolio_summary(...)` (TICKET-006). It does **not** call:

- `get_nav_series` (TICKET-013) — no time axis here
- `OhlcDataProvider` directly — no historical bars
- The repository or FIFO engine directly — orchestration is the service layer's job, and the existing valuation service already does it

This keeps the tab cheap and keeps it working even if yfinance is partially down, because per-ticker failure isolation in `compute_live_positions` already returns positions with a `staleness` flag.

### 2. New domain function: `herfindahl_index`

Lives in `app/domain/analytics.py` (the stats library introduced in TICKET-A0). Signature:

```python
def herfindahl_index(weights_pct: list[Decimal]) -> Decimal:
    """
    Return the Herfindahl–Hirschman Index from a list of weights expressed
    in percent (e.g. [35, 25, 10, 30]).

    Formula: Σ(w_i)^2, where w_i is each weight in percent.
    Result is in the same units as if weights were on 0–100 scale, so a
    fully diversified 10-position portfolio at 10% each yields 1000;
    a single-position portfolio at 100% yields 10000.

    Edge cases:
    - Empty list → raise ValueError
    - Any negative weight → raise ValueError (weights must be ≥ 0)
    - Weights need not sum to 100 (caller's responsibility); we square what we get.
    """
```

Decision: weights are in **percent** (0–100), not fractions (0–1). Reason: the rest of the analytics layer (and the UI) deals in percent. Squaring a fraction `0.35` gives `0.1225`; squaring a percent `35` gives `1225`. The percent form yields integer-readable numbers in the user-facing range 0–10,000, which is the convention we use in the KPI card.

Edge case for the empty list: raise `ValueError`, consistent with the rest of `app/domain/analytics.py` (decision §5 in TICKET-A0). The service layer renders an empty state when no positions exist.

### 3. New service module: `app/services/analytics_concentration.py`

One service function:

```python
def compute_concentration_view(
    positions: list[LivePosition],
    summary: PortfolioSummary,
) -> ConcentrationView:
    ...
```

Returns a `ConcentrationView` dataclass (frozen Pydantic model in `app/domain/analytics_views.py` — see decision §4) containing everything the UI needs:

```python
class ConcentrationView(BaseModel):
    model_config = ConfigDict(frozen=True)

    top_1_pct: Decimal              # weight of largest position
    top_3_pct: Decimal              # sum of top 3 weights
    herfindahl: Decimal             # 0–10000 scale
    weights_by_ticker: list[tuple[str, Decimal]]  # (ticker, weight_pct), sorted desc
    currency_split: list[tuple[Currency, Decimal]]  # (currency, eur_value), sorted desc
    rows: list[ConcentrationRow]    # per-position table rows
```

The service does the math; the UI renders. No business logic in the page.

### 4. New domain models: `ConcentrationView`, `ConcentrationRow`

Lives in `app/domain/analytics_views.py` — a new module that will collect view-models for all analytics sub-tabs (A1–A5 each add their own to this file or to a parallel one). Decision: **one file per sub-tab is the eventual goal, but A5 starts the pattern by introducing the file with just its own models.**

```python
class ConcentrationRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    name: str
    weight_pct: Decimal
    value_eur: Money       # EUR-denominated, even for USD/JPY positions
    currency: Currency     # native currency of the underlying instrument
    thesis_status: str | None  # carried through from LivePosition; can be None
```

Note: `name` comes from the existing `LivePosition` model. If `LivePosition` doesn't already carry a display name, the service falls back to `ticker` and the implementer adds a follow-up note (do NOT add a name lookup here — that's scope creep).

### 5. Currency exposure calculation

Currency split groups EUR-valued positions by their **native currency**, not by their displayed value's currency (which is always EUR for `LivePosition.market_value_eur`). The aggregation:

```python
for pos in positions:
    bucket[pos.currency] += pos.market_value_eur.amount
```

So a USD position worth €1,000 contributes `(USD, 1000)` to the bucket. A reader of the donut chart sees "30% USD" and reads it as "30% of my portfolio's EUR value is in USD-denominated instruments." This is the natural meaning and matches the question the user is asking.

Edge case: if a position has `market_value_eur` of zero (e.g. fully realised, no open lots), it contributes nothing. If all positions are zero, `currency_split` is `[]` and the donut shows an empty state.

### 6. Weight-bar component extraction

Live Overview (TICKET-008) has an inline weight-bar render — a styled `<div>` with two layered bars (background = max scale, foreground = position weight, coloured by bucket). A5 needs the same pattern in its table.

**This ticket extracts the weight-bar into `app/ui/components/weight_bar.py`** and updates Live Overview to use the extracted component, in the same PR. The extraction is justified because:

1. A5 is the second consumer; the rule-of-three becomes rule-of-second-consumer here because the inline implementation is ~25 lines of HTML/CSS that would otherwise be copy-pasted.
2. A4 (Position Sizer, drafted as the next ticket) is the third consumer; getting the component right now saves a refactor in A4.
3. The change to Live Overview is purely structural — the rendered HTML must be byte-identical to before. Tests in `tests/unit/ui/test_overview_table.py` (or wherever the existing weight-bar tests live) must continue to pass without modification.

Component signature:

```python
def render_weight_bar(
    weight_pct: Decimal,
    *,
    scale_max: Decimal = Decimal(40),
    danger_threshold: Decimal = Decimal(35),
    warning_threshold: Decimal = Decimal(25),
) -> str:
    """
    Returns a sanitised HTML snippet for inline rendering. Caller passes
    it to render_html (TICKET-008b).

    Colour buckets:
      - weight_pct > danger_threshold → red
      - warning_threshold < weight_pct ≤ danger_threshold → amber
      - weight_pct ≤ warning_threshold → green
    """
```

The thresholds default to the same values Live Overview uses today; A4 will pass different thresholds for its post-trade weight bar.

### 7. The 35% reference line

Both the horizontal bar chart (left column) and the per-position table (below) show a vertical reference at 35%. The constant is **introduced in this ticket** at `app/services/analytics_concentration.py`:

```python
MAX_POSITION_WEIGHT_PCT: Final[Decimal] = Decimal(35)
BAR_SCALE_MAX_PCT: Final[Decimal] = Decimal(40)
```

A4 (Position Sizer) will need the same constants. Decision: **A4 will import them from this module** rather than introducing a third location. We do not pre-create a `app/services/analytics.py` shared-constants module; that's premature. If a third sub-tab needs the same constants (none does in v1), the extraction triggers then.

This is consistent with TICKET-A0 decision §9 ("`MAX_POSITION_WEIGHT` is **not** introduced in A0") — A5 is the natural home because A5 is the first consumer.

### 8. Plotly directly for the bar chart and donut

Neither the horizontal bar chart of weights nor the currency donut fits any existing component in `app/ui/components/charts.py`. Both are added here as new render functions:

- `render_weight_bar_chart(weights: list[tuple[str, Decimal]], *, max_position_pct: Decimal) -> Figure`
- `render_currency_donut(split: list[tuple[Currency, Decimal]]) -> Figure`

Both functions go in `app/ui/components/charts.py` (the same module that hosts `render_candlestick`, `render_line_chart`, `render_sparkline`). They use the same chart-style helpers (`app/ui/components/_chart_styles.py`) so visually they match the existing charts.

These are pure render functions — no data fetching, no business logic, just Plotly figure construction. Tests for them are smoke tests (does the figure render, does it have the right number of traces, does the reference line exist).

### 9. KPI strip uses existing `MetricCard`

The three KPI cards (Top-1 %, Top-3 %, Herfindahl) use the existing `MetricCard` component (TICKET-007). Colour-coding (green/amber/red) follows the same convention as Tax Dashboard and Live Overview:

| KPI | Green | Amber | Red |
|---|---|---|---|
| Top-1 % | < 25 | 25–35 | ≥ 35 |
| Top-3 % | < 50 | 50–70 | ≥ 70 |
| Herfindahl | < 1500 | 1500–2500 | ≥ 2500 |

Thresholds are constants in `app/services/analytics_concentration.py`. Reasoning for HHI thresholds: a perfectly diversified 10-position portfolio = 1000; a 5-position portfolio = 2000; a 3-position portfolio = ~3300. So the bands map roughly to "well-diversified / acceptable / concentrated."

### 10. No persistence, no state

Concentration is a pure function of current portfolio. Switching to another tab and back recomputes — that's fine; the underlying `compute_live_positions` cache absorbs the cost. No `st.session_state` writes, no JSON files, no settings.

### 11. Empty-portfolio handling

If `positions` is empty (new user, no positions yet), the service returns a `ConcentrationView` with all zeros and empty lists. The UI detects this and renders a single `st.info("No positions yet — add transactions in Manage Portfolio.")` instead of the KPI strip and charts. **Do not render zero-everywhere KPIs** — that's misleading.

### 12. Error handling: per-position, not page-wide

If `compute_live_positions` returns positions with `staleness="missing"` (failed to fetch price), those positions appear in the table with `value_eur = €0` and a "data unavailable" indicator. They contribute zero to the weights and to the currency split. The KPI cards are computed on the positions that did resolve; a small banner above the KPI strip says "N positions have stale or missing data — affecting weights below" if any are stale.

This matches the existing Live Overview behaviour and is the principle laid out in `METHODOLOGY.md` ("No silent fallback to a default value without surfacing it").

---

## Acceptance criteria

### Domain

- [ ] `app/domain/analytics.py` gains a `herfindahl_index` function with the signature, docstring, and edge-case behaviour specified in decision §2.
- [ ] `app/domain/analytics_views.py` exists, exports `ConcentrationView` and `ConcentrationRow` (both frozen Pydantic v2 models per decision §4).
- [ ] Domain layer remains I/O-free. `import-linter` passes.

### Service

- [ ] `app/services/analytics_concentration.py` exposes `compute_concentration_view(positions, summary) -> ConcentrationView`.
- [ ] Module-level constants: `MAX_POSITION_WEIGHT_PCT = Decimal(35)`, `BAR_SCALE_MAX_PCT = Decimal(40)`, plus the KPI-threshold constants from decision §9.
- [ ] Service is a pure function (no globals, ports as parameters where applicable — though here the inputs are domain objects, not ports).
- [ ] Empty-portfolio path returns an all-zero / empty-list `ConcentrationView` rather than raising.
- [ ] Stale positions contribute €0 to weights and currency split; they are still listed in the table rows with their staleness preserved.

### UI

- [ ] `app/ui/pages/analytics.py` Concentration tab body is implemented (replacing the `st.info("Coming in TICKET-A5")` placeholder from A0).
- [ ] Tab layout: KPI strip (3 cards) → two-column row (`st.columns([1, 1])`) with weight-bar chart left and currency donut right → per-position table below.
- [ ] `app/ui/components/weight_bar.py` exists and exports `render_weight_bar` (decision §6).
- [ ] Live Overview is migrated to use `render_weight_bar`. The rendered HTML for Live Overview's weight column is byte-identical to before this ticket (verified by existing tests passing without modification).
- [ ] `app/ui/components/charts.py` gains `render_weight_bar_chart` and `render_currency_donut`. Both use existing chart styles.
- [ ] Empty-portfolio state renders the `st.info` message specified in decision §11.
- [ ] Stale-position banner renders above the KPI strip when applicable (decision §12).

### Tests

- [ ] `pytest`, `ruff check .`, `mypy app/`, `lint-imports` all green.
- [ ] All existing tests pass without modification (in particular, the existing Live Overview weight-bar tests must pass after the extraction — the rendered HTML must be byte-identical).
- [ ] New tests listed under "Test cases" below.

### Bookkeeping

- [ ] `docs/SESSION_LOG.md` appended.
- [ ] `docs/PROJECT_STATE.md` updated: TICKET-A5 → IN_REVIEW.
- [ ] `docs/TICKETS/BACKLOG.md` updated: TICKET-A5 row → IN_REVIEW.
- [ ] Ticket file `Status:` → `IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.

---

## Files created

```
app/domain/analytics_views.py
app/services/analytics_concentration.py
app/ui/components/weight_bar.py
tests/unit/domain/test_analytics_views.py
tests/unit/domain/test_herfindahl.py            # or extend test_analytics.py
tests/unit/services/test_analytics_concentration.py
tests/unit/ui/test_weight_bar_component.py
tests/unit/ui/test_concentration_tab.py
```

## Files modified

```
app/domain/analytics.py                ← add herfindahl_index
app/domain/__init__.py                 ← export ConcentrationView, ConcentrationRow
app/ui/pages/analytics.py              ← replace Concentration placeholder with real tab body
app/ui/components/charts.py            ← add render_weight_bar_chart, render_currency_donut
app/ui/pages/overview.py               ← migrate to render_weight_bar (no behaviour change)
docs/PROJECT_STATE.md                  ← TICKET-A5 → IN_REVIEW, Next up updated
docs/SESSION_LOG.md                    ← new session entry
docs/TICKETS/BACKLOG.md                ← TICKET-A5 row → IN_REVIEW
docs/TICKETS/TICKET-A5-concentration-tab.md  ← Status: IN_REVIEW
```

## Files NOT to modify

- `app/domain/fifo.py`, `app/domain/tax.py`, `app/domain/positions.py` — out of scope.
- `app/services/valuation.py` — Concentration consumes its output; do not change it.
- `app/services/nav.py` — Concentration does not use NAV.
- `app/adapters/*` — no adapter changes.
- `app/ui/pages/research.py`, `app/ui/pages/manage.py`, `app/ui/pages/tax.py` — out of scope.
- `app/ui/components/_chart_styles.py` — reuse existing styles; do not add new ones unless necessary, and if necessary, justify in commit message.
- The HTML output of Live Overview's positions table — extraction must be transparent. If you find yourself changing the existing tests in `tests/unit/ui/` to make them pass, **stop**: the extraction is wrong.
- `pyproject.toml` / dependencies — no new packages.
- `app/ui/components/sidebar.py` — Analytics is already registered (TICKET-A0). Do not re-register.

---

## Out of scope

- ❌ **Sector breakdown.** Needs sector tags on positions, which we don't have. Comes after the Panel framework lands.
- ❌ **Geography breakdown.** Same reason — needs region tags.
- ❌ **Factor exposure** (growth/value, large/small cap, etc.). Same reason.
- ❌ **Concentration over time.** No time axis here. If a future ticket wants "Top-1 % over the last year," that's a follow-up using NAV reconstruction logic similar to A1.
- ❌ **Drill-down from a bar in the chart to the position detail.** Would need either a modal or a routing change. Not in v1.
- ❌ **Editing the 35% threshold from the UI.** Constant in code. A future Settings page may surface it; not now.
- ❌ **Hover tooltips on the donut showing tickers per currency.** Plotly's default donut tooltips show the currency label and the % — that's enough. Tooltip customisation can be a follow-up.
- ❌ **Exporting the table to CSV.** No export buttons in v1.
- ❌ **Real-time auto-refresh.** Render once on tab load; user reloads to refresh.
- ❌ **Adding `MAX_POSITION_WEIGHT_PCT` to a shared `analytics.py` constants module.** Lives in `analytics_concentration.py`; A4 imports from there. (Decision §7.)
- ❌ **Refactoring the existing Live Overview weight-bar tests.** They must continue to pass without changes after the extraction. If they don't, the extraction is wrong.

---

## Test cases

### Domain — `herfindahl_index`

1. `herfindahl_index([Decimal(100)])` → `Decimal(10000)` (single position, fully concentrated).
2. `herfindahl_index([Decimal(10)] * 10)` → `Decimal(1000)` (perfectly diversified 10-position).
3. `herfindahl_index([Decimal(50), Decimal(50)])` → `Decimal(5000)`.
4. `herfindahl_index([])` raises `ValueError`.
5. `herfindahl_index([Decimal(50), Decimal(-10)])` raises `ValueError` (negative weight).
6. `herfindahl_index([Decimal("33.33"), Decimal("33.33"), Decimal("33.34")])` is approximately `3333.33` — verifies decimal precision is preserved.

### Domain — `ConcentrationView` / `ConcentrationRow`

7. Both models are frozen — assignment after construction raises.
8. `ConcentrationRow.weight_pct` validator rejects negative values.
9. `ConcentrationView.top_3_pct >= ConcentrationView.top_1_pct` is enforced (validator) — top-3 must include top-1.
10. Round-trip serialise → deserialise via Pydantic preserves `Decimal` precision.

### Service — `compute_concentration_view`

11. **Realistic 13-position portfolio** (use a fixture mirroring `data/portfolio.json`'s shape — 8 USD, 4 EUR, 1 JPY, totalling ~€100k): KPI numbers match a hand-computed expected. Top-1 ticker, Top-3 sum, Herfindahl all correct to 2 decimals.
12. **Single-position portfolio**: Top-1 = 100, Top-3 = 100, Herfindahl = 10000.
13. **Empty portfolio**: returns `ConcentrationView` with `top_1_pct=0`, `top_3_pct=0`, `herfindahl=0`, all lists empty. Does not raise.
14. **Currency split**: 3 USD positions worth €1000 each, 2 EUR positions worth €500 each, 1 JPY position worth €200. Result: `[(USD, 3000), (EUR, 1000), (JPY, 200)]` in that order (descending by EUR value).
15. **Weights are descending and normalised to portfolio total**: `sum(w for _, w in weights_by_ticker)` is approximately `100` (within rounding); list is sorted descending.
16. **Stale position handling**: 3 positions, one with `staleness="missing"` and `market_value_eur = 0`. Service returns 3 rows in `rows`, but only 2 contribute to weights and currency split. Top-1 % is computed on the 2 healthy positions.
17. **Two positions with identical weights**: ordering is stable (deterministic — alphabetical by ticker as tiebreaker, documented in service module).
18. **Top-3 with only 2 positions**: `top_3_pct == top_1_pct + second_position_pct` (top-3 collapses gracefully when fewer than 3 positions exist).

### UI — `render_weight_bar` (extracted component)

19. **Byte-identity test**: feeding the same inputs as a representative Live Overview row (e.g. weight_pct=18.5) produces the same HTML string the inline version produced (snapshot test against committed expected HTML).
20. Weight `> 35` returns HTML containing the danger CSS class.
21. Weight `30` returns HTML containing the warning CSS class.
22. Weight `15` returns HTML containing the success CSS class.
23. Weight `0` returns a valid (empty foreground) bar — no exceptions.
24. Weight `45` (above scale_max=40) clips foreground to 100% — no overflow.
25. HTML is properly escaped (no raw `<script>` tags can pass through). Malicious ticker names like `"<img onerror>"` would not be passed here, but defensive escaping is verified.

### UI — `render_weight_bar_chart`, `render_currency_donut`

26. `render_weight_bar_chart` with 13 weights returns a Plotly Figure with one bar trace (13 bars), one shape (vertical line at 35), labels in the right order (descending).
27. Empty input list to `render_weight_bar_chart` returns a Figure with no bars and the reference line still present.
28. `render_currency_donut` with `[(USD, 3000), (EUR, 2000)]` returns a Figure with one Pie trace, two slices, labels USD/EUR.
29. Empty input list to `render_currency_donut` returns a Figure with an empty Pie (or annotation indicating no data — implementer choice; document in code).

### UI — Concentration tab integration

30. **Smoke test**: render the tab with a fixture portfolio, no exceptions, KPI strip and both charts render.
31. **Empty-portfolio path**: render with no positions; tab shows the `st.info("No positions yet — add transactions in Manage Portfolio.")` and nothing else (no KPIs, no charts, no table).
32. **Stale-position banner**: render with one stale position out of three; banner renders above KPI strip with the count.
33. **Live Overview unchanged**: the existing Live Overview tests pass without modification. (This is a global property of the test suite, not a Concentration-specific test.)

---

## Notes (architectural and methodological — for the implementation agent)

### On the weight-bar extraction

The biggest risk in this ticket is breaking Live Overview while extracting the weight-bar. The mitigation is:

1. **Write the new component first**, with its own unit tests (cases 19–25). Verify it compiles and tests pass.
2. **Then migrate Live Overview to use it.** Run the full test suite — Live Overview's existing tests must pass without changing them.
3. If you find yourself wanting to change a Live Overview test to make it pass, **stop**: that's a signal the extracted component's output isn't byte-identical to the inline version. Diff the rendered HTML and fix the component, not the test.

The ticket allows you to do this in two commits (one per step) within the same PR — that's preferred, because it makes the diff reviewable.

### On Plotly chart styling

`app/ui/components/_chart_styles.py` already defines colours, fonts, and layout helpers used by the existing chart components. Use them. If a colour you need isn't there, **add it to `_chart_styles.py` rather than inlining a hex code in the new render function.** This preserves the principle that chart styling is centralised.

### On the KPI thresholds

The thresholds in decision §9 are seed values. They were not derived from data — they're "looks reasonable for a 10-15 position concentrated portfolio." A future ticket may surface them in Settings. **Don't try to be clever about these now**; hardcode them as module constants and move on.

### On testing strategy

The 13-position fixture (case 11) is the most important test in this ticket. Build it once, in `tests/fixtures/concentration_fixtures.py`, and reuse across service and UI tests. Hand-compute the expected values for the fixture once and document them in a comment so future readers can verify the test isn't lying.

### On scope discipline

This ticket is the simplest of the four remaining analytics sub-tabs, but it introduces:

- A new domain function (`herfindahl_index`)
- A new view-model module (`analytics_views.py`)
- A new service module (`analytics_concentration.py`)
- A new UI component (`weight_bar.py`)
- Two new chart helpers (`render_weight_bar_chart`, `render_currency_donut`)
- A migration of an existing UI page

That's a lot of surface area. **Resist the urge to also**:

- Refactor `app/services/valuation.py` "while you're in there." Out of scope.
- Add a fourth KPI card "because the strip looks unbalanced." Three is the spec.
- Make the donut chart interactive (click to filter the table). Out of scope.
- Add a "concentration history" chart. Out of scope (no time axis).

If you spot a real bug in adjacent code, open a new ticket and link it; do not fix it here.

### On future analytics sub-tabs

After A5 merges, the patterns established here are reused by A4 (Position Sizer):

- Service module pattern: `app/services/analytics_<tab>.py` with a single `compute_<tab>_view` function returning a frozen view-model.
- View-model home: `app/domain/analytics_views.py`.
- Constants live in the first consumer's service module.
- Weight-bar component is reused (A4 passes different thresholds for the post-trade weight bar).

A2 (Correlation) and A3 (Technicals) follow the same pattern but additionally consume `OhlcDataProvider`.

### On why this ticket is the first of the four remaining analytics tickets

A5 is the simplest because:

1. No historical data — no NAV, no OHLC, no FX history.
2. Data shape is identical to what Live Overview already produces.
3. Only one new domain function (`herfindahl_index`).
4. The riskiest part (weight-bar extraction) is the only adjacent-code change, and it's small and verifiable.

Implementing A5 first lets us battle-test the analytics-module patterns (view-models, service modules, sub-tab integration) on the easiest case before A2/A3 introduce OHLC fan-out and A1 introduces NAV reconstruction at scale.
