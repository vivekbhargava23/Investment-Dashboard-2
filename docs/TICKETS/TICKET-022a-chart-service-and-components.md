# TICKET-022a — Chart service + Plotly components (OHLC, line, sparkline)

**Status:** DRAFT
**Priority:** P1
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-06)
**Implemented by:** _pending_
**Depends on:** TICKETs 001 (domain — Money, Currency), 004-005 (yfinance adapter — extending), 006 (valuation service patterns), 020 (TickerResolver — for "any ticker" lookups)

> **After this ticket merges, the dashboard has a reusable charting layer.** Three render functions — `render_candlestick`, `render_line_chart`, `render_sparkline` — that can be called from any page. They consume an `OhlcDataProvider` port and a chart-period selector, and return Plotly figures rendered via `st.plotly_chart`. The data layer (`app/services/market_data.py`) caches OHLC history at the service level for 15 minutes intraday and 24 hours for daily bars. **No page consumes these yet** — TICKET-022b does that. This is the foundation.

---

## Problem

Two needs make charting unavoidable:

1. **Visualising owned positions.** The Live Overview today shows ticker + price + EUR value as text. Vivek can't see whether NVDA is breaking out, consolidating, or rolling over — only the current snapshot. A 6-month line chart per position, or a sparkline inline in the table, makes the position table 5x more informative.

2. **Researching new tickers.** Vivek's panel discussions surface 5–10 candidate names per session (Session 1 introduced 10). To form a view on each, he needs to see the chart. Today this means switching to a separate site (TradingView, Yahoo Finance) — a context switch that breaks the dashboard's value as a single source of truth.

The mockup (`Investment_Dashboard.html`) uses pure-SVG mini-charts (line + bar + pie). That works for one specific layout but is not reusable. We want a **first-class charting module** that any current or future page can call.

This ticket builds the module *without* consuming it from any user-facing page. TICKET-022b is the consumer — Research page + Overview integration. Splitting the work this way keeps PRs small and lets the chart components be tested in isolation before being deployed in real UI.

---

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-06.

### 1. Plotly is the chart library

Three options were considered:

- **Plotly** — has built-in candlestick, line, scatter; renders client-side as SVG; interactive (hover, zoom, pan); free; well-supported in Streamlit via `st.plotly_chart`. **Chosen.**
- **lightweight-charts (TradingView)** — gorgeous, native-feeling, but requires a custom Streamlit component. Adds a JS dependency to maintain. Rejected for v1.
- **Bokeh / Altair** — comparable to Plotly but with smaller communities and less Streamlit-native polish.

Plotly is the cheapest path to "charts that look fine and work everywhere." If we ever outgrow it (specifically, if zooming/scrolling on candlesticks feels sluggish), we can re-evaluate; a swap is contained inside `app/ui/components/charts.py`.

### 2. New port: `OhlcDataProvider`

Mirrors the pattern of `PriceProvider`, `FxProvider`, `TickerResolver`. Single method:

```python
class OhlcDataProvider(Protocol):
    def get_ohlc_history(
        self,
        ticker: str,
        period: ChartPeriod,
    ) -> OhlcSeries: ...
    def clear_cache(self) -> None: ...
```

Why a separate port: same logic as TICKET-020. A future Finnhub or Alpha Vantage adapter could provide OHLC without providing prices/FX. The yfinance adapter implements all four Protocols today; tomorrow's adapter might split them.

### 3. New domain types: `ChartPeriod`, `OhlcBar`, `OhlcSeries`

Live in `app/domain/market_data.py` (new module):

```python
class ChartPeriod(StrEnum):
    ONE_DAY = "1d"        # intraday, 5-min bars
    FIVE_DAY = "5d"       # intraday, 15-min bars
    ONE_MONTH = "1mo"     # daily bars
    THREE_MONTH = "3mo"
    SIX_MONTH = "6mo"
    ONE_YEAR = "1y"
    TWO_YEAR = "2y"
    FIVE_YEAR = "5y"
    YEAR_TO_DATE = "ytd"

class OhlcBar(BaseModel):
    model_config = ConfigDict(frozen=True)
    timestamp: datetime  # UTC
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None  # may be None for some intraday data

class OhlcSeries(BaseModel):
    model_config = ConfigDict(frozen=True)
    ticker: str
    currency: Currency
    period: ChartPeriod
    bars: tuple[OhlcBar, ...]  # ordered chronologically
    fetched_at: datetime
```

Decimals not floats: same discipline as `Money`. Floats accumulate error in long histories.

`volume` is `int | None` because some yfinance responses (intraday for European tickers) come back without volume.

### 4. New service: `app/services/market_data.py`

Single function: `get_ohlc_history(ticker, period, *, provider) -> OhlcSeries`. Service-level cache via `@lru_cache` keyed on `(ticker, period)`. **This is a deviation from the "service layer is stateless" rule (ADR established in TICKET-006)** — and a deliberate one. Justification in §6 below.

### 5. Three render functions, one stylesheet

`app/ui/components/charts.py` exposes:

```python
def render_candlestick(series: OhlcSeries, *, height: int = 400) -> None: ...
def render_line_chart(series: OhlcSeries, *, height: int = 200, color: str | None = None) -> None: ...
def render_sparkline(series: OhlcSeries, *, height: int = 40, width: int = 120) -> None: ...
```

Each takes a pre-fetched `OhlcSeries` and renders a Plotly figure via `st.plotly_chart`. The components are pure UI — they do not fetch. The caller fetches via the service, then passes the result. This separates "what to show" (component) from "where the data comes from" (service).

A single Plotly layout config — dark background, no gridlines, minimal axes for sparkline, full axes for candlestick — lives in `app/ui/components/_chart_styles.py` and is reused across all three.

### 6. Why service-level caching is justified here (and only here)

TICKET-006's discipline is: services are stateless; caches live at the adapter layer (low) and the Streamlit `@st.cache_data` layer (high). For `compute_live_positions`, this works because the service composes other ports — the caching is naturally pushed to the adapter.

OHLC fetches are different:
- yfinance's adapter cache is for *current* prices (60-second TTL) and *historical close on a date* (infinite). Neither shape fits "6-month daily history" — that data point is bigger and has its own staleness curve.
- Adding OHLC caching to the yfinance adapter would mean a third caching strategy in one file. Bloated.
- The Streamlit `@st.cache_data` layer is per-page; if Overview, Research, and Performance all render charts, each Streamlit page caches its own copy. Wasteful.

A small cache *at the service layer*, scoped to OHLC only, with explicit TTL handling, is the cleanest solution. It's `@lru_cache(maxsize=64)` plus a TTL check on retrieval. The cost: the service is no longer stateless. The benefit: every page that asks for `OhlcSeries(NVDA, 6mo)` shares one cached fetch.

We accept the deviation, document it loudly in `app/services/market_data.py`'s docstring, and add a `lint-imports` exception. The cache is **invalidated by the existing Refresh button** via a new `clear_market_data_caches()` function called alongside the existing `clear_caches()`.

Going forward: any new service that needs caching must justify it the same way. Default remains stateless.

### 7. yfinance adapter extension is minimal

`app/adapters/yfinance_feed.py` gains one method: `get_ohlc_history(ticker, period) -> OhlcSeries`. Implementation calls `yfinance.Ticker(ticker).history(period=period.value, interval=_interval_for_period(period))`. The result is a pandas DataFrame; we convert to `tuple[OhlcBar, ...]` row-by-row.

Currency for the series comes from `infer_currency_from_ticker(ticker)` — TICKET-008c's helper, the canonical source. yfinance's `info["currency"]` is *not* trusted here (we cross-checked it in TICKET-020 and found bugs).

`_interval_for_period`: a private helper mapping `ChartPeriod` → yfinance interval string (`1d`/`5d` → `5m`/`15m`; everything else → `1d`). Centralised so the choice is reviewable.

### 8. No Streamlit `@st.cache_data` in this ticket

The components don't cache; the service does. Adding `@st.cache_data` on top would be a third cache layer with its own invalidation rules. The service-level cache is sufficient for v1. TICKET-022b can add `@st.cache_data` *only* if profiling shows it's needed (it almost certainly won't be).

### 9. Out-of-scope errors are surfaced, not silenced

If yfinance returns no data for a ticker (delisted, typo, market closed for too long), the adapter raises `OhlcUnavailableError(reason=...)`. The service does NOT catch this — the caller does. The render functions are not called with broken data; the caller decides how to display "chart unavailable" (a placeholder div, an `st.warning`, or skip the panel entirely).

---

## Acceptance criteria

### `app/domain/market_data.py` — new domain module

- [ ] Imports: `datetime`, `decimal.Decimal`, `enum.StrEnum`, `pydantic.{BaseModel, ConfigDict}`, `app.domain.currency.Currency`.

- [ ] `ChartPeriod` enum:
  ```python
  class ChartPeriod(StrEnum):
      ONE_DAY = "1d"
      FIVE_DAY = "5d"
      ONE_MONTH = "1mo"
      THREE_MONTH = "3mo"
      SIX_MONTH = "6mo"
      ONE_YEAR = "1y"
      TWO_YEAR = "2y"
      FIVE_YEAR = "5y"
      YEAR_TO_DATE = "ytd"
  ```
  - Values match yfinance's period strings exactly. This is intentional: zero translation needed at the adapter boundary.
  - Add a property `is_intraday: bool` returning `True` for `ONE_DAY` and `FIVE_DAY` only. Used by the rendering layer to decide whether to format x-axis as time-of-day or as date.

- [ ] `OhlcBar` — frozen Pydantic v2 model:
  - `timestamp: datetime` — UTC. Validator: must have tzinfo (ValueError on naive datetime).
  - `open: Decimal`
  - `high: Decimal`
  - `low: Decimal`
  - `close: Decimal`
  - `volume: int | None`
  - Validator: `low <= open <= high` AND `low <= close <= high` (the OHLC integrity check). On violation: raise `ValueError` with a message including the timestamp.
  - Validator: prices > 0 (negative or zero prices are data corruption).

- [ ] `OhlcSeries` — frozen Pydantic v2 model:
  - `ticker: str` (canonical, uppercase)
  - `currency: Currency`
  - `period: ChartPeriod`
  - `bars: tuple[OhlcBar, ...]`
  - `fetched_at: datetime` (UTC)
  - Validator: bars are sorted by timestamp ascending. On violation: raise `ValueError` ("OhlcSeries.bars must be sorted by timestamp").
  - Validator: bars is non-empty (zero-bar series are invalid; the adapter raises `OhlcUnavailableError` instead).
  - Helper property `latest_close: Decimal` — `self.bars[-1].close`.
  - Helper property `period_change_pct: Decimal | None` — `(latest_close - bars[0].open) / bars[0].open * 100`, or `None` if `bars[0].open == 0`.

- [ ] `OhlcUnavailableError` — exception class with `reason: str`. Mirrors the existing `PriceUnavailableError` pattern.

### `app/ports/market_data.py` — new port

- [ ] Imports from `app.domain.market_data` only.

- [ ] `OhlcDataProvider` Protocol:
  ```python
  class OhlcDataProvider(Protocol):
      def get_ohlc_history(self, ticker: str, period: ChartPeriod) -> OhlcSeries:
          """Fetch OHLC history for a ticker over a period.

          Raises OhlcUnavailableError if the ticker has no data for this period.
          """
          ...

      def clear_cache(self) -> None: ...
  ```

- [ ] Existing yfinance adapter will satisfy this Protocol (see below). No new adapter file.

### `app/adapters/yfinance_feed.py` — extend existing adapter

- [ ] Add a private `_ohlc_cache: dict[tuple[str, ChartPeriod], tuple[float, OhlcSeries]]` field. TTL: 15 minutes for intraday periods, 24 hours for daily periods.

- [ ] Add `_interval_for_period(period: ChartPeriod) -> str` helper:
  - `ONE_DAY` → `"5m"`
  - `FIVE_DAY` → `"15m"`
  - all others → `"1d"`

- [ ] Add `_ttl_for_period(period: ChartPeriod) -> float` helper:
  - intraday → `15 * 60`
  - daily → `24 * 60 * 60`

- [ ] Implement `get_ohlc_history(ticker, period)`:
  1. Cache check; respect TTL.
  2. `df = yf.Ticker(ticker).history(period=period.value, interval=_interval_for_period(period), auto_adjust=False)`. (`auto_adjust=False` keeps reported prices nominal — corporate actions render as gaps, which is what users expect on candlesticks.)
  3. If df is empty → raise `OhlcUnavailableError(reason=f"yfinance returned no data for {ticker} period={period.value}")`.
  4. Construct `bars` by iterating `df.itertuples()`. For each row:
     - `timestamp`: convert via `df.index[i].to_pydatetime().astimezone(timezone.utc)`. yfinance returns timezone-aware Timestamps.
     - `open/high/low/close`: convert via `Decimal(str(row.Open))` (string conversion avoids float→Decimal precision loss).
     - `volume`: `int(row.Volume) if pd.notna(row.Volume) else None`.
     - On any `ValueError` (e.g., OHLC integrity check fails because yfinance returned a bad row): skip the row, log a warning. **Do not abort the whole series** for one bad row.
  5. Determine `currency`: `currency = infer_currency_from_ticker(ticker)`. (TICKET-008c's helper.)
  6. Construct and validate `OhlcSeries`. Cache. Return.

- [ ] Update `clear_cache()`: also clear `_ohlc_cache`.

- [ ] **Critical: respect existing logger and exception classes.** Use the same `logging.getLogger(__name__)` instance. `OhlcUnavailableError` is the *only* new exception (the existing `PriceUnavailableError` is for current-price failures; conceptually different).

### `app/services/market_data.py` — new service module

- [ ] Module docstring loud-flags the deviation from stateless service rule:
  ```python
  """OHLC market data service with deliberate service-level caching.

  This module deviates from the stateless-service convention (TICKET-006).
  The cache here is justified because:
    - OHLC histories are large (days × bars per day) and slow to fetch (~600ms).
    - Multiple pages share the same series; per-page Streamlit caching wastes memory.
    - The adapter cache (60s on prices) doesn't fit OHLC's staleness profile.

  The cache is invalidated by clear_market_data_caches() — wired into the
  Refresh button alongside the price/FX cache invalidation.
  """
  ```

- [ ] Imports: `time`, `app.domain.market_data.{ChartPeriod, OhlcSeries, OhlcUnavailableError}`, `app.ports.market_data.OhlcDataProvider`.

- [ ] Module-level cache: `_cache: dict[tuple[str, ChartPeriod], tuple[float, OhlcSeries]] = {}`.

- [ ] Function `get_ohlc_history(ticker: str, period: ChartPeriod, *, provider: OhlcDataProvider) -> OhlcSeries`:
  1. Normalise: `ticker = ticker.strip().upper()`.
  2. Cache key: `(ticker, period)`.
  3. If hit and within TTL → return.
  4. On miss: call `provider.get_ohlc_history(ticker, period)`. Cache. Return.
  5. **Do NOT catch `OhlcUnavailableError`** — propagate to caller. The caller decides how to render "no chart available."

- [ ] TTL helper (private): same logic as the adapter's `_ttl_for_period` but lives in this module too. (Duplicated rather than shared — the service shouldn't depend on adapter internals.)

- [ ] Function `clear_market_data_caches(provider: OhlcDataProvider) -> None`:
  - Clear `_cache`.
  - Call `provider.clear_cache()` (this also flushes the adapter's `_ohlc_cache`).
  - Mirrors the existing `clear_caches()` function in `app/services/valuation.py`.

### `app/ui/components/_chart_styles.py` — Plotly styling module

- [ ] Single module with constants and a layout factory:
  ```python
  CHART_BG = "rgba(0,0,0,0)"  # transparent — inherits page bg
  GRID_COLOR = "rgba(255,255,255,0.05)"  # near-invisible faint grid
  AXIS_COLOR = "rgba(255,255,255,0.4)"
  CANDLE_UP = "#26a69a"
  CANDLE_DOWN = "#ef5350"
  LINE_COLOR_DEFAULT = "#26a69a"  # green; caller can override

  def base_layout(*, height: int, show_axes: bool = True) -> dict:
      """Plotly figure layout for dark dashboard."""
      ...
  ```

- [ ] `base_layout` returns a dict suitable for `fig.update_layout(**base_layout(height=400))`. Includes:
  - `paper_bgcolor` and `plot_bgcolor` set to `CHART_BG`.
  - `margin=dict(l=20, r=10, t=10, b=20)` — tight, dashboard-friendly.
  - `showlegend=False`.
  - `xaxis` and `yaxis` with `showgrid=show_axes`, `zeroline=False`, `color=AXIS_COLOR`.
  - For sparklines (`show_axes=False`): both axes hidden, no margin.
  - `hovermode="x unified"` for candlestick + line; `False` for sparkline.

### `app/ui/components/charts.py` — three render functions

- [ ] Imports: `streamlit as st`, `plotly.graph_objects as go`, `app.domain.market_data.OhlcSeries`, `app.ui.components._chart_styles.{base_layout, CANDLE_UP, CANDLE_DOWN, LINE_COLOR_DEFAULT}`.

- [ ] `render_candlestick(series: OhlcSeries, *, height: int = 400) -> None`:
  - Build a `go.Figure` with one `go.Candlestick` trace using series timestamps and OHLC values.
  - `increasing_line_color=CANDLE_UP`, `decreasing_line_color=CANDLE_DOWN`.
  - `xaxis_rangeslider_visible=False` (the small range slider Plotly adds is noise).
  - Apply `base_layout(height=height, show_axes=True)`.
  - X-axis tick format: if `series.period.is_intraday` → `"%H:%M"`; else `"%b %Y"`.
  - Y-axis prefix: `series.currency.value + " "` (e.g., `"USD 250"`).
  - Render via `st.plotly_chart(fig, use_container_width=True)`.

- [ ] `render_line_chart(series: OhlcSeries, *, height: int = 200, color: str | None = None) -> None`:
  - Build a `go.Figure` with one `go.Scatter(mode="lines")` using close prices.
  - Line color: `color or LINE_COLOR_DEFAULT`. Width 2.
  - Fill below line: `fill="tozeroy"` with low-alpha version of color (creates the "area chart" look from the mockup).
  - Apply `base_layout(height=height, show_axes=True)`.
  - Render via `st.plotly_chart(fig, use_container_width=True)`.

- [ ] `render_sparkline(series: OhlcSeries, *, height: int = 40, width: int = 120) -> None`:
  - Build a `go.Figure` with one `go.Scatter(mode="lines")` of close prices.
  - Color: `CANDLE_UP` if `series.period_change_pct >= 0` else `CANDLE_DOWN`. Width 1.5.
  - No fill, no axes, no grid, no hover — pure line.
  - Apply `base_layout(height=height, show_axes=False)`. Override margin to `dict(l=0, r=0, t=0, b=0)`.
  - Render via `st.plotly_chart(fig, use_container_width=False, config={"displayModeBar": False})`. Set explicit `width` to keep sparklines compact.

- [ ] Each function is **pure rendering** — takes a series, calls `st.plotly_chart`, returns `None`. No fetching, no caching, no error handling. The caller is responsible for catching `OhlcUnavailableError`.

### `app/ui/wiring.py` — expose the OHLC provider

- [ ] The yfinance adapter already implements `OhlcDataProvider` after this ticket. Add wiring:
  ```python
  @lru_cache(maxsize=1)
  def get_ohlc_data_provider() -> OhlcDataProvider:
      return _yfinance_adapter()  # same instance — adapter satisfies multiple Protocols
  ```

### `pyproject.toml` — Plotly dependency

- [ ] Add `plotly = "^5.24"` to runtime dependencies. (Plotly is large but well-cached by pip.)

### Tests

#### `tests/unit/domain/test_market_data.py` — domain validation

- [ ] **`OhlcBar` happy path:** construct with valid OHLC; equality and frozen-ness work.
- [ ] **`OhlcBar` validates OHLC integrity:** open > high → raises ValueError; close < low → raises ValueError.
- [ ] **`OhlcBar` rejects negative prices:** open=Decimal("-1") → raises ValueError.
- [ ] **`OhlcBar` rejects naive datetime:** timestamp without tzinfo → raises ValueError.
- [ ] **`OhlcSeries` validates non-empty:** zero bars → raises ValueError.
- [ ] **`OhlcSeries` validates sorting:** bars in reverse chronological order → raises ValueError.
- [ ] **`OhlcSeries.latest_close`:** matches the close of the last bar.
- [ ] **`OhlcSeries.period_change_pct`:** matches `(latest_close - first_open) / first_open * 100`. Edge case: first_open=0 → returns None.
- [ ] **`ChartPeriod.is_intraday`:** ONE_DAY → True, FIVE_DAY → True, ONE_MONTH → False, etc.

#### `tests/unit/services/test_market_data.py` — service caching

All tests use a `FakeOhlcDataProvider` (new in `tests/fakes/ohlc.py`). Zero network.

- [ ] **Cache miss → provider called, result cached:** call `get_ohlc_history("NVDA", SIX_MONTH, provider=fake)` twice. Fake's call count = 1 second time.
- [ ] **TTL miss for intraday:** prime cache; advance `time.monotonic` past 15 min; second call hits provider.
- [ ] **TTL hit for daily within 24h:** advance time 23h59m; second call uses cache.
- [ ] **TTL miss for daily after 24h:** advance time 24h+1m; second call hits provider.
- [ ] **Different periods cached independently:** call `(NVDA, SIX_MONTH)` then `(NVDA, ONE_YEAR)`. Two cache entries; provider called twice.
- [ ] **`clear_market_data_caches` clears both:** prime cache; clear; provider also `clear_cache` was called; next service call hits provider again.
- [ ] **`OhlcUnavailableError` propagates:** fake raises; service does not catch.

#### `tests/unit/adapters/test_yfinance_ohlc.py` — adapter conversion logic

Tests use `pytest-mock` to patch `yfinance.Ticker`. **Zero network.**

- [ ] **Happy path: yfinance DataFrame → OhlcSeries:** mock `Ticker.history` to return a DataFrame with 5 rows; verify resulting series has 5 bars with correct values, currency inferred from ticker, period set correctly.
- [ ] **Empty DataFrame → OhlcUnavailableError:** mock returns empty df; assert OhlcUnavailableError raised.
- [ ] **Bad row skipped:** DataFrame with one row where Open > High; that row skipped, valid rows preserved, warning logged.
- [ ] **NaN volume → None:** DataFrame with a row containing `volume=NaN`; resulting bar has `volume=None`.
- [ ] **Decimal precision preserved:** DataFrame with Open=251.378241; resulting bar has open=`Decimal("251.378241")` (no float rounding).
- [ ] **Currency inference is canonical:** mock ticker `RHM.DE`; resulting series has `currency=EUR` (regardless of what yfinance reports).
- [ ] **Cache TTL respected:** call adapter twice with intraday period; mock counter = 1. Advance time past TTL; counter = 2.
- [ ] **`_interval_for_period` mappings:** spot-check a few values.

#### `tests/unit/ui/test_chart_components.py` — render-call-shape tests

The render functions call `st.plotly_chart`. Streamlit isn't running during tests, so we use `pytest-mock` to verify the call shape. This is a smoke test — it confirms the figure is constructed, not what it looks like.

- [ ] **`render_candlestick` calls `st.plotly_chart` with a Figure containing one Candlestick trace:** mock `st.plotly_chart`; pass a known `OhlcSeries`; assert call args[0] is a `go.Figure` and `args[0].data[0].type == "candlestick"`.
- [ ] **`render_line_chart` produces a Scatter trace with mode='lines':** same pattern; assert `data[0].type == "scatter"` and `data[0].mode == "lines"`.
- [ ] **`render_sparkline` hides axes:** assert `fig.layout.xaxis.visible is False`.
- [ ] **Color override on `render_line_chart`:** call with `color="#abc123"`; assert the trace's line color matches.

#### `tests/fakes/ohlc.py` — for downstream tickets

- [ ] `FakeOhlcDataProvider` class implementing the Protocol with hardcoded series fixtures plus a counting mechanism. Used by TICKET-022b's tests.

### Lints / quality

- [ ] `pytest` — all new tests pass (~22 new).
- [ ] `ruff check .` — passes.
- [ ] `mypy app/` — passes; `app/domain/market_data.py` is in strict mode.
- [ ] `lint-imports` — passes:
  - `app/domain/market_data.py` imports from stdlib + pydantic + `app.domain.currency` only.
  - `app/ports/market_data.py` imports from `app.domain` only.
  - `app/services/market_data.py` imports from `app.domain` and `app.ports` only.
  - `app/ui/components/charts.py` imports from `app.domain`, `streamlit`, `plotly` — **no service or adapter imports.** The component is data-passing-pure.
  - `app/adapters/yfinance_feed.py` already imports from `app.ports` and yfinance; no rule change.

### State updates (per CLAUDE.md session-end ritual)

- [ ] `docs/SESSION_LOG.md` appended.
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-022a → IN_REVIEW).
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-022a row → IN_REVIEW).
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.

---

## Files created

```
app/domain/market_data.py
app/ports/market_data.py
app/services/market_data.py
app/ui/components/_chart_styles.py
app/ui/components/charts.py
tests/unit/domain/test_market_data.py
tests/unit/services/test_market_data.py
tests/unit/adapters/test_yfinance_ohlc.py
tests/unit/ui/test_chart_components.py
tests/fakes/ohlc.py
```

## Files modified

```
app/adapters/yfinance_feed.py           ← add get_ohlc_history + cache
app/adapters/__init__.py                ← if needed
app/domain/__init__.py                  ← export ChartPeriod, OhlcBar, OhlcSeries, OhlcUnavailableError
app/ports/__init__.py                   ← export OhlcDataProvider
app/ui/wiring.py                        ← add get_ohlc_data_provider singleton
pyproject.toml                          ← plotly dependency
docs/TICKETS/BACKLOG.md                 ← TICKET-022a row → IN_REVIEW
```

---

## Out of scope

- **Any UI page consuming the charts.** That is TICKET-022b. This ticket ends with foundation in place but no page calling the components.
- **Volume bars overlaid on candlesticks.** Volume is captured in `OhlcBar` but not rendered. TICKET-022b can add a sub-plot if useful.
- **Technical indicators (moving averages, RSI, MACD).** Out of scope; would require their own domain types and computation. Future ticket.
- **Comparing two tickers on one chart** (e.g., NVDA vs AVGO normalised). Useful but separate; can be added as a fourth render function later.
- **Drawing tools / annotations** (mark a buy date, mark a thesis-change date). Would tie charts to portfolio data. Best as a follow-up after TICKET-022b proves the simple version works.
- **Persisting OHLC history to disk.** Same logic as TICKET-021's ticker cache could apply, but daily OHLC for a year is ~500 KB per ticker — multiplied by a watchlist, this hits megabytes. Defer until needed.
- **Configurable color themes per user.** Hard-coded dark theme matching the dashboard.
- **Streamlit `@st.cache_data` on the render functions or service.** The service-level cache is sufficient. Adding a third cache layer needs evidence (profiling) before it's justified.
- **Mobile responsiveness.** Plotly is responsive by default via `use_container_width=True`; no special handling needed.

---

## Notes (architectural and methodological — for future AI sessions)

### Why splitting 022a and 022b matters

A single "build charting and use it everywhere" ticket would be 5+ hours, would touch a dozen files, and would mix backend with frontend in one PR. Splitting it:

- 022a is purely additive — no existing page changes — so risk is low.
- 022b becomes a focused UI ticket with the foundation already proven.
- If 022a takes longer than estimated, we don't carry that into 022b; if 022b reveals new requirements, we don't have to revisit 022a.

This is the same split discipline as TICKET-010 (engine) → TICKET-011 (page) for tax. It worked there. It works here.

### Why we don't use `@st.cache_data` for OHLC

Two reasons:

1. **Cache key complexity.** `@st.cache_data` keys on argument values. `OhlcSeries` is unhashable (frozen Pydantic, but with a tuple of bars). We'd have to hash by `(ticker, period)`, which means the function signature must take exactly those two — and that's the service signature, not the component signature. Putting the cache on the service is cleaner.
2. **Page-scope vs cross-page reuse.** Streamlit's cache is per-script-run, but the script reruns frequently. The service-level cache survives reruns and is shared across pages. For OHLC fetches that are slow, sharing is the win.

### Why the rendering components don't accept `Money` for prices

`OhlcBar` uses `Decimal` for OHLC values, not `Money`. Reason: candlesticks plot a single currency throughout. Wrapping every value in `Money(amount, currency)` would inflate memory (5x per bar) for no benefit, since the currency is held once at the series level. The components prefix the y-axis with the currency string from `series.currency`. This is the correct level of currency awareness.

### Why no IO Provider for charts (download CSV, etc.)

Tempting, but premature. The chart shows what it shows. If the user wants the data, they can copy from yfinance directly or we add a "Download CSV" button as a 5-line follow-up ticket once it's actually requested.

### Pattern for future "research" features

This ticket's structure — domain types, port, service with deliberate caching, UI components calling the service — is the template for future research-mode features (TICKET-022b's research page, future watchlists, future fundamentals views). The split between "data layer (port + service)" and "render layer (component)" should be preserved. Components never fetch.

### Cost / risk note on Plotly

Plotly's wheels are ~5 MB (compared to ~200 KB for matplotlib). For a self-hosted dashboard this is irrelevant; for any future cloud deployment it adds to the cold-start time. If we ever deploy to a memory-constrained environment, we'd revisit. For Vivek's local dev workflow: nothing to worry about.

### How TICKET-022b will use this

```python
# app/ui/pages/research.py (TICKET-022b)
from app.services.market_data import get_ohlc_history
from app.ui.components.charts import render_candlestick
from app.domain.market_data import ChartPeriod, OhlcUnavailableError

ticker = st.text_input("Ticker")  # or use TICKET-021's searchbox
if ticker:
    try:
        series = get_ohlc_history(ticker, ChartPeriod.SIX_MONTH, provider=resolver)
        render_candlestick(series, height=500)
    except OhlcUnavailableError as e:
        st.warning(f"Chart unavailable: {e.reason}")
```

The Research page is essentially this loop wrapped in period selection and metadata display. TICKET-022b adds the page; this ticket guarantees the call shape works.
