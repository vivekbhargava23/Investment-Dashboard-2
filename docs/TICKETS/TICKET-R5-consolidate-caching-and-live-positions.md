# TICKET-R5 — Consolidate caching layers and live-positions fetch

**Status:** IN_PROGRESS
**Priority:** HIGH
**Estimated session length:** 2 hr
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Recommended model:** Opus — cache correctness and invalidation across multiple pages; partial clears cause stale/divergent data that is hard to detect. See expanded scope (2026-06-02) below.
**Milestone:** UI polish

---

## Problem

Three independent caches hold near-identical data and each page invalidates them in its own way:

1. **Adapter cache.** `YfinanceAdapter._ohlc_cache`, `_current_cache`, `_historical_cache`, `_resolver_cache` — in-memory with per-key TTL.
2. **Service cache.** `services/market_data.py::_cache` for OHLC — duplicates the adapter cache. The comment justifies it ("adapter cache doesn't fit OHLC's staleness profile"), but the TTLs are the same (`_INTRADAY_TTL = 15 * 60`, `_DAILY_TTL = 24 * 60 * 60`) — both layers cache the same OhlcSeries with the same expiry.
3. **Page-local Streamlit caches.** Three near-identical `@st.cache_data` wrappers for `compute_live_positions`:
   - `app/ui/pages/tax.py:125` — `_cached_live_positions`
   - `app/ui/pages/analytics.py:783` — `_cached_concentration_live_positions`
   - `app/ui/components/sell_simulator.py:38` — `_live_positions_cached`

   Each uses its own cache key shape over `transactions_signature(...)` and they don't share results. Visiting Tax → Analytics → Sell Simulator refetches the same data three times in the worst case.

`clear_market_data_caches()` and the top-bar Refresh button have to know about all three layers; adding a new live-data consumer means manually wiring a fourth.

## Solution

### Step 1 — Single service-layer cache for live positions

Add `services/valuation.py::get_live_positions_cached`:

```python
def get_live_positions_cached(
    *,
    repo: TransactionRepository,
    price_provider: PriceProvider,
    fx_provider: FxProvider,
    ttl_seconds: float = 60.0,
) -> dict[str, LivePosition]:
    """Module-level TTL cache keyed by transactions_signature.
    Single source of truth across all UI pages."""
```

Internally it does `transactions_signature(...)` keying with a module dict — same pattern as `services/market_data.py::_cache`. Add a paired `clear_live_positions_cache()`.

Delete the three page-local `_cached_*` functions; pages call `get_live_positions_cached(repo=get_repository(), price_provider=get_price_provider(), fx_provider=get_fx_provider())` directly.

### Step 2 — Collapse OHLC double-cache

Remove `_cache` from `services/market_data.py`. The service still owns aggregation, but caching delegates to the adapter (`YfinanceAdapter._ohlc_cache`), which already has matching TTLs and clear semantics.

Justification: the original service-layer cache predates the adapter's OHLC cache (added in TICKET-022a). Today they hold identical data; one is redundant.

If aggregation cost becomes a concern, cache only the aggregated derivative keyed by `(ticker, period, freq)` — but profile first; aggregation is a single `groupby` over <300 bars and shouldn't need caching.

### Step 3 — Single Refresh hook

`clear_market_data_caches()` becomes the single entry:

```python
def clear_market_data_caches(provider: OhlcDataProvider) -> None:
    clear_live_positions_cache()
    provider.clear_cache()
    st.cache_data.clear()  # nukes any remaining @st.cache_data
```

The top-bar Refresh button calls this and only this.

## Acceptance criteria

- [ ] `get_live_positions_cached` and `clear_live_positions_cache` added to `services/valuation.py`.
- [ ] `_cached_live_positions`, `_cached_concentration_live_positions`, `_live_positions_cached` removed.
- [ ] `services/market_data.py::_cache` removed; OHLC fetches delegate to the adapter cache.
- [ ] `clear_market_data_caches` clears live positions + adapter cache in one call.
- [ ] Refresh button (Top bar) calls only `clear_market_data_caches`.
- [ ] Visiting Tax → Analytics → Sell Simulator without changes in `portfolio.json` triggers exactly **one** live-positions fetch (verifiable by patching `compute_live_positions` in tests).
- [ ] All tests pass; ruff / mypy / lint-imports clean.

### Manual smoke

- Cold start → open Tax tab → KPIs render. Open Analytics → Concentration. Should not re-hit prices (watch logs).
- Click Refresh → next render fetches fresh prices.
- Add a transaction in Manage → next visit to any page reflects the new tx (transactions_signature changes → cache miss).

## Out of scope

- Persistent cache (Redis, on-disk). Module-level dict is sufficient for a single-user Streamlit app.
- Splitting `YfinanceAdapter` into per-protocol classes (separate architectural ticket — needs ADR).
- Removing `@st.cache_resource` on `get_company_provider` (`wiring.py:78`) — different concern; that's session-singleton not data-staleness.

## Notes

- Assumes `transactions_signature` is stable across a session for unchanged data — it is (sorted-ID hash).
- Assumes `clear_market_data_caches` is the only place that nukes data caches. If other call sites exist, they get migrated in this ticket.
- Risk: cross-user data leak if this is ever multi-tenant. Not a concern today (single-user app), but document in `services/valuation.py` that the module-level cache is process-global.
- This ticket is HIGH priority because the cache divergence is a *correctness* risk (a stale OHLC in one layer can disagree with the other after a partial clear), not just an efficiency one.

---

## Update — 2026-06-02 (Cowork review): partially implemented + newly found gaps

`get_live_positions_cached` / `clear_live_positions_cache` already exist in
`services/valuation.py`, but the consolidation was never finished and the review surfaced
two correctness gaps not in the original plan. Fold all of this into one comprehensive pass:

- [ ] **A fourth page-local cache was added after this ticket was written.**
  `app/ui/pages/overview.py:52` defines its *own* `@st.cache_data` `_cached_live_positions`
  (and `_cached_portfolio_summary`) calling `compute_live_positions` directly — bypassing
  `get_live_positions_cached`. This is exactly the "switching Overview → Tax refetches
  everything" slowness. Route Overview through the shared cache like every other page and
  delete the Overview-local wrappers. (The original acceptance list missed this file.)
- [ ] **The cache key misses in-place edits.** `transactions_signature` = `f"{len(txs)}:{max_id}"`
  (`app/ui/cache_keys.py:11`). Editing a transaction's shares/price/date without adding or
  removing a row leaves count and max-id unchanged → the signature doesn't change → caches
  serve stale numbers. Make the signature reflect *content* (a short hash over each tx's
  `id, shares, price, trade_date`) or key on `file_mtime_key(portfolio.json)` (helper already
  in `cache_keys.py:19`). After this, correctness no longer depends on remembering to call `clear()`.
- [ ] **Deduplicate the signature function.** `valuation.py::_tx_sig` (valuation.py:22) is a
  byte-for-byte copy of `cache_keys.transactions_signature`. Collapse to one shared
  implementation; both layers import it.
- [ ] **Every mutation clears every layer.** `app/ui/pages/manage.py` calls
  `st.cache_data.clear()` after edits (manage.py:570/635/778) but not
  `clear_live_positions_cache()` nor the adapter caches → Tax/Analytics can show stale data
  for up to 60s after an edit. Route all mutations and the top-bar Refresh through the single
  `clear_market_data_caches()` so one call clears all three layers.

**Added acceptance criteria:**

- [ ] Overview uses `get_live_positions_cached`; no `_cached_*` live-position wrapper remains in any page or component.
- [ ] Editing an existing transaction (no add/remove) invalidates the live-positions cache (unit test: change a tx in place, assert recompute).
- [ ] Exactly one `transactions_signature` / `_tx_sig` implementation exists.
- [ ] After any `manage.py` mutation, a subsequent page render recomputes (no stale read), verified without a manual Refresh.

**Coordinate with TICKET-PERF-1:** both touch `compute_live_positions`; whichever lands second rebases.
