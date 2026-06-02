# TICKET-C4 — Composite ticker resolver (yfinance + Finnhub fallback)

**Status:** IN_PROGRESS
**Priority:** MEDIUM
**Estimated session length:** 1 hr
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** Claude Code (claude-sonnet-4-6, 2026-06-02)
**Milestone:** Foundation

---

## Problem

Ticker resolution today is yfinance-only, wrapped in `CachedTickerResolver`. The company-data stack (`app/adapters/company_factory.py`) uses a clean `cache(composite(yfinance, finnhub))` pattern: cache layer outside, composite fallback inside. Ticker resolution should mirror it — Finnhub covers European/Japanese tickers that yfinance misses (especially less-liquid German listings and Tokyo IPOs).

## Solution

Add a `CompositeTickerResolver` that mirrors `CompositeCompanyAdapter`:

```
CachedTickerResolver(
    inner=CompositeTickerResolver(
        primary=YfinanceResolverAdapter(),
        fallbacks=[FinnhubTickerResolverAdapter()],
    ),
    cache_path=...,
)
```

### Step 1 — Composite adapter

`app/adapters/ticker_resolver_composite/adapter.py`:

- `resolve(query, limit)`: call primary; if results < limit, call fallbacks and merge by `symbol` (dedup, primary wins on conflict). Return up to `limit`.
- `lookup(symbol)`: call primary; if returns `None`, try fallbacks in order; return first non-`None`. If all return `None`, return `None`.
- Catch each adapter's exceptions individually; one source down does not break the composite.

### Step 2 — Finnhub resolver adapter

`app/adapters/ticker_resolver_finnhub/adapter.py`:

- Implements `TickerResolver`.
- Uses Finnhub's `/search?q=...` endpoint for `resolve` and `/stock/profile2?symbol=...` for `lookup`.
- Reads `FINNHUB_API_KEY` from settings (already wired for company data).
- Skips silently if the key is unset (composite continues with yfinance only).

### Step 3 — Factory pattern (mirror company_factory.py)

`app/adapters/ticker_resolver_factory.py`:

```python
def build_ticker_resolver(cache_path: Path, finnhub_api_key: str | None = None) -> TickerResolver:
    primary = YfinanceResolverAdapter()
    fallbacks: list[TickerResolver] = []
    if finnhub_api_key:
        fallbacks.append(FinnhubTickerResolverAdapter(api_key=finnhub_api_key))
    composite = CompositeTickerResolver(primary=primary, fallbacks=fallbacks)
    return CachedTickerResolver(inner=composite, cache_path=cache_path)
```

`wiring.py::get_ticker_resolver` delegates to this factory.

### Step 4 — Tests

Unit tests for `CompositeTickerResolver`:

- Primary returns 3 of 8 requested → fallback fills to 8.
- Primary returns the requested limit → fallback not called.
- Primary raises → fallback is called.
- Both raise → returns empty list (or `None` for `lookup`); does not raise.
- Dedup: primary returns `SYMBOL=X`; fallback also returns `SYMBOL=X` → only primary's version survives.

Integration test for `FinnhubTickerResolverAdapter`: gated by `FINNHUB_API_KEY` env var; skip if unset.

## Acceptance criteria

- [ ] `CompositeTickerResolver` adapter with the merge/fallback logic described.
- [ ] `FinnhubTickerResolverAdapter` implements `TickerResolver` using Finnhub search + profile endpoints.
- [ ] `build_ticker_resolver` factory composes `cache(composite(yf, finnhub))`.
- [ ] `wiring.py::get_ticker_resolver` uses the factory.
- [ ] Unit tests cover the four composite scenarios listed above.
- [ ] Integration test for Finnhub (env-gated).
- [ ] All tests pass; ruff / mypy / lint-imports clean.

### Manual smoke

- Mappings page → search "rheinmetall" → result includes RHM.DE (yfinance found it).
- Mappings page → search a less-common German ticker that yfinance misses → result appears via Finnhub.
- Set `FINNHUB_API_KEY=""` → app still works; results limited to yfinance.

## Out of scope

- Reordering primary vs fallback (yfinance stays primary).
- Caching at the Finnhub adapter level — the outer `CachedTickerResolver` covers it.
- Currency support beyond what yfinance + Finnhub already cover.

## Notes

- TICKET-C3 (adapter split) must land first — this ticket assumes `YfinanceResolverAdapter` exists as a standalone class.
- The dedup key is `symbol.upper()`. If primary and fallback disagree on currency for the same symbol, primary wins.
- Finnhub free tier rate-limits to 60 calls/min. The outer cache absorbs this; in practice resolver calls are sparse.
