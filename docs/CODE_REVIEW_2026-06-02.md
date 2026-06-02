# Codebase review — redundancies, performance & UX

_Fresh-perspective pass, 2026-06-02. Not a ticket — a findings doc to spawn tickets from._

The architecture itself is clean: the hexagonal layering, the L1/L2/L3 split, and the
domain purity rules are genuinely well done. The problems below are almost all in the
**seam between the UI and the live-data layer** — caching and network fetching — which is
exactly where "why is it slow when I switch pages?" comes from.

I framed the review around five goals rather than a flat bug list.

---

## Goal 1 — Make the live data fetch *once per refresh*, not once per page

This is the single biggest lever for perceived speed, and it has two compounding causes.

### 1a. There are two separate live-position caches that never share state

- `overview.py` defines its **own** `@st.cache_data` wrapper, `_cached_live_positions`
  (overview.py:52), which calls `compute_live_positions(...)` directly.
- `tax.py`, `analytics.py`, and `components/sell_simulator.py` instead call
  `get_live_positions_cached(...)` — a **module-level dict cache** living in
  `valuation.py:116`.

These are two different cache stores keyed differently. So the moment you go
**Overview → Tax**, the identical portfolio valuation is recomputed from scratch — even
though Overview fetched it seconds ago. Every first visit to each page pays the full
network cost again. This is the "load time when switching" you're feeling.

**Fix:** one cache path. Pick `get_live_positions_cached` as the single entry point and
have Overview call it too; delete `overview._cached_live_positions`. (Or wrap it once in
`st.cache_data` in a shared module and route everyone through that.)

### 1b. Live prices are fetched serially, one ticker at a time

`compute_live_positions` (valuation.py:46) loops over positions and calls
`price_provider.get_current_price(ticker)` one at a time. Each call is a separate
`yf.Ticker(ticker).fast_info` HTTP round-trip (yfinance_price/adapter.py:29). For ~12
positions that's 12 sequential network calls.

Then `overview._fetch_trend_texts` (overview.py:204) loops over the **same tickers again**
calling `get_ohlc_history` per ticker — another N serial round-trips for the 30-day trend
column.

So a cold Overview load is ≈ **2 × N serial yfinance calls** plus the FX call. At
0.3–1s each that's easily 8–20 seconds.

**Fix (highest impact):** batch the fetch. yfinance supports multi-symbol requests
(`yf.download([...])` / `yf.Tickers(...)`). Add a `get_current_prices(tickers) -> dict`
to the `PriceProvider` port and a batched `get_ohlc_history` for multiple tickers. Even a
stopgap `ThreadPoolExecutor` inside the adapter (keeping the port unchanged) would cut
cold-load time roughly N×. This one change will make the whole app feel like a different
product.

---

## Goal 2 — One cache invalidation path, so "Refresh" actually refreshes

There are **three** independent cache layers for live data:

1. `st.cache_data` wrappers in pages (overview/tax/analytics).
2. The module-level `_live_positions_cache` dict in `valuation.py`.
3. The adapter-internal TTL dicts (`YfinancePriceAdapter._current_cache`,
   `YfinanceOhlcAdapter._ohlc_cache`).

The refresh/clear paths each hit a *different subset*:

- `topbar._handle_refresh` (topbar.py:22) clears market-data caches + `st.cache_data` —
  but **not** `valuation._live_positions_cache` and **not** the price adapter's cache.
- `manage.py` clears `st.cache_data` after edits (manage.py:570/635/778) — again missing
  the module-level dict used by Tax/Analytics/Simulator.

Net effect: after you edit a transaction or hit Refresh, Tax/Analytics can keep showing
**stale numbers for up to 60s** because the cache they read from was never cleared.

**Fix:** a single `clear_all_live_caches()` that clears all three layers, called from both
the Refresh button and every mutation in `manage.py`.

---

## Goal 3 — Make the cache key honest (it currently misses edits)

`transactions_signature` = `f"{len(txs)}:{max_id}"` (cache_keys.py:11, and a byte-for-byte
duplicate `_tx_sig` in valuation.py:22).

Editing a transaction **in place** (changing shares, price, or date without adding or
removing a row) leaves both the count and the max id unchanged → the signature doesn't
change → `st.cache_data` won't invalidate. The code currently papers over this by calling
`st.cache_data.clear()` after edits, but per Goal 2 that clear is incomplete.

**Fix:** make the signature reflect content — e.g. a short hash over `(id, shares,
price, date)` for all txs, or simply key on `file_mtime_key(portfolio.json)` (that helper
already exists in cache_keys.py:19 but is barely used). Then the manual `clear()` calls
become unnecessary and correctness stops depending on remembering to call them.

---

## Goal 4 — Kill duplication and dead code

- **Duplicate signature fn:** `valuation._tx_sig` ≡ `cache_keys.transactions_signature`.
  Collapse to one. (Put it somewhere domain-free both layers can import.)
- **Duplicate FX adapter instance:** `get_fx_provider()` (wiring.py:64) is a "back-compat
  shim" that news up a *second* `YfinanceLiveFxAdapter` — a separate instance with its own
  cache, distinct from `get_live_fx_provider()`. Grep for callers; if none, delete it. If
  some, point them at `get_live_fx_provider`.
- **Mixed singleton idioms in wiring:** 10 providers use `@lru_cache(maxsize=1)`, one uses
  `@st.cache_resource` (wiring.py:87). Pick one. `st.cache_resource` is the
  Streamlit-correct choice for cross-session singletons; standardizing avoids subtle
  "why does this provider behave differently" surprises.

---

## Goal 5 — Stop swallowing failures; surface them

- **The router hides every page error.** `main.render_page` (main.py:50) wraps the page
  import+render in `except Exception: pass` and falls back to the "Coming Soon"
  placeholder. A real bug in `tax.py` therefore renders as a blank "Coming Soon" with zero
  diagnostics — painful to debug and confusing to use. At minimum log the traceback and
  show `st.exception(e)` in dev.
- **Router is also a perf/UX smell.** It re-runs `importlib.import_module` + `os.path.exists`
  on every rerun and routes via query params, so each nav click re-executes the whole
  script. Streamlit-native `st.navigation`/`st.Page` would give cleaner routing and let
  Streamlit skip redundant re-imports.
- **Hardcoded business data in the UI.** `overview.py:29` `_PLACEHOLDER_THESIS_STATUS` and
  `_PLACEHOLDER_HORIZON` are ticker→status dicts baked into the UI layer. This violates
  "no business logic in UI" and the ADR-006 "classification is data" principle, and any
  ticker not in the dict silently shows "intact"/"H2" — i.e. it can be confidently wrong.
  Move to a small data file (like `isin_map.json`) and render "unknown" honestly.
- **Multi-currency valuation gap.** `compute_live_positions` only converts EUR and USD
  (valuation.py:57–76). JPY is a fully supported currency (tickers.py:33) and `5631.T`
  appears in your portfolio, but a JPY position will hit the `else` branch and be marked
  `"Unsupported currency"` → **permanently stale on Overview**. Generalize the conversion
  to fetch a rate per distinct non-EUR currency instead of hardcoding USD.
- **Minor security/robustness:** `_build_positions_table_html` interpolates the company
  `name` (from isin_map) straight into HTML unescaped (overview.py:153+). A name
  containing `<`/`>` would break the table or inject markup. Escape interpolated strings,
  or finish the `TICKET-C6` "extract inline HTML cards" direction.

---

## Suggested priority order

1. **Goal 1b — batch/parallelize the price + OHLC fetch.** Biggest felt-speed win.
2. **Goal 1a — unify the two live-position caches.** Removes redundant work on page switch.
3. **Goal 2 + 3 — one invalidation path + an honest cache key.** Fixes stale-after-edit.
4. **Goal 5 — un-swallow router errors; fix JPY valuation.** Correctness + debuggability.
5. **Goal 4 — dedupe signature fn / FX shim / wiring idioms.** Cleanup, low risk.

Each maps cleanly to a one-ticket-one-PR unit under the AGENTS.md workflow.
