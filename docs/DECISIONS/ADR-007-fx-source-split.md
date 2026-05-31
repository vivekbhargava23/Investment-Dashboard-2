# ADR-007 — FX: ECB for cost basis, yfinance for live valuation

**Status:** Proposed
**Date:** 2026-05-31
**Drafted by:** Vivek + Claude (Cowork session 2026-05-31)
**Supersedes / amends:** None (extends ARCHITECTURE.md invariant #2 and #3)

---

## Context

`ARCHITECTURE.md` invariant #2 says: *"Cost basis EUR is frozen at transaction-date ECB FX rate. Never re-translated."* The architecture file layout names the FX adapter `fx_ecb/`. The actual code on disk is `app/adapters/fx_yfinance/` — yfinance is used for both cost-basis FX (looked up at transaction date) and live-valuation FX (looked up now). The doc and the code disagree.

For a personal dashboard this divergence is tolerable on the live side — yfinance's intraday rate is fine for "what's my portfolio worth today". On the cost-basis side it's a *correctness* drift: German tax law uses the ECB reference rate for foreign-currency translation. A transaction recorded with yfinance's intraday rate can drift from the ECB rate by 10–50 bps, which is small per trade but accumulates across lots and shows up as silent error in the tax summary.

The user (Vivek) confirmed in the 2026-05-31 chat: live rates don't need to be live; "good data" is sufficient. But cost basis should match the rate the tax authority would use.

## Decision

**Split FX into two adapters, one per concern:**

1. **`app/adapters/fx_ecb/`** — implements `HistoricalFxProvider` (cost basis lookups). Source: ECB daily reference rates. Cached on disk at `data/fx_cache/ecb.json` (rates are immutable once published). No network call after first fetch per date.
2. **`app/adapters/fx_yfinance/`** — implements `LiveFxProvider` (live valuation lookups). Existing code stays; just narrowed to the live-rate surface.

The current `FxProvider` Protocol (in `app/ports/fx_feed.py`) is split into `HistoricalFxProvider` and `LiveFxProvider`. Services that need both (e.g. `compute_live_positions`) accept both as parameters.

`wiring.py` wires `get_historical_fx_provider() = EcbFxAdapter(...)` and `get_live_fx_provider() = YfinanceAdapter(...)`. The `# type: ignore` on `get_fx_provider()` goes away.

## Reasoning

1. **Architecture invariant already says so.** This ADR resolves a code-vs-doc divergence, not a new question.
2. **Correctness on cost basis.** ECB reference rates are the rate a German tax form would use. Matching it eliminates a class of silent rounding errors.
3. **No live-rate compromise.** ECB publishes once per business day at 16:00 CET. Using it for live valuation would freeze the dashboard to yesterday's rate after market close; yfinance keeps the "live" feel.
4. **Caching is trivial.** ECB historical rates never change after publication. Disk cache means the network is hit once per (currency, date) tuple. No TTL.
5. **Smaller adapters.** Each adapter does one thing. `YfinanceAdapter`'s FX surface shrinks; further to ADR-009 (splitting that god-class).

## Consequences

- **Pro:** Cost basis matches the tax-authority reference rate.
- **Pro:** `fx_ecb/` matches the architecture document — no more divergence.
- **Pro:** Adapter file count goes from 1 to 2 but each is simpler than the current dual-purpose code.
- **Pro:** The `Port` split makes the dependency at every call site explicit.
- **Con:** ECB endpoint requires a different fetch pattern (XML or CSV download from `https://www.ecb.europa.eu/...`). One-time integration cost.
- **Con:** ECB doesn't publish all pairs directly — only EUR-base. Cross rates (USD/JPY) are derived. Acceptable: the adapter does the derivation; tests cover the calculation.
- **Con:** Backfill: existing cost-basis FX values in `portfolio.json` were stored at yfinance rates. They are not re-translated (invariant #2). New transactions get ECB rates. The two regimes coexist; the change is forward-only.

## Reversal cost

If we ever want to consolidate back: delete `fx_ecb/`, point `get_historical_fx_provider()` at yfinance. ~30 minutes. Low.

## Alternatives considered

- **ECB only for everything.** Rejected — end-of-day rates make live valuation feel stale.
- **Yfinance only for everything.** Rejected — leaves the cost-basis divergence from German tax-authority reference unaddressed.
- **External library (`forex-python`, `currencyapi`).** Rejected — adds a dependency for what is a single ECB CSV fetch.
- **Bundle ECB rates as a static asset.** Rejected — would go stale; the adapter's cache-on-fetch pattern is just as offline-friendly.

## Implementation ticket

TICKET-C1.

## Notes

- The ECB reference rate is published at 16:00 CET each business day. For transactions on weekends/holidays, the convention is to use the most recent prior business day's rate.
- Existing on-disk fx cache (`data/fx_cache/`) is yfinance-shaped; ECB cache is a separate file (`data/fx_cache/ecb.json`). No migration of existing cost-basis values.
