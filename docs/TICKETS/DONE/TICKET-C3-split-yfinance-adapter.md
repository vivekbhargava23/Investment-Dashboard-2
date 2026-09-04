# TICKET-C3 — Split YfinanceAdapter into four per-protocol adapters

**Status:** IN_PROGRESS
**Priority:** MEDIUM
**Estimated session length:** 2 hr
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Milestone:** Foundation

---

## Problem

Per ADR-009: `app/adapters/yfinance_feed/yfinance_adapter.py` is a 444-line god-class implementing four ports. Violates `ARCHITECTURE.md`'s "one adapter per port" rule; forces `# type: ignore` in `wiring.py`; blocks per-protocol substitution.

## Solution

Split into:

```
app/adapters/
├── _yfinance_client.py            shared: yf import, exception mapping, currency inference reuse
├── yfinance_price/adapter.py      PriceProvider
├── yfinance_ohlc/adapter.py       OhlcDataProvider
├── yfinance_resolver/adapter.py   TickerResolver
└── fx_yfinance/adapter.py         LiveFxProvider (per ADR-007 — this one mostly survives)
```

### Step 1 — Shared client helper

`app/adapters/_yfinance_client.py`:

- `import yfinance as yf` (single source).
- `map_yf_exception(e: Exception, *, port_error_class) -> Exception` — wraps yfinance errors in the right port-domain exception.
- Nothing else. Keep tiny.

### Step 2 — Per-protocol adapters

Move methods verbatim from `YfinanceAdapter` into the matching new class:

- `YfinancePriceAdapter` — `get_current_price`, `get_historical_close`, owns `_current_cache` + `_historical_cache`.
- `YfinanceOhlcAdapter` — `get_ohlc_history`, owns `_ohlc_cache`.
- `YfinanceResolverAdapter` — `resolve`, `lookup`, owns `_resolver_cache`.
- `YfinanceLiveFxAdapter` — `get_current_rate`, owns its slice of the current cache. (The historical FX surface goes to `EcbFxAdapter` per ADR-007 / TICKET-C1.)

Each adapter exposes its own `clear_cache()`.

### Step 3 — Wire one-port-per-adapter

`wiring.py`:

```python
@lru_cache(maxsize=1)
def get_price_provider() -> PriceProvider: return YfinancePriceAdapter()

@lru_cache(maxsize=1)
def get_ohlc_data_provider() -> OhlcDataProvider: return YfinanceOhlcAdapter()

@lru_cache(maxsize=1)
def get_ticker_resolver() -> TickerResolver:
    return CachedTickerResolver(inner=YfinanceResolverAdapter(), cache_path=...)

@lru_cache(maxsize=1)
def get_live_fx_provider() -> LiveFxProvider: return YfinanceLiveFxAdapter()
```

The `# type: ignore[return-value]` on `get_fx_provider` is gone.

### Step 4 — Refresh button

`clear_market_data_caches(...)` (per TICKET-R5) calls each adapter's `clear_cache()`. Selective refresh becomes possible later.

### Step 5 — Tests

Move integration tests:
- `tests/integration/test_yfinance_price.py`
- `tests/integration/test_yfinance_ohlc.py`
- `tests/integration/test_yfinance_resolver.py`
- `tests/integration/test_yfinance_live_fx.py`

The current `test_yfinance_adapter.py` splits by method into the four new files.

### Step 6 — Delete the god class

After all callers point at the new adapters, delete `app/adapters/yfinance_feed/yfinance_adapter.py`. `__init__.py` re-exports for back-compat for one release (then removed).

## Acceptance criteria

- [ ] Four per-protocol adapter files created.
- [ ] `_yfinance_client.py` holds only shared import + exception mapping.
- [ ] `wiring.py` has no `# type: ignore` for adapter wiring.
- [ ] Each adapter has its own integration test file.
- [ ] Old `YfinanceAdapter` deleted; back-compat re-export documented as deprecated.
- [ ] `import-linter` rule passes — adapters depend only on ports + domain.
- [ ] All tests pass; ruff / mypy / lint-imports clean.

### Manual smoke

- Live Overview, Research, Analytics, Sell Simulator all work as before.
- Refresh button still clears caches across all four protocols.

## Out of scope

- The ECB FX adapter — TICKET-C1.
- A composite ticker resolver (yfinance + Finnhub) — TICKET-C4.
- Refactoring caches into a shared base class — keep them per-adapter for now.

## Notes

- TICKET-R5 (cache consolidation) and this ticket touch the same code; sequence matters. Implement R5 first (single live-positions cache) then C3 (split adapters).
- Assumes `infer_currency_from_ticker` stays in `app/domain/tickers.py` (it does — already domain-pure).
