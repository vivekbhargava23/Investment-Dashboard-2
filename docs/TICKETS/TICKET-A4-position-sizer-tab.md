# TICKET-A4 — Analytics: Position Sizer tab v1

**Status:** IN_REVIEW
**Priority:** P1
**Estimated session length:** 2.5 – 3 hr
**Drafted by:** Vivek + Claude (chat 2026-05-09)
**Implemented by:** GPT Codex (GPT-5, session 2026-05-09)
**Depends on:** TICKET-006 (`compute_live_positions`, `compute_portfolio_summary`), TICKET-A0 (page shell + `app/domain/analytics.py`), TICKET-A5 (`MAX_POSITION_WEIGHT_PCT` / `BAR_SCALE_MAX_PCT` constants, `render_weight_bar` component), TICKET-007 (`MetricCard`, card patterns)

> **After this ticket merges, the Position Sizer sub-tab on the Analytics page is fully functional.** It is a two-column calculator: inputs on the left (ticker + Buy/Sell + risk-based and weight-based parameters), results on the right (two result cards + a post-trade weight-bar preview). The tab is **a calculator, not an executor** — it computes target trade sizes and surfaces them, but recording an actual trade still happens through Manage Portfolio. No persistence, no history, no handoff in v1.

---

## Problem

The Analytics page has five tabs (post TICKET-A0). After A5 merges, the Concentration tab will be live; this ticket fills the **Position Sizer** tab. It answers two specific questions a user asks before placing a trade:

1. **"Given my risk budget and a stop-loss level, how many shares should I trade?"** — the **risk-based** sizing method, i.e. classic `(account × risk%) / (entry − stop)`.
2. **"Given a target weight in the portfolio, how many shares do I need to add or trim to get there?"** — the **weight-based** method, a delta calculation against the current position.

Both methods operate on the **current portfolio state** — total portfolio value, the selected ticker's current weight, current price, and currency. There is no historical data, no NAV reconstruction, no OHLC. Inputs are: a ticker, a Buy/Sell direction, a risk % (0.1–5), a stop-loss % (1–30), and a target weight % (1–40). Outputs are: shares-to-trade, EUR delta, risk EUR, stop price, and a post-trade weight preview against the 35% concentration cap.

The tab is the **second consumer** of the `MAX_POSITION_WEIGHT_PCT` and `BAR_SCALE_MAX_PCT` constants introduced in TICKET-A5's `app/services/analytics_concentration.py`, and the **second consumer** of the `render_weight_bar` component extracted in A5. Both are imported from their A5 locations; this ticket does not relocate them.

This ticket is a **calculator**: clicking a "Compute" or "Apply" button does not write a transaction. The user reads the result, opens Manage Portfolio in a separate flow, and records the trade there. A "send these numbers to Manage Portfolio" handoff is explicitly deferred (see Out of scope).

---

## Architectural decisions implemented by this ticket

These were locked in the planning chat 2026-05-08 (see `docs/ANALYTICS_DRAFT_HANDOFF.md` § A4) and refined in the drafting chat 2026-05-09.

### 1. Data source: live positions + summary (no time series)

The Position Sizer tab reads exclusively from `compute_live_positions(...)` and `compute_portfolio_summary(...)` (TICKET-006). It does **not** call:

- `get_nav_series` (TICKET-013) — no time axis here
- `OhlcDataProvider` directly — no historical bars
- The repository or FIFO engine directly — orchestration is the service layer's job

This matches A5's data-shape decision and keeps the tab cheap. If a position has `staleness="missing"` the tab disables the Compute action for that ticker and surfaces a banner; see decision §11.

### 2. Two methods, two result cards, side-by-side inputs

The tab is structured as a two-column grid using `st.columns([1, 1])`:

- **Left column (inputs):**
  - Ticker selector: `st.selectbox` over every owned position (same source as the Technicals tab will use). Persists selection to `st.session_state["sizer_ticker"]`. Default = first position alphabetical.
  - Buy/Sell toggle: `st.radio` horizontal, default Buy. Persists to `st.session_state["sizer_direction"]`.
  - **Current Position** card (read-only, neutral styling): weight %, market value €, last price (native currency + EUR), open lot count.
  - **Method 1 — Risk-Based** input group:
    - Risk % — `st.number_input(min=0.1, max=5.0, step=0.1, value=1.0)`
    - Stop Loss % — `st.number_input(min=1.0, max=30.0, step=0.5, value=8.0)`
  - **Method 2 — Weight-Based** input group:
    - Target Weight % — `st.number_input(min=1.0, max=40.0, step=0.5, value=15.0)`
- **Right column (results):**
  - **Method 1 result card** (green-bordered): shares to trade (signed by direction), trade € (in EUR), risk € + risk %, stop price (native currency).
  - **Method 2 result card** (blue-bordered): shares to buy/sell (signed by Buy/Sell + delta), Δ€ (signed), current weight %, target weight %.
  - **New Weight After Method 1** card: a horizontal weight-bar preview using the extracted `render_weight_bar` component (decision §6 of A5) — current weight as a faded background bar, post-trade weight as the foreground bar coloured by the same buckets. A vertical red marker is drawn at `MAX_POSITION_WEIGHT_PCT` (35).

Both result cards recompute on every input change (Streamlit's natural rerender). No "Compute" button; the recompute is automatic. (See decision §10 for why no submit button.)

### 3. New service module: `app/services/analytics_sizer.py`

One service function per method, plus a single orchestrator that returns both:

```python
def compute_sizer_view(
    *,
    positions: list[LivePosition],
    summary: PortfolioSummary,
    selected_ticker: str,
    direction: Literal["buy", "sell"],
    risk_pct: Decimal,
    stop_pct: Decimal,
    target_weight_pct: Decimal,
) -> SizerView:
    ...
```

Internally calls two pure-math helpers in `app/domain/sizing.py` (decision §4) and assembles a `SizerView` (decision §5). The service is responsible for:

- Looking up the selected position from `positions`
- Detecting `staleness` and short-circuiting to a degraded view
- FX conversion of native price → EUR via the helper in decision §7
- Bucket assignment (green/amber/red) for the post-trade weight

This module also re-exports the constants imported from `analytics_concentration.py` (decision §8), so consumers of the sizer service (the UI) have a single import surface.

### 4. New domain module: `app/domain/sizing.py` — pure math

The risk-based and weight-based formulas are pure-math functions, no I/O, no Pydantic dependencies beyond `Decimal`. They live in their own module rather than being added to `app/domain/analytics.py` because:

1. They are not statistical primitives (the `analytics.py` module is statistical aggregation: returns, vol, drawdown, correlation). Mixing trade-sizing math into it confuses the module's purpose.
2. The functions are small but have well-defined inputs and edge cases worth isolating in a dedicated test file.
3. Future trade-sizing features (Kelly criterion, position-limits, fixed-fractional) would naturally extend this module.

Signatures:

```python
def risk_based_shares(
    *,
    portfolio_value_eur: Decimal,
    risk_pct: Decimal,
    stop_pct: Decimal,
    price_eur: Decimal,
) -> Decimal:
    """
    Return the number of shares (unrounded Decimal) such that if price drops by
    stop_pct from current, the loss equals risk_pct of portfolio_value.

    Formula: (portfolio_value_eur × risk_pct/100) / (price_eur × stop_pct/100)

    Edge cases:
      - portfolio_value_eur ≤ 0 → raise ValueError
      - price_eur ≤ 0          → raise ValueError
      - risk_pct ≤ 0 or > 100  → raise ValueError
      - stop_pct ≤ 0 or > 100  → raise ValueError
    """

def weight_based_delta_shares(
    *,
    target_weight_pct: Decimal,
    current_weight_pct: Decimal,
    portfolio_value_eur: Decimal,
    price_eur: Decimal,
) -> Decimal:
    """
    Return the *signed* number of shares to add (positive) or trim (negative)
    such that the position reaches target_weight_pct of portfolio_value_eur.

    Formula: (target_weight_pct − current_weight_pct)/100 × portfolio_value_eur / price_eur

    Edge cases:
      - portfolio_value_eur ≤ 0  → raise ValueError
      - price_eur ≤ 0            → raise ValueError
      - target_weight_pct < 0    → raise ValueError
      - current_weight_pct < 0   → raise ValueError
      (Either weight may exceed 100; we don't clamp — caller's responsibility.)
    """
```

Both return **unrounded `Decimal`**. Rounding/share-fractionality is a UI concern (decision §9).

### 5. New view-model: `SizerView` in `app/domain/analytics_views.py`

A5 introduced `app/domain/analytics_views.py` for sub-tab view-models. A4 extends that file with its own:

```python
class CurrentPositionCard(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    name: str
    weight_pct: Decimal
    market_value_eur: Money
    last_price_native: Money
    last_price_eur: Money
    open_lot_count: int
    staleness: str | None  # "fresh", "stale", "missing", or None if not applicable


class RiskBasedResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    shares: Decimal              # signed (+ for buy, − for sell)
    trade_value_eur: Money       # absolute (sign carried in shares)
    risk_eur: Money              # always ≥ 0
    risk_pct_input: Decimal      # echoed back for display
    stop_price_native: Money     # entry × (1 − stop_pct/100) for buy
                                 # entry × (1 + stop_pct/100) for sell


class WeightBasedResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    shares: Decimal              # signed Δ
    delta_eur: Money             # signed Δ in EUR
    current_weight_pct: Decimal
    target_weight_pct: Decimal


class PostTradeWeightPreview(BaseModel):
    model_config = ConfigDict(frozen=True)

    current_weight_pct: Decimal
    new_weight_pct: Decimal      # after Method 1 trade
    bucket: Literal["green", "amber", "red"]


class SizerView(BaseModel):
    model_config = ConfigDict(frozen=True)

    current: CurrentPositionCard
    risk_based: RiskBasedResult | None    # None if degraded (stale/missing/zero portfolio)
    weight_based: WeightBasedResult | None
    post_trade: PostTradeWeightPreview | None
    degraded_reason: str | None           # short user-facing string when results are None
```

`degraded_reason` populates a banner above both result cards when results are `None`. Reasons in v1: `"Selected ticker has no live price."`, `"Selected ticker is stale — results may be inaccurate."` (still computes), `"Portfolio value is zero — sizing requires existing positions."`. The "stale" case is a *warning* but still computes; the "missing" and "zero" cases short-circuit.

### 6. Currency: native price for stop, EUR for trade value

A position has a native currency (e.g. USD for `AAPL`). The user thinks about the **stop price in the native currency** ("AAPL stops at $180"), but about the **trade value and risk in EUR** ("I'm risking €100"). The decision:

- `stop_price_native` is computed in native currency from the native last price and the stop %.
- `trade_value_eur`, `risk_eur`, `delta_eur` are all EUR.
- `shares` is unitless (count) — it's a number of shares regardless of currency.

The risk-based formula does the math in **EUR**: portfolio is EUR, price is converted to EUR via the position's known FX rate, the formula yields EUR-denominated risk. Then `stop_price_native` is computed separately for display, by applying the stop % to the native last price directly (no FX involved on that line).

### 7. FX helper: `to_base_eur(amount, currency, fx_rate) -> Decimal`

The handoff doc (`§ A4`) explicitly calls out the "inline-conversion-in-three-places anti-pattern". Decision: introduce a single helper at the **top of `app/services/analytics_sizer.py`**:

```python
def to_base_eur(amount: Decimal, currency: Currency, fx_rate: Decimal) -> Decimal:
    """
    Convert `amount` in `currency` to EUR using `fx_rate` (native→EUR).

    For Currency.EUR, fx_rate must be Decimal(1); we assert this to catch wiring bugs.
    For other currencies, returns amount × fx_rate.

    Caller passes the FX rate from LivePosition.fx_rate_eur (already on the model).
    This helper is a thin wrapper, but centralising it ensures all three call sites
    in this module use the same conversion semantics — no rounding here, no caching.
    """
```

This helper is module-private (`_to_base_eur` if preferred, or `to_base_eur` exported for the test). Used three times in `compute_sizer_view`:

1. Converting last price (native → EUR) for the risk-based formula's `price_eur`.
2. Converting last price (native → EUR) for the weight-based formula's `price_eur`.
3. Converting `risk_eur` and `trade_value_eur` for display (already EUR — no-op call to assert the helper handles `Currency.EUR` correctly).

If a future ticket needs the same conversion, **promote the helper to `app/services/_fx.py`** — but only when there's a second consumer. Premature shared modules are out.

### 8. Constants imported from `analytics_concentration.py`

`MAX_POSITION_WEIGHT_PCT` and `BAR_SCALE_MAX_PCT` were introduced in TICKET-A5's `app/services/analytics_concentration.py` (A5 decision §7). A4 imports them:

```python
# app/services/analytics_sizer.py
from app.services.analytics_concentration import (
    MAX_POSITION_WEIGHT_PCT,
    BAR_SCALE_MAX_PCT,
)
```

We do **not** create `app/services/analytics.py` as a shared-constants module. A5's decision §7 explicitly defers that until a third consumer exists, and A4 does not warrant it — the import from A5 is the simplest possible thing.

### 9. Share rounding is a UI concern, not a domain concern

`risk_based_shares` and `weight_based_delta_shares` return unrounded `Decimal`. The UI displays them with rounding:

- For tickers we know are integer-only (every supported instrument today — no fractional broker), display as `int(round(shares))` with a "rounded from X.XX" subtitle when the rounding delta exceeds 0.1.
- The actual `SizerView.shares` field carries the unrounded `Decimal` so future fractional-shares support is a UI change, not a domain change.

This matches the principle in `ARCHITECTURE.md` ("All formatting goes through `ui/format.py`"). Add a `format_shares(shares: Decimal) -> str` helper to `ui/format.py` if one doesn't already exist.

### 10. No submit button — recompute on every input change

Streamlit's natural model re-runs the page on every input change. A "Compute" button would add friction without value (the calculator response is instant, no I/O on the recompute path beyond the existing live-positions cache). Decision: **no buttons in the input column**. The result cards recompute on every keystroke.

The one exception is if we ever add a "Send to Manage Portfolio" handoff button (see Out of scope) — that *would* be a button, because it does a state transition. v1 has no such button.

### 11. Stale / missing / zero handling

- **`staleness="missing"`** (no price at all): the tab still renders the input column, but the **result column shows a single red banner** "Selected ticker has no live price — results unavailable." All three result cards are hidden. `SizerView.degraded_reason` is set; `risk_based`, `weight_based`, `post_trade` are all `None`.
- **`staleness="stale"`** (cached but old): tab renders normally. A small amber banner above the result cards reads "Selected ticker price is stale — results may be inaccurate." Results compute normally.
- **`portfolio_value_eur == 0`** (empty portfolio or all positions worth 0): same treatment as missing — banner explains "Portfolio has no value to size against," all result cards hidden.
- **No positions at all**: tab renders `st.info("No positions yet — add transactions in Manage Portfolio to enable sizing.")` and nothing else. Same treatment as A5's empty-portfolio path.

This matches the explicit `METHODOLOGY.md` rule: "No silent fallback to a default value without surfacing it."

### 12. No persistence; no defaults stored in state beyond ticker + direction

Risk %, Stop %, Target Weight % default to module-level constants (`DEFAULT_RISK_PCT = Decimal("1.0")`, `DEFAULT_STOP_PCT = Decimal("8.0")`, `DEFAULT_TARGET_WEIGHT_PCT = Decimal("15.0")`) on every page load. They are **not** persisted across sessions. The only state writes are the ticker and direction (decision §2), to make tab-switching feel non-jarring.

A future Settings/Panel ticket may surface defaults; v1 keeps it simple.

---

## Acceptance criteria

### Domain

- [ ] `app/domain/sizing.py` exists with `risk_based_shares` and `weight_based_delta_shares`, signatures and docstrings per decision §4.
- [ ] Both functions raise `ValueError` on the listed bad inputs.
- [ ] Both functions return unrounded `Decimal`; `weight_based_delta_shares` returns signed values.
- [ ] `app/domain/analytics_views.py` is extended (NOT replaced) with `CurrentPositionCard`, `RiskBasedResult`, `WeightBasedResult`, `PostTradeWeightPreview`, `SizerView` — all frozen Pydantic v2 models per decision §5.
- [ ] Existing `ConcentrationView` / `ConcentrationRow` exports remain unchanged.
- [ ] Domain layer remains I/O-free. `import-linter` passes.

### Service

- [ ] `app/services/analytics_sizer.py` exposes `compute_sizer_view(...)` with the keyword-only signature in decision §3.
- [ ] Module-level constants: `DEFAULT_RISK_PCT`, `DEFAULT_STOP_PCT`, `DEFAULT_TARGET_WEIGHT_PCT` per decision §12.
- [ ] `MAX_POSITION_WEIGHT_PCT` and `BAR_SCALE_MAX_PCT` are imported from `app.services.analytics_concentration` (decision §8) — they are NOT redefined here.
- [ ] `to_base_eur` helper exists per decision §7 and is used at all three call sites in `compute_sizer_view`.
- [ ] Service correctly populates `degraded_reason` and returns `None`-valued result fields when missing/zero (decision §11).
- [ ] Stale positions still compute, but `SizerView.degraded_reason` carries the warning string (decision §11).

### UI

- [ ] `app/ui/pages/analytics.py` Position Sizer tab body is implemented (replacing the `st.info("Coming in TICKET-A4")` placeholder from A0).
- [ ] Tab layout: two-column grid using `st.columns([1, 1])`. Left: ticker + direction + Current Position card + Method 1 inputs + Method 2 inputs. Right: Method 1 result card (green border) + Method 2 result card (blue border) + Post-Trade Weight preview card.
- [ ] Ticker selection persists to `st.session_state["sizer_ticker"]`; direction to `st.session_state["sizer_direction"]`.
- [ ] Risk % / Stop % / Target Weight % use `st.number_input` with the bounds, steps, and defaults specified in decision §2.
- [ ] No "Compute" button — recompute happens on every input change (decision §10).
- [ ] Post-Trade Weight preview uses the extracted `render_weight_bar` component (TICKET-A5) — passing the new (post-trade) weight as `weight_pct`, with a vertical red marker drawn at `MAX_POSITION_WEIGHT_PCT`. The component is imported, NOT re-implemented.
- [ ] Empty-portfolio path renders `st.info("No positions yet — add transactions in Manage Portfolio to enable sizing.")` — no input column, no result column (decision §11).
- [ ] Stale / missing / zero banners render with the correct severity and message (decision §11).
- [ ] Share counts display via `format_shares` in `app/ui/format.py` (decision §9).

### Tests

- [ ] `pytest`, `ruff check .`, `mypy app/`, `lint-imports` all green.
- [ ] All existing tests pass without modification (in particular, A5's tests for `analytics_concentration.py` constants must pass after A4 imports them — A4 is a consumer, not a modifier, of those constants).
- [ ] New tests listed under "Test cases" below.

### Bookkeeping

- [ ] `docs/SESSION_LOG.md` appended.
- [ ] `docs/PROJECT_STATE.md` updated: TICKET-A4 → IN_REVIEW.
- [ ] `docs/TICKETS/BACKLOG.md` updated: TICKET-A4 row → IN_REVIEW.
- [ ] Ticket file `Status:` → `IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.

---

## Files created

```
app/domain/sizing.py
app/services/analytics_sizer.py
tests/unit/domain/test_sizing.py
tests/unit/domain/test_analytics_views_sizer.py    # extends test_analytics_views.py if A5 already created it; otherwise create new
tests/unit/services/test_analytics_sizer.py
tests/unit/ui/test_sizer_tab.py
```

## Files modified

```
app/domain/analytics_views.py          ← add CurrentPositionCard, RiskBasedResult, WeightBasedResult, PostTradeWeightPreview, SizerView
app/domain/__init__.py                 ← export new view-models
app/ui/pages/analytics.py              ← replace Position Sizer placeholder with real tab body
app/ui/format.py                       ← add format_shares helper if not already present
docs/PROJECT_STATE.md                  ← TICKET-A4 → IN_REVIEW, Next up updated
docs/SESSION_LOG.md                    ← new session entry
docs/TICKETS/BACKLOG.md                ← TICKET-A4 row → IN_REVIEW
docs/TICKETS/TICKET-A4-position-sizer-tab.md  ← Status: IN_REVIEW
```

## Files NOT to modify

- `app/domain/analytics.py` — sizing math goes in `sizing.py`, not here. The statistical-primitives module is closed for sub-tab consumption.
- `app/domain/fifo.py`, `app/domain/tax.py`, `app/domain/positions.py` — out of scope.
- `app/services/valuation.py` — Position Sizer consumes its output; do not change it.
- `app/services/nav.py` — Position Sizer does not use NAV.
- `app/services/analytics_concentration.py` — A4 IMPORTS its constants. Do not modify the file. If you find yourself wanting to extract the constants into a shared `app/services/analytics.py`, **stop**: that's premature (decision §8). The import-from-A5 pattern is correct for the second consumer.
- `app/ui/components/weight_bar.py` — A4 uses the component as-is. If the post-trade preview needs different thresholds (e.g. amber at 25% vs 30%), pass them as keyword arguments per the existing `render_weight_bar` signature; do NOT modify the component.
- `app/ui/components/charts.py` — no chart changes for A4. The post-trade preview uses `render_weight_bar` (HTML), not Plotly.
- `app/ui/pages/research.py`, `app/ui/pages/manage.py`, `app/ui/pages/tax.py`, `app/ui/pages/overview.py` — out of scope.
- `app/adapters/*` — no adapter changes.
- `pyproject.toml` / dependencies — no new packages.
- `app/ui/components/sidebar.py` — Analytics is already registered (TICKET-A0). Do not re-register.

---

## Out of scope

- ❌ **Trade-ticket export to Manage Portfolio.** A "Send to Manage Portfolio" handoff (similar to the Sell Simulator's handoff in TICKET-012) is a separate ticket — A4.x. v1 is a calculator only.
- ❌ **Trailing stop or chandelier stop.** v1 supports a single % stop below entry (for buy) or above entry (for sell). Other stop types are post-v1.
- ❌ **Persistence of risk-pct / stop-pct / target-weight defaults.** Defaults are module constants reset on every page load (decision §12). A future Settings/Panel ticket may surface them.
- ❌ **Kelly criterion or other position-sizing formulas.** Risk-based and weight-based are the two methods in v1. Other formulas are post-v1, and would naturally extend `app/domain/sizing.py`.
- ❌ **Multi-leg sizing** (e.g. "size a paired long/short"). Single ticker only.
- ❌ **Backtesting the sizing rule against historical drawdowns.** No historical data in this tab.
- ❌ **Integrating Sparerpauschbetrag / tax considerations into the size suggestion.** That's the Sell Simulator's concern (TICKET-012). The Position Sizer is pre-tax.
- ❌ **Fractional shares.** Decision §9 keeps the unrounded `Decimal` in the view-model, but UI rounds to integer. Fractional-shares display is a future change.
- ❌ **Stop-price slippage / fee modelling.** The risk € calculation assumes the stop fills exactly at the stop price. v1 does not model partial fills, slippage, or commissions.
- ❌ **A "Reset" button.** Streamlit's natural rerun semantics handle this; refreshing the page restores defaults. Adding a button is friction without value.

---

## Test cases

### Domain — `risk_based_shares`

1. `risk_based_shares(portfolio_value_eur=Decimal(100_000), risk_pct=Decimal(1), stop_pct=Decimal(8), price_eur=Decimal(200))` → `Decimal("6.25")`. Hand-computed: `(100_000 × 0.01) / (200 × 0.08) = 1000 / 16 = 62.5` → wait, that's 62.5 not 6.25. Let me re-verify: `(100_000 × 1/100) = 1000` (risk EUR). `(200 × 8/100) = 16` (loss per share at stop). `1000 / 16 = 62.5`. Result is `Decimal("62.5")`.
2. `risk_based_shares(portfolio_value_eur=Decimal(50_000), risk_pct=Decimal("0.5"), stop_pct=Decimal(10), price_eur=Decimal(50))` → `Decimal("5")`. Hand: `(50_000 × 0.005) / (50 × 0.10) = 250 / 5 = 50`. Result `Decimal("50")`.
3. `risk_based_shares(portfolio_value_eur=Decimal(0), ...)` raises `ValueError`.
4. `risk_based_shares(portfolio_value_eur=Decimal(-1), ...)` raises `ValueError`.
5. `risk_based_shares(price_eur=Decimal(0), ...)` raises `ValueError`.
6. `risk_based_shares(price_eur=Decimal(-100), ...)` raises `ValueError`.
7. `risk_based_shares(risk_pct=Decimal(0), ...)` raises `ValueError`.
8. `risk_based_shares(risk_pct=Decimal(101), ...)` raises `ValueError`.
9. `risk_based_shares(stop_pct=Decimal(0), ...)` raises `ValueError`.
10. **Decimal precision is preserved**: `risk_based_shares(portfolio_value_eur=Decimal(100_000), risk_pct=Decimal("1.5"), stop_pct=Decimal("7.5"), price_eur=Decimal("123.45"))` returns the exact `Decimal` quotient — no float conversion in the formula path.

### Domain — `weight_based_delta_shares`

11. **Buy more to reach target**: `weight_based_delta_shares(target_weight_pct=Decimal(20), current_weight_pct=Decimal(15), portfolio_value_eur=Decimal(100_000), price_eur=Decimal(100))` → `Decimal(50)`. Hand: `(20−15)/100 × 100_000 / 100 = 5000/100 = 50`. Positive → buy.
12. **Trim to reach target**: `weight_based_delta_shares(target_weight_pct=Decimal(10), current_weight_pct=Decimal(15), portfolio_value_eur=Decimal(100_000), price_eur=Decimal(100))` → `Decimal(-50)`. Negative → sell.
13. **Already at target**: `weight_based_delta_shares(target_weight_pct=Decimal(15), current_weight_pct=Decimal(15), ...)` → `Decimal(0)`.
14. `weight_based_delta_shares(portfolio_value_eur=Decimal(0), ...)` raises `ValueError`.
15. `weight_based_delta_shares(price_eur=Decimal(0), ...)` raises `ValueError`.
16. `weight_based_delta_shares(target_weight_pct=Decimal(-5), ...)` raises `ValueError`.
17. `weight_based_delta_shares(current_weight_pct=Decimal(-1), ...)` raises `ValueError`.
18. **Target above 100% does not raise** (caller responsibility per docstring): `weight_based_delta_shares(target_weight_pct=Decimal(150), current_weight_pct=Decimal(50), portfolio_value_eur=Decimal(100_000), price_eur=Decimal(100))` → `Decimal(1000)` (no exception).

### Domain — view-models

19. `CurrentPositionCard`, `RiskBasedResult`, `WeightBasedResult`, `PostTradeWeightPreview`, `SizerView` are all frozen — assignment after construction raises.
20. `RiskBasedResult.shares` accepts negative values (sell direction) — no validator rejection.
21. `WeightBasedResult.shares` accepts negative values (trim) — no validator rejection.
22. `PostTradeWeightPreview.bucket` is constrained to `Literal["green", "amber", "red"]` — invalid string raises Pydantic validation error.
23. `SizerView` round-trip serialise → deserialise via Pydantic preserves `Decimal` precision and `None` fields.
24. **Existing A5 view-model tests still pass** — `ConcentrationView` / `ConcentrationRow` round-trip unchanged.

### Service — `compute_sizer_view`

25. **Realistic portfolio + happy path**: 13-position fixture (reuse A5's `tests/fixtures/concentration_fixtures.py` if available, else a parallel fixture). Selected ticker = AAPL (USD), Buy direction, risk 1%, stop 8%, target weight 20%. All three result fields populated. Numbers match hand-computed expected. `degraded_reason is None`.
26. **Sell direction inverts shares sign**: same fixture, Sell direction. `RiskBasedResult.shares` is negative. `stop_price_native` is computed as `entry × (1 + stop_pct/100)` (stop above entry for shorts).
27. **Stale ticker still computes**: fixture has one position with `staleness="stale"`. Selecting it still produces all three result cards, but `degraded_reason` is the stale-warning string.
28. **Missing ticker short-circuits**: fixture has one position with `staleness="missing"` and `market_value_eur = 0`. Selecting it: `risk_based`, `weight_based`, `post_trade` all `None`. `degraded_reason` is the no-live-price string.
29. **Zero-portfolio short-circuit**: empty `positions` list. Service raises? No — it returns `SizerView` with all `None` results and `degraded_reason="Portfolio has no value to size against."`. (UI then renders the no-positions `st.info` from acceptance criteria; service does not raise.)
30. **EUR-native ticker**: selected ticker is EUR-denominated (e.g. `IUSQ.DE`). `to_base_eur` is called with `Currency.EUR` and `fx_rate=Decimal(1)`; assertion does not trip. `stop_price_native` and EUR figures all match (no FX conversion happens for the stop math; the EUR-native check is a wiring sanity test).
31. **JPY ticker FX conversion**: selected ticker is JPY-denominated (e.g. `5631.T`), price ¥3000, fx_rate `0.0061`. `risk_based.trade_value_eur` and `risk_based.risk_eur` are EUR; `stop_price_native` is in JPY (`¥3000 × (1 - 0.08) = ¥2760`).
32. **Post-trade weight bucket assignment**: with current weight 20% and a risk-based trade adding to a new weight of 36%, `PostTradeWeightPreview.bucket == "red"` (above MAX_POSITION_WEIGHT_PCT). At 30% → `"amber"`. At 18% → `"green"`.
33. **Bucket boundaries**: exactly 35% → `"red"` (boundary inclusive at the cap). Exactly 25% → `"amber"` (matches A5's bucketing convention; verify against `render_weight_bar` thresholds).
34. **Constants imported from A5**: `analytics_sizer.MAX_POSITION_WEIGHT_PCT is analytics_concentration.MAX_POSITION_WEIGHT_PCT` (object identity check confirms re-import, not redefinition).
35. **`to_base_eur` rejects mismatched EUR fx_rate**: `to_base_eur(Decimal(100), Currency.EUR, Decimal("1.1"))` raises `AssertionError` (or `ValueError` — implementer's choice; document in docstring).

### UI — Position Sizer tab integration

36. **Smoke test**: render the tab with the fixture portfolio, no exceptions, both columns render, all three result cards visible.
37. **Empty-portfolio path**: render with no positions; tab shows the `st.info("No positions yet — add transactions in Manage Portfolio to enable sizing.")` and nothing else (no inputs, no results, no banners).
38. **Stale-position banner**: render with the selected ticker stale; amber banner above results, results still visible.
39. **Missing-position banner**: render with the selected ticker missing; red banner above the result column, all three result cards hidden.
40. **Ticker switch updates atomically**: simulate selecting ticker A then ticker B. The Current Position card, both result cards, and the post-trade preview all reflect ticker B's data — no stale fragments from ticker A.
41. **Direction toggle inverts sign in display**: switching Buy → Sell flips the sign on the displayed share counts and the stop-price-relative-to-entry direction.
42. **Input change triggers recompute**: changing Risk % from 1.0 to 2.0 doubles the risk-based shares and risk EUR (within rounding). Hand-computed delta verified.
43. **Weight-bar preview uses `render_weight_bar`**: assert the rendered HTML for the post-trade preview comes from the imported component (e.g. by patching `render_weight_bar` and verifying it was called with the new-weight value).
44. **A5 Live Overview unchanged**: existing Live Overview tests pass without modification (global property; A4 must not regress A5's extraction work).
45. **`format_shares` is used**: assert the displayed share count goes through `app.ui.format.format_shares` (e.g. by patching the helper and verifying call). Negative values render with a leading `−` sign per existing format conventions.

---

## Notes (architectural and methodological — for the implementation agent)

### On the calculator-not-executor distinction

This tab does math and shows numbers. **It does not record trades.** The temptation is real: the Sell Simulator (TICKET-012) has a "send to Manage Portfolio" handoff, and it would feel natural to add the same here. **Resist it for v1.** Reasons:

1. The Sell Simulator's handoff is for a *specific known sell* (chosen lots at a chosen price). The Sizer's output is *aspirational* (a target share count assuming an entry price that will move by the time the user actually trades).
2. Recording trades requires real broker confirmations (price, quantity, fees) — the Sizer doesn't have those.
3. Adding the handoff button means deciding whether clicking it pre-fills Manage Portfolio's Buy form or its Sell form, what happens if the user navigates away mid-flow, etc. That's a separate ticket worth (A4.x).

If you find yourself implementing a "Send to Manage Portfolio" button, **stop**: open A4.x.

### On the import-from-A5 pattern

A4 imports `MAX_POSITION_WEIGHT_PCT` and `BAR_SCALE_MAX_PCT` from `app/services/analytics_concentration.py` (decision §8). This is the **second consumer** pattern: A5 introduced the constants, A4 imports them. **Do not extract them into a shared module.** That's a *third*-consumer trigger, and A4 is the second.

If you find a third consumer in your work (you shouldn't — A1/A2/A3 don't need these constants), open a follow-up ticket to extract; do not extract here.

### On the FX helper

Decision §7 introduces `to_base_eur` as a **module-private** helper. The handoff doc explicitly called out the "inline-conversion-in-three-places anti-pattern". Implement the helper, use it three times, and resist the urge to:

- Generalise it to handle FX caching (out of scope; the cache is one layer up)
- Move it to a shared `app/services/_fx.py` (premature; second consumer triggers extraction, and A4 is the only consumer right now)
- Add rounding inside the helper (rounding is a UI concern; decision §9)

### On the new domain module `sizing.py`

`app/domain/analytics.py` is the **statistics primitives** module — returns, vol, drawdown, correlation. Adding sizing math to it would muddy that purpose. `sizing.py` is a small new module with a clear role: pure-math sizing formulas. Future sizing methods (Kelly, fixed-fractional, percent-of-volatility) extend it naturally without touching `analytics.py`.

If you find yourself adding `risk_based_shares` to `analytics.py` "because it's analytics math too", **stop** — that's the wrong module. The split is intentional.

### On testing strategy

The 13-position fixture from A5 (case 25) is the most important UI/service test. **Reuse A5's fixture file** rather than building a parallel one. If A5's fixture file (`tests/fixtures/concentration_fixtures.py`) doesn't yet exist (e.g. A5 didn't break it out into a fixture file and instead inlined the data), **break it out as part of this ticket** — that's a small refactor in scope here, since you're now its second consumer.

The pure-math domain tests (cases 1–18) are the foundation. Hand-compute the expected values for each non-trivial case and document them in the test as a comment ("# (100k × 1%) / (200 × 8%) = 1000 / 16 = 62.5"). Future readers should be able to verify the test isn't lying without re-deriving the formula.

### On scope discipline

This ticket introduces:

- A new domain module (`sizing.py`)
- A new service module (`analytics_sizer.py`)
- Five new view-models in an existing module (`analytics_views.py`)
- An FX helper
- A UI tab body
- Possibly a new format helper (`format_shares`)

It does NOT introduce:

- A new chart component (the post-trade preview reuses `render_weight_bar`)
- A new persistence layer
- A new adapter
- A new sidebar entry
- A new ADR (no architectural change)

That's a moderate ticket — bigger than A5's pure additions (because A5 also did the weight-bar extraction migration), comparable in line count, but with simpler integration risk because A5 already paved the analytics-tab pattern.

**Resist the urge to also**:

- Refactor `compute_live_positions` "while you're in there." Out of scope.
- Add a fourth result card "to balance the right column." Three is the spec.
- Make the weight-bar preview animated. Out of scope; the static bar is the spec.
- Add tooltips explaining the formulas. The card layout + result labels are sufficient; tooltips are a follow-up.

If you spot a real bug in adjacent code, open a new ticket and link it; do not fix it here.

### On future analytics sub-tabs

After A4 merges, the patterns are doubly-confirmed for A2 and A3:

- Service module: `app/services/analytics_<tab>.py` with a single `compute_<tab>_view` function returning a frozen view-model.
- View-model home: `app/domain/analytics_views.py` (extended, not replaced).
- Constants live in the first consumer's service module; second consumer imports.
- New domain primitives go in their own module if not statistical (e.g. `sizing.py` here). Statistical primitives go in `analytics.py`.

A2 (Correlation) consumes `analytics.correlation_matrix` directly; no new domain module. A3 (Technicals) consumes `analytics.sma` and `analytics.rsi` directly; no new domain module. Both follow the pattern A4 and A5 establish for the service/view-model layer.

### On why this ticket is the second of the four remaining analytics tickets

A4 is second-simplest after A5 because:

1. No historical data — uses only `compute_live_positions` output.
2. No new chart components — reuses A5's `render_weight_bar`.
3. Pure-math domain functions with well-defined formulas — easy to hand-verify and unit-test.
4. The riskiest part (importing from A5's `analytics_concentration.py`) is a one-line import.

A2 and A3 introduce OHLC fan-out (one historical-bar fetch per position for A2; one per selected ticker for A3) and Plotly heatmap/RSI panels. A1 introduces the full NAV reconstruction pipeline. Doing A4 second lets the analytics-tab patterns settle on calculator-style tabs before the data-heavy ones land.
