# TICKET-CSV-5 — Native-currency support for non-EUR tickers

**Status:** QUEUED
**Priority:** HIGH
**Estimated session length:** 2 hr
**Drafted by:** Vivek + Claude (chat session 2026-05-15)
**Implemented by:** TBD
**Milestone:** Foundation
**Depends on:** TICKET-CSV-1, TICKET-CSV-1-hotfix, TICKET-CSV-4 (workbench is the surface that consumes this)

## Problem

TICKET-CSV-1 decided that all Scalable-CSV-sourced transactions are stored EUR-native with `fx_rate_eur=1.0`. See SESSION_LOG 2026-05-15 entry for CSV-1, decision note:

> Tickers in isin_map.json must therefore be EUR-denominated (e.g., SAP.DE, RHM.DE). USD/JPY tickers would fail Transaction.validate_ticker_currency — the importer catches ValidationError and counts them as invalid_mapping with a clear message.

In practice this means: 12 of the 18 mapped ISINs in the current `isin_map.json` resolve to USD or JPY tickers (NVDA, DELL, NOW, MU, HXSCL, ASX, CIEN, 5631.T, KD, MRVL, AVGO, ANET). Every CSV row for these tickers — 70+ transactions in the reference export — is silently dropped under the `invalid_mapping` counter.

The fix is to detect each ticker's native currency, compute the implied FX rate from the CSV's EUR amounts, and store the transaction in its native currency with the FX rate preserved. Downstream price tracking (yfinance) already expects native-currency prices for US/JP tickers, so this also fixes price-fetch behaviour for these positions (which is currently broken: a USD ticker stored as EUR-native confuses every consumer that compares stored price to live price).

## Goal

Importer (and through it, the CSV-4 workbench) supports non-EUR tickers as a first-class case. A NVDA row from a Scalable EUR-amount CSV produces a `Transaction` with:

- `ticker = "NVDA"`
- `price_native = Money(amount=<native price USD>, currency="USD")`
- `fees_native = Money(amount=<native fee USD>, currency="USD")` (or `None` if blank)
- `fx_rate_eur = <implied rate from CSV row>`

`shares` are unchanged (currency-agnostic).

## Approach

### 1. Native-currency detection from ticker

A pure helper `app/domain/ticker_currency.py` with:

```python
def ticker_native_currency(ticker: str) -> Currency:
    """Map a ticker symbol to its native trading currency."""
```

Rules (in order):
1. Suffix-based — match the dot-suffix against a lookup table:
   - `.DE`, `.F`, `.SG`, `.MU`, `.HM`, `.DU`, `.BE` → EUR (German exchanges)
   - `.PA`, `.AS`, `.BR`, `.LS`, `.MI`, `.MC`, `.HE`, `.VI`, `.IR`, `.LU` → EUR (other eurozone)
   - `.SW`, `.VX` → CHF (Swiss)
   - `.L` → GBP (London — note: London ETFs often quote in GBX pence, handled separately if encountered)
   - `.T`, `.JP` → JPY (Tokyo)
   - `.HK` → HKD
   - `.TO`, `.V` → CAD
   - `.AX` → AUD
2. No suffix (e.g. `NVDA`, `AAPL`, `NOW`) → USD (default for plain US tickers).
3. Override map for known exceptions (`HXSCL` is a Korean GDR but trades USD-denominated; `ASX` is a Taiwanese ADR USD-denominated; etc.) — small dict in the same module, easy to extend.

Returns a `Currency` enum value. Raises `UnknownTickerCurrency` for ambiguous suffixes (e.g. `.U` could be multiple things) — caller decides whether to fall back or fail.

### 2. Implied FX rate computation

For a CSV row with EUR-denominated amounts but a non-EUR ticker:

```python
# CSV gives us amount in EUR; price in CSV is also EUR-quoted per share
# (this is how Scalable presents to a German retail user)
# Native price is what the instrument actually trades at in its home market
# We DON'T have the native price directly. We DO have:
#   - shares (currency-agnostic)
#   - csv_price_eur (price per share in EUR, as Scalable shows it)
#   - csv_amount_eur (total cash EUR)
#   - the trade date
#
# The FX rate at trade time is: rate = csv_price_eur / native_price
# But we don't have native_price either. So:
#
# We look up the FX rate at trade_date from a price source (yfinance EURUSD=X
# or similar) and compute native_price = csv_price_eur / rate.
```

This is the key insight: **Scalable's CSV reports the EUR-translated price, not the native price.** So we need an FX rate source to back-derive native price. The `fx_rate_eur` field on the Transaction model then stores that rate at trade time.

#### FX rate source

A new port `app/ports/fx_rate.py`:

```python
class FxRateProvider(Protocol):
    def get_rate(self, date: date, from_ccy: Currency, to_ccy: Currency) -> Decimal:
        """FX rate at date close. 1 from_ccy = X to_ccy."""
```

Default adapter `app/adapters/fx_yfinance/adapter.py` using yfinance pairs (`EURUSD=X`, `EURJPY=X`, etc.) with disk caching at `data/fx_cache/{from}_{to}.json` (one file per pair, append-only).

Cache TTL: rates older than 7 days never refresh (historical rates don't change). Today's rate refreshes on first request of the day.

#### Fallback when FX is unavailable

If `FxRateProvider` raises or returns no rate (offline, rate-limited, weekend with no Friday close yet):
- The workbench shows the row with status `fx_unavailable` instead of `new`.
- An inline override input lets the user enter the rate manually for this row.
- The CLI prints a warning and skips the row with a clear message: "Row N: FX rate EUR→USD unavailable for 2026-03-15. Skipped. Re-run when online, or set rate manually in the workbench."

### 3. Importer changes

`app/adapters/scalable_csv/importer.py`:

1. Per row, after mapping ISIN→ticker, call `ticker_native_currency(ticker)`.
2. If native currency is EUR: existing path. Build EUR-native Transaction.
3. If native currency ≠ EUR:
   - Call `FxRateProvider.get_rate(trade_date, from_ccy=NATIVE, to_ccy=EUR)`. This gives `1 NATIVE = X EUR`.
   - `native_price = csv_price_eur / rate_native_per_eur` (where `rate_native_per_eur = 1 / rate`).
   - Equivalently: `native_price = csv_price_eur * (1 / rate)`. Use `Decimal`, never float.
   - `native_fee = csv_fee_eur * (1 / rate)` (preserving fee currency match).
   - `fx_rate_eur = 1 / rate` (i.e. how many EUR per 1 unit of native — consistent with existing `Money` / `fx_rate_eur` convention; double-check against `Transaction.validate_ticker_currency` to confirm).
4. Construct `Transaction` with native-currency `Money` objects. Pydantic validation now passes (no `ValidationError` to catch).
5. Sanity check: `abs(shares × native_price × fx_rate_eur - csv_amount_eur) < 0.02` (slightly looser tolerance than EUR-native to absorb FX rounding).

### 4. Workbench integration (CSV-4 hook)

CSV-4 defines a `needs_currency_support` row status for non-EUR tickers. After this ticket lands:

- Rows with non-EUR tickers and successful FX lookup → status changes from `needs_currency_support` to `new` (importable normally).
- Rows with non-EUR tickers but FX lookup failed → status `fx_unavailable`, with an inline manual-rate input.
- The classification logic in `app/services/csv_import_planner.py` gets one new branch; the action control gets one new variant.

## Non-goals

- Live FX for active price refresh on existing positions. Out of scope. This ticket is about *import-time* FX only. Live FX for the Live Overview is handled elsewhere (and the existing code path probably needs review once positions exist in non-EUR currencies — flag as follow-up).
- Multi-leg FX (e.g. JPY ticker, USD-denominated CSV). Not applicable — Scalable always denominates in EUR for German users.
- User-configurable currency override per ticker. The auto-detection plus the per-row manual rate fallback is sufficient for v1.
- Historical FX correction. If yfinance later updates a historical rate, we don't re-derive prices. The stored value at import time wins.

## Acceptance criteria

- [ ] `ticker_native_currency("NVDA")` returns USD; `("VUAA.DE")` returns EUR; `("5631.T")` returns JPY; `("HXSCL")` returns USD (override map).
- [ ] `FxRateProvider` adapter fetches and caches EUR→USD, EUR→JPY rates from yfinance.
- [ ] Cache file `data/fx_cache/EUR_USD.json` is created on first call, reused on second call.
- [ ] Importing a NVDA row (mapped ISIN `US67066G1040` → `NVDA`) produces a Transaction with `price_native.currency == "USD"`, `fx_rate_eur != 1.0`, and `shares × price_native.amount × fx_rate_eur ≈ csv_amount_eur` (within €0.02).
- [ ] Importing a 5631.T row produces a JPY-native Transaction.
- [ ] CSV row when FX provider raises → row classified as `fx_unavailable` in the workbench (when integrated with CSV-4) or skipped with clear warning in CLI.
- [ ] Workbench's manual-rate override input: setting rate, then Apply → transaction uses that rate, FX cache is NOT updated (user override stays per-row).
- [ ] Existing EUR-native imports continue to work unchanged (regression).
- [ ] After CSV-4 + CSV-5 ship, re-importing `scalable_raw.csv` via the workbench shows the previously-`needs_currency_support` rows as `new`, importable.
- [ ] All previously-passing tests still pass.
- [ ] New tests added for: ticker currency detection (8 cases minimum), FX rate provider (cache hit/miss, offline fallback), importer end-to-end with USD ticker, importer end-to-end with JPY ticker.
- [ ] Lints pass.

## Files likely touched

### New
- `app/domain/ticker_currency.py` — detection helper + override map + `UnknownTickerCurrency` exception
- `app/ports/fx_rate.py` — `FxRateProvider` Protocol
- `app/adapters/fx_yfinance/__init__.py`, `adapter.py` — yfinance FX adapter with disk cache
- `tests/unit/domain/test_ticker_currency.py`
- `tests/unit/adapters/test_fx_yfinance.py`
- `tests/integration/test_fx_yfinance_live.py` — integration-gated

### Modified
- `app/adapters/scalable_csv/importer.py` — branch on native currency, FX lookup, construct native-currency Money
- `app/services/csv_import_planner.py` (from CSV-4) — new branch for `fx_unavailable`, remove `needs_currency_support` as a permanent state (it becomes transient: needs lookup → either `new` or `fx_unavailable`)
- `app/ui/pages/import_workbench.py` (from CSV-4) — manual-rate input control for `fx_unavailable` rows
- `app/config.py` — `fx_cache_dir` setting
- `app/ui/wiring.py` — `get_fx_rate_provider()`
- `tests/unit/test_scalable_csv_importer.py` — additional cases for USD and JPY rows

## Test cases

1. **Ticker detection** — 8+ tickers covering each suffix family + 2 override-map entries (HXSCL→USD, ASX→USD).
2. **FX cache** — first call writes file, second call reads from cache, neither calls yfinance more than once.
3. **FX offline** — provider raises; importer returns row with `fx_unavailable` status (when integrated) or CLI prints warning and skips.
4. **NVDA buy import** — CSV row `shares=4, csv_price_eur=76.51, csv_amount_eur=-306.04`, FX rate EUR/USD on trade date = X → `price_native = 76.51/X USD`, sanity check passes.
5. **JPY buy import** — same structure for 5631.T.
6. **Manual rate override** — workbench row with `fx_unavailable`, user enters rate, Apply uses that rate, FX cache untouched.
7. **Regression — EUR import** — RHM.DE row imports identically to pre-CSV-5 behavior.
8. **Mixed import** — single CSV with EUR + USD + JPY rows applies cleanly.

## Notes

### Why this is HIGH priority and separate from CSV-4

CSV-4 ships the visibility win. The day it merges, the user sees all the missing rows as `needs_currency_support`, understands why, and waits for CSV-5. CSV-5 unlocks the actual import. Splitting them means CSV-4 can ship without being blocked by FX-provider work, and CSV-5 has a clear surface (the workbench) to plug into. Without the split, CSV-4 alone would still leave the portfolio incomplete, and bundling them doubles the ticket size to ~6 hours.

### The FX-direction trap

Easy to get backwards: `EUR/USD` on yfinance means "how many USD per 1 EUR" (typically ~1.05-1.15). The `fx_rate_eur` field convention in this codebase is "how many EUR per 1 unit of native currency" (typically ~0.9 for USD, ~0.006 for JPY). The conversion: `fx_rate_eur = 1 / yfinance_pair_rate`. Test cases should pin this down with concrete numeric examples to prevent regression.

### Why we don't use the CSV's `tax` column for FX hints

Tempting idea: Scalable sometimes shows withholding tax in the CSV which is itself a currency conversion. But the tax column is unreliable (only present on dividends, often EUR-only) and using it would couple the importer to dividend-row logic that belongs in TICKET-CSV-3. Stick with the dedicated FX provider.

### Anti-approximation

The implied-rate math is the kind of thing that's easy to plausibly-but-wrongly approximate. Use `Decimal` throughout, never `float`. Use the `Money` class's existing arithmetic where possible — don't recompute from raw decimals if `Money * Decimal` is available. Tests should assert exact equality to a few decimal places on the resulting `price_native.amount`, not just "approximately correct."
