# ADR-009 — Split YfinanceAdapter into four per-protocol adapters

**Status:** Proposed
**Date:** 2026-05-31
**Drafted by:** Vivek + Claude (Cowork session 2026-05-31)
**Supersedes / amends:** Extends ARCHITECTURE.md "Adapters layer" rules

---

## Context

`app/adapters/yfinance_feed/yfinance_adapter.py` is 444 lines and implements four ports in one class: `PriceProvider`, `FxProvider`, `TickerResolver`, `OhlcDataProvider`. Symptoms:

- `app/ui/wiring.py:52` needs a `# type: ignore[return-value]` because `get_fx_provider()` returns the same singleton as `get_price_provider()`.
- The class holds four independent caches (`_current_cache`, `_historical_cache`, `_resolver_cache`, `_ohlc_cache`) with overlapping TTL logic — adding a fifth concern would inherit all of them.
- Swapping any one protocol's implementation (e.g. ECB FX per ADR-007, or Finnhub ticker resolution) means working around the god-class.
- The architecture doc says *"Each adapter implements exactly one port"* — the YfinanceAdapter is the only violation.

## Decision

**Split `YfinanceAdapter` into four per-protocol adapters in `app/adapters/yfinance_*/`:**

```
app/adapters/
├── yfinance_price/       PriceProvider           (current_price, historical_close)
├── yfinance_ohlc/        OhlcDataProvider        (get_ohlc_history)
├── yfinance_resolver/    TickerResolver          (resolve, lookup)
└── (fx_yfinance/         LiveFxProvider          — survives ADR-007 split)
```

A thin shared helper module `app/adapters/_yfinance_client.py` holds:
- `yf` import isolation (so each adapter doesn't restate it)
- Common error mapping (yfinance exception → port-domain exception)
- Common currency inference (`infer_currency_from_ticker` — already in `app/domain/tickers.py`, just reused)

Caching stays *inside* each adapter — they're not shared because invalidation semantics differ (intraday vs daily TTL).

`wiring.py` instantiates four adapters separately; no more shared singleton across protocols.

## Reasoning

1. **The architecture rule already says so.** "Each adapter implements exactly one port." The YfinanceAdapter is the singular violation.
2. **Type safety.** The `# type: ignore` in wiring disappears. Each `get_*_provider()` returns its declared port type.
3. **Per-protocol substitution becomes trivial.** ADR-007 (ECB FX) and a future composite ticker resolver (mirror of the company-data stack) both depend on the split being done.
4. **Caches stop interfering.** Today `clear_cache()` on the YfinanceAdapter nukes price, historical, resolver, and OHLC caches in one call. Splitting lets the Refresh button be selective — refresh prices without invalidating ticker metadata.
5. **Test isolation.** Each adapter gets its own integration test file in `tests/integration/`. Today they share one.

## Consequences

- **Pro:** Cleaner wiring; no `# type: ignore`.
- **Pro:** Architecture rule restored.
- **Pro:** ADR-007 (ECB FX) and a future composite resolver are easier.
- **Pro:** Each adapter is ~100 lines; cognitively cheap.
- **Con:** Four adapters instead of one. More files, but each is single-purpose.
- **Con:** Shared `_yfinance_client.py` introduces a small DRY layer; risk of over-extraction. Keep it tiny — exception mapping only.
- **Con:** Existing tests touch the god-class. Migration: each test file moves to the adapter it actually tests; no behaviour changes.

## Reversal cost

Re-merging the four adapters back into one is mechanical: re-introduce the god-class, point all four wiring functions at it. ~1 hr. Low.

## Alternatives considered

- **Leave the god-class, fix internal seams.** Rejected — keeps the architecture-rule violation and the type-ignore.
- **Inheritance / mixins.** Rejected — Python has no compelling case for it here; composition via a shared helper is cleaner and more Pythonic.
- **Skip the shared helper, duplicate the import + currency inference.** Rejected — actual duplication, not the right answer to "stay simple".

## Implementation ticket

TICKET-C3.
