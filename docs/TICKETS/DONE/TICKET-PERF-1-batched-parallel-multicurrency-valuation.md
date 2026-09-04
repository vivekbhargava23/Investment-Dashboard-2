# TICKET-PERF-1 — Batched, parallel, multi-currency live valuation

**Status:** QUEUED
**Priority:** HIGH
**Estimated session length:** 3 – 4 hr
**Drafted by:** Vivek + Claude (Cowork review 2026-06-02)
**Implemented by:** _pending_
**Recommended model:** Opus — cross-cutting (ports + adapters + services + 4 pages), introduces concurrency, and changes money/FX conversion. A plausible-but-wrong batch or FX inversion is expensive and hard to spot.
**Milestone:** Performance & correctness
**Depends on:** None (TICKET-R5 is complementary — that one dedupes the *caches*, this one fixes the *fetch underneath them*; either order works, but coordinate the `compute_live_positions` signature so they don't conflict).

> **After this ticket merges, the app stops fetching one ticker at a time.** Every live-data screen (Overview, Analytics, Tax, Sell Simulator) currently issues one network round-trip per position, serially — a cold Overview is ~2×N sequential yfinance calls. This ticket routes all live price + OHLC fetching through a single batched/parallel path and fixes valuation so non-USD foreign currencies (e.g. JPY) convert instead of showing permanently "stale". This is the single biggest perceived-speed win in the codebase.

---

## Problem

### 1. Live prices are fetched serially, one ticker at a time

`app/services/valuation.py::compute_live_positions` loops over positions calling
`price_provider.get_current_price(ticker)` one at a time (valuation.py:46–55). Each call is
a separate `yf.Ticker(ticker).fast_info` HTTP round-trip
(`app/adapters/yfinance_price/adapter.py:29`). For ~12 positions that is 12 sequential
network calls before the page can render.

### 2. OHLC trends are then fetched serially again, over the same tickers

`app/ui/pages/overview.py::_fetch_trend_texts` (overview.py:204) loops over the **same
tickers** calling `get_ohlc_history` per ticker — another N serial round-trips for the
30-day trend column. The same per-ticker OHLC loop pattern recurs in:

- `app/services/analytics_correlation.py:145` (`build_correlation_view`)
- `app/services/analytics_performance.py:106` (benchmark series — single symbol, but in the same fetch path)
- `app/services/nav.py:184` and `:210` (NAV reconstruction + FX series)
- `app/services/analytics_technicals.py:122` (single ticker — lower priority but same call)

So a cold Overview load ≈ **2 × N serial yfinance calls** + 1 FX call. At 0.3–1s each
that's easily 8–20s.

### 3. Valuation only converts USD; every other foreign currency is marked stale

`compute_live_positions` only handles `EUR` and `USD` (valuation.py:57–76). Any other
*supported* currency falls into the `else` branch and is tagged
`"Unsupported currency: …"` → the position shows **permanently stale on Overview**, even
though the price was fetched fine. `JPY` is fully supported in the domain
(`app/domain/tickers.py:33`, `.T`/`.JP` → JPY) and Japanese names appear in the portfolio
data, so this is a live correctness bug, not a hypothetical. It also hardcodes a single
`EUR→USD` FX fetch rather than fetching a rate per distinct foreign currency.

---

## Solution

Keep the architecture honest: **batching and concurrency live in the adapter; the domain
stays pure; the port grows a batch method.** No `st.cache_data`, no threads in `domain/`.

### Step 1 — Add batch methods to the ports

`app/ports/price_feed.py`:

```python
def get_current_prices(self, tickers: Sequence[str]) -> dict[str, Money]:
    """Batch fetch. Missing/failed tickers are simply absent from the result dict
    (callers treat absence as stale). Never raises for a single bad ticker."""
```

`app/ports/market_data.py`:

```python
def get_ohlc_histories(
    self, tickers: Sequence[str], period: ChartPeriod
) -> dict[str, OhlcSeries]:
    """Batch OHLC. Per-ticker failures are omitted from the result, never raised."""
```

Single-ticker `get_current_price` / `get_ohlc_history` stay (used by Research, Company,
single-ticker paths) but become thin wrappers over the batch call where practical.

### Step 2 — Implement batching in the yfinance adapters

`app/adapters/yfinance_price/adapter.py` — implement `get_current_prices` using a
`concurrent.futures.ThreadPoolExecutor` (yfinance is blocking I/O; threads are the right
tool) or `yf.Tickers(...)`/`yf.download(...)` multi-symbol. Reuse the existing per-ticker
TTL cache: check cache first, only fetch the misses, in parallel. Same TTL semantics.

`app/adapters/yfinance_ohlc/adapter.py` — implement `get_ohlc_histories` similarly,
honouring the existing intraday/daily TTL split (`_ttl_for_period`). Cap concurrency
(e.g. 8 workers) to avoid hammering yfinance.

Currency inference, NaN handling, and error isolation must match the current single-ticker
behaviour exactly — extract the per-ticker parse into a shared helper so single and batch
paths can't drift.

### Step 3 — Generalize FX in `compute_live_positions`

Replace the EUR/USD-only block (valuation.py:57–76) with: collect the set of distinct
non-EUR currencies across positions, fetch each `EUR→<ccy>` rate **once** via the
`LiveFxProvider`, then convert. EUR positions need no rate. Any currency whose rate is
unavailable → `staleness_reason`, as today. Document the inversion direction in a comment
(the current USD code inverts `usd_to_eur`; make the general path provably correct and add a
unit test asserting a JPY position values correctly given a known rate).

### Step 4 — Route every call site through the batch path (comprehensive — no site left behind)

This is the production-grade part. Update **all** of these to fetch once, in batch:

- [ ] `services/valuation.py::compute_live_positions` — batch prices for all tickers up front.
- [ ] `ui/pages/overview.py::_fetch_trend_texts` — batch OHLC for all tickers (one call).
- [ ] `services/analytics_correlation.py::build_correlation_view` — batch OHLC over the included tickers.
- [ ] `services/nav.py` — batch the per-ticker OHLC + FX-series fetches.
- [ ] `services/analytics_technicals.py` / `analytics_performance.py` — use the batch API even for their single/benchmark symbols, so there is one fetch path, not two.

Grep acceptance: after this ticket, no module under `app/` contains a `for … in tickers:`
(or equivalent) loop that calls `get_current_price`/`get_ohlc_history` inside the loop body.

---

## Acceptance criteria

- [ ] `get_current_prices` and `get_ohlc_histories` exist on the ports and the yfinance adapters, with per-ticker error isolation (one bad ticker never fails the batch).
- [ ] Single-ticker methods still work and share the per-ticker parse/cache logic (no duplicated parsing).
- [ ] `compute_live_positions` values **any** supported currency; a JPY position with a known FX rate produces the correct EUR value (unit test).
- [ ] FX rates are fetched once per distinct foreign currency, not once per position.
- [ ] No remaining per-ticker network loop anywhere under `app/` (grep-verifiable).
- [ ] A portfolio of N positions triggers **one** batched price fetch and **one** batched OHLC fetch per render (verifiable by patching the adapter in tests and counting calls).
- [ ] Architecture preserved: threads/batching only in `adapters/`; `domain/` untouched by I/O; `lint-imports` clean.
- [ ] All tests pass; ruff / mypy / lint-imports clean.

### Manual smoke

1. `streamlit run app/ui/main.py`, open Overview cold (after Refresh). It should render in
   noticeably less time than `main` — eyeball it, and confirm the JPY position (Japan-listed
   holding) shows a live value, not "—"/stale.
2. Switch Overview → Analytics → Tax. No long re-fetch stall on each switch (the cache work
   in R5 amplifies this; even alone, batching makes each first-load fast).
3. Kill the network mid-session and Refresh: positions degrade to stale gracefully, no crash.
