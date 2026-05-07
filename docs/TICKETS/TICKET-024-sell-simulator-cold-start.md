# TICKET-024 — Sell simulator cold-start performance (repeated slow renders after restart)

**Status:** IN_PROGRESS
**Priority:** P1
**Estimated session length:** 1 – 1.5 hr
**Drafted by:** Claude Code (bug investigation 2026-05-07)
**Implemented by:** _pending_
**Found by:** Vivek — sell simulator was "opening instantly after first load" post-TICKET-012, but now takes several seconds again after each Streamlit restart.

---

## Problem

The sell simulator page (`app/ui/components/sell_simulator.py`) has two independent slow-on-restart paths:

### Slow path 1 — `_build_ticker_labels` re-runs all resolver calls after restart

```python
@st.cache_data(ttl=3600, show_spinner=False)
def _build_ticker_labels(tickers: tuple[str, ...]) -> dict[str, str]:
    resolver = get_ticker_resolver()
    for t in tickers:
        matches = resolver.resolve(t, limit=5)   # yf.Search: ~150ms
        # _build_match called per result: yf.Ticker(symbol).fast_info × 5: ~200ms each
```

The `@st.cache_data` cache lives in-process. After a Streamlit restart, this cache is cleared and the function re-runs: for N portfolio tickers with up to 5 search results each, that's up to N × 6 yfinance network calls (~1.2 s per ticker at 200ms each). For a 5-ticker portfolio: ~6 s cold, instant warm.

TICKET-021 (disk-backed `CachedTickerResolver`) partially fixes this: the resolver calls will hit the disk cache on restart. But `_build_match` STILL calls `yf.Ticker(symbol).fast_info` for each search result to populate `recent_price`, which is a network call that bypasses the disk cache (the disk cache stores full `TickerMatch` objects, and `recent_price` is included — so if the disk cache is warm, `_build_match` is not called at all). Once TICKET-021 is merged and the disk cache has been seeded by at least one warm run, this path is fast. **This part may self-resolve once TICKET-021 merges and the user runs once.**

### Slow path 2 — `compute_live_positions` on every render fetches prices

```python
def render_sell_simulator(default_ticker: str | None = None) -> None:
    transactions = get_repository().load_all()
    live_positions = compute_live_positions(transactions, get_price_provider(), get_fx_provider())
```

This is called on **every render** of the sell simulator page, including every radio-button change and form rerun. `compute_live_positions` calls `get_current_price(ticker)` for each open position. The YfinanceAdapter has a 60-second in-memory TTL. After restart (or after 60 seconds), all prices are re-fetched: N × ~400ms network calls.

If the user opened Live Overview before the sell simulator, prices are already warm (same in-memory instance). If not, or after >60s, the first sell-simulator render is slow. **This path is not fixed by TICKET-021** (disk cache only covers ticker metadata, not live prices).

---

## Acceptance criteria

### Fix 1 — Cache `live_positions` at the Streamlit layer in the sell simulator

Wrap `compute_live_positions` in a `@st.cache_data(ttl=60, show_spinner=False)` function local to `sell_simulator.py`. This ensures:
- First call per session: slow (fetches prices). After the first visit, results persist across page navigations.
- After 60 s TTL: refreshes prices on next render. This is the same staleness window as the YfinanceAdapter's in-memory cache.
- After Streamlit restart: same as current first-call (cold), but then fast for the remainder of the session.

Implementation:
```python
@st.cache_data(ttl=60, show_spinner=False)
def _live_positions_cached(
    tx_ids: tuple[str, ...],  # used as cache key
) -> dict[str, LivePosition]:
    transactions = get_repository().load_all()
    return compute_live_positions(transactions, get_price_provider(), get_fx_provider())
```

Call with `tx_ids = tuple(tx.id for tx in transactions)` so that adding a new transaction invalidates the cache. (The repository call is cheap — it's the price fetch that's expensive.)

**Concern:** `LivePosition` contains `Money` and `Decimal` — Pydantic frozen models. Streamlit's pickle-based cache should handle these. If serialization fails, fall back to the current uncached call.

### Fix 2 — Don't fetch `recent_price` in `_build_match` when the result is just for label lookup

`_build_ticker_labels` only needs the ticker name — it doesn't use `recent_price`. But `_build_match` always calls `yf.Ticker(symbol).fast_info` (one network call per search result) to populate `recent_price`. For label-building, this is wasteful.

Two options:
- **Option A (simpler):** Add an optional `fetch_price: bool = True` parameter to `_build_match`. When `fetch_price=False`, skip the `fast_info` call and set `recent_price=None`. Change `_build_ticker_labels` to call a lightweight variant.
- **Option B (TICKET-021-safe):** Since TICKET-021 caches full `TickerMatch` objects to disk (including `recent_price`), once the disk cache is warm the `fast_info` call never runs again. Option B means "wait for TICKET-021 to warm the cache" — acceptable but slower recovery after fresh installs.

Implement Option A. The disk cache in TICKET-021 can later cache the rich objects; label-building should always be lightweight.

### Tests

- `tests/unit/ui/test_sell_simulator_component.py` — verify `_live_positions_cached` is invoked with the right cache key and that changing `tx_ids` causes a new call to `compute_live_positions`.
- Verify the existing sell simulator tests still pass (no regression from the cache wrapper).

### Lints / quality

- `pytest && ruff check . && mypy app/ && lint-imports` — all green.

---

## Files likely touched

```
app/ui/components/sell_simulator.py     ← add _live_positions_cached; remove direct compute call
app/adapters/yfinance_feed/yfinance_adapter.py  ← add fetch_price param to _build_match (Option A)
tests/unit/ui/test_sell_simulator_component.py  ← update / add tests
```

## Out of scope

- Persistent caching of live prices across Streamlit restarts (that would require TICKET-013 / daily NAV cache, which is deferred).
- Any changes to the Live Overview page's price caching (handled separately).
- Changing the 60-second price TTL in the YfinanceAdapter.

## Dependency

TICKET-021 should merge first. Once the disk cache is warm, Slow Path 1 resolves itself. This ticket fixes Slow Path 2 (price fetching) which TICKET-021 does not address.
