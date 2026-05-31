# TICKET-C1 — Add ECB FX adapter for cost-basis lookups

**Status:** QUEUED
**Priority:** HIGH
**Estimated session length:** 2 hr
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Milestone:** Foundation

---

## Problem

Per ADR-007: cost-basis FX should use the ECB daily reference rate (matches `ARCHITECTURE.md` invariant #2 and German tax practice); live valuation continues with yfinance. Today both use yfinance.

## Solution

### Step 1 — Split the port

`app/ports/fx_feed.py`:

```python
class HistoricalFxProvider(Protocol):
    def get_historical_rate(self, base: Currency, quote: Currency, on_date: date) -> Decimal: ...

class LiveFxProvider(Protocol):
    def get_current_rate(self, base: Currency, quote: Currency) -> Decimal: ...

# Back-compat shim: keep FxProvider as a union for one release
FxProvider = HistoricalFxProvider | LiveFxProvider
```

### Step 2 — New adapter

`app/adapters/fx_ecb/adapter.py`:

- Implements `HistoricalFxProvider`.
- Fetches from `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip` (full history CSV, refreshed daily) or `eurofxref-daily.xml` (just today). Use the CSV — it's one fetch per cache miss for the full history.
- Caches on disk at `data/fx_cache/ecb.json`. Schema: `{"USD": {"2025-12-31": "1.0518", ...}, "JPY": {...}}`.
- Pair derivation: ECB publishes EUR-base only. Cross rates computed as `rate(base, quote) = rate(EUR, quote) / rate(EUR, base)`.
- Weekend/holiday handling: ECB doesn't publish on weekends or German holidays. The adapter walks back to the most recent prior business day.
- Test fixtures: include a sample `eurofxref-hist.zip` snippet so integration tests don't hit the network.

### Step 3 — Wiring

`app/ui/wiring.py`:

```python
@lru_cache(maxsize=1)
def get_historical_fx_provider() -> HistoricalFxProvider:
    return EcbFxAdapter(cache_path=Path("data/fx_cache/ecb.json"))

@lru_cache(maxsize=1)
def get_live_fx_provider() -> LiveFxProvider:
    return get_price_provider()  # YfinanceAdapter's live-rate path
```

`get_fx_provider()` becomes a deprecation shim that returns `get_live_fx_provider()` (most current callers actually want live).

### Step 4 — Update callers

Grep `get_fx_provider` and `FxProvider`. For each call site:
- Cost-basis path (FIFO recompute, transaction recording): use `get_historical_fx_provider`.
- Live valuation path (`compute_live_positions`, portfolio summary): use `get_live_fx_provider`.

Service signatures: `compute_live_positions(transactions, price_provider, *, live_fx, historical_fx)` — accept both explicitly.

### Step 5 — Adapter test

`tests/integration/test_fx_ecb.py`:

- Cold cache: fetches CSV, populates `ecb.json`.
- Warm cache: no network call.
- Weekend lookup: returns Friday's rate.
- Cross rate: USD → JPY via EUR-cross matches the ECB-published derived rate within a tolerance.

## Acceptance criteria

- [ ] `HistoricalFxProvider` and `LiveFxProvider` protocols in `app/ports/fx_feed.py`.
- [ ] `app/adapters/fx_ecb/adapter.py` with disk cache, cross-rate derivation, weekend walk-back.
- [ ] `wiring.py` exposes `get_historical_fx_provider` and `get_live_fx_provider`. `get_fx_provider` is a back-compat shim.
- [ ] All cost-basis call sites use `get_historical_fx_provider`. All live-valuation sites use `get_live_fx_provider`.
- [ ] Tests cover ECB CSV parsing, cross-rate derivation, weekend walk-back, and cache hit/miss.
- [ ] No `# type: ignore` for FX in `wiring.py`.
- [ ] All tests pass; ruff / mypy / lint-imports clean.

### Manual smoke

- Add a transaction for an NVDA buy on a weekend date — recorded cost basis uses Friday's ECB rate.
- Live Overview still shows current portfolio value (yfinance live rate path).
- Delete `data/fx_cache/ecb.json`, restart, add a transaction — cache repopulates from one ECB fetch.

## Out of scope

- Re-translating existing cost basis values stored at old yfinance rates. The change is forward-only (per ADR-007).
- Currency pairs beyond EUR/USD/JPY (current Currency enum is the same scope).
- ECB intraday rates — not published; the daily reference rate is the only ECB rate.

## Notes

- ECB CSV format: `Date,USD,JPY,BGN,CYP,...` — first column is date, rest are EUR-base rates. Validate parsing on the header row.
- Assumes `pandas` is available for CSV parsing (it is — yfinance depends on it). Don't add a new dependency.
- Cache file format: pretty-printed JSON for easy diffing.
