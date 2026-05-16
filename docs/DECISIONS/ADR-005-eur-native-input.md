# ADR-005 — User input is EUR-native; currency and FX are inferred

**Status:** Accepted
**Date:** 2026-05-04
**Drafted by:** Vivek + Claude (chat 2026-05-04)
**Accepted:** 2026-05-04 (TICKET-009-revised, TICKET-008c, TICKET-020 all merged).
**Supersedes / amends:** None (extends ADR-004)

---

## Context

The Manage Portfolio form (TICKET-009 as originally drafted) asks the user to enter:

- Ticker
- Currency (EUR or USD, manual selectbox)
- Price per share in the native currency
- FX rate (EUR per 1 native)
- Shares
- Fees in native currency

This matches the data model exactly. It is also wrong for the user we are building for.

The user (Vivek) operates exclusively through Scalable Capital. Scalable shows him:

- The ticker
- The number of shares
- The total EUR amount debited from his account
- A flat fee (typically €0.99)

Scalable does **not** prominently surface:

- The native-currency price (USD price of NVDA, JPY price of 5631.T)
- The FX rate it used (visible only on the trade-confirmation PDF, sometimes labelled "Devisenkurs")

The dashboard's form, asking for native price and FX rate, demands data the user does not have in front of him. The result, observed in the working app on 2026-05-04:

1. **Silent FX=1.0 default for USD trades.** Auto-fill failed silently; user submitted with FX=1.0; cost basis recorded ~17% too high; portfolio gain dropped by ~€43 on a single 1-share APD purchase that should have been a no-op.
2. **Currency mismatched to ticker.** User entered NVDA with Currency=EUR (the form's default) and price=€100. yfinance has no "NVDA in EUR" listing, so the row went stale (em dashes everywhere) with €100 of phantom cost basis.
3. **Japan Steel Works (5631.T) silently wrong since seed.** The seed CSV recorded JPY price 4,200 with currency=USD as a "v1 approximation". In the live app this produces a fake gain of ~€4,000 because 4,200 JPY (~€26) is being treated as $4,200 (~€3,580) and live-valued against a current JPY price that is ~150× what was recorded.

These are not three independent bugs. They share a root cause: **the form's input model is broker-incompatible.** The form asks for fields the user cannot provide, so the user fills them with whatever default the form offers, and silent corruption follows.

---

## Decision

**The input layer becomes EUR-native. The data model does not change.**

### What the user enters

The Add Transaction and Edit Transaction forms collect six fields:

1. **Ticker** — with autocomplete (see "Ticker resolver" below)
2. **Type** — Buy or Sell
3. **Trade date**
4. **Shares**
5. **Total EUR paid** — the number on the bank statement / Scalable confirmation
6. **Fees in EUR** — typically €0.99

There is no Currency dropdown. There is no native-price field. There is no FX rate field.

### What the dashboard does under the hood

On submit, the dashboard:

1. Resolves the ticker via the new `TickerResolver` port (TICKET-020) to learn `(symbol, name, exchange, native_currency)`.
2. If `native_currency == EUR`: stores `price_native = total_eur_paid / shares`, `fx_rate_eur = 1.0`. No FX work needed.
3. If `native_currency != EUR`: looks up the historical native-currency close price for `trade_date` via the existing `PriceProvider` port. Computes `fx_rate_eur = (total_eur_paid - fees_eur) / (shares × historical_native_price)`. Stores all three.

### What stays the same

- `Transaction` model: unchanged. Still stores `(ticker, type, trade_date, shares, price_native: Money, fees_native, fx_rate_eur, notes)`.
- `Currency` enum: extended to include JPY (and GBP, CHF as natural neighbours) — this is independent of this ADR but required for it to function correctly. See TICKET-008c.
- ADR-004 (cost basis frozen at transaction-date FX): preserved. The FX rate stored is the one derived from the user's actual EUR debit, which is *more accurate* than the ECB rate because it captures Scalable's actual execution rate including spread.
- FIFO engine, valuation service, tax engine: all unchanged. They consume the same `Transaction` shape they always did.

### What the form shows back to the user as confirmation

Before submit, a live "you are recording" panel:

```
Recording: 1 share of APD on 2026-05-04
  Inferred currency: USD
  Historical USD price (close on 2026-05-04): $298.35
  Implied FX rate: 0.8561 EUR/USD
  EUR cost basis: €255.43 + €0.99 fees = €256.42  ← matches your input ✓
```

If the user's "Total EUR paid" deviates from the implied EUR cost (using ECB historical FX) by more than **2%**, the form shows a warning but does not block submit:

> ⚠ Your EUR total implies an FX rate of 0.92, but the ECB rate on 2026-05-04 was 0.86 — a 7% deviation. Did you enter the right amount?

Two percent comfortably accommodates broker spreads (5–25 bps typical) and intraday FX drift, while catching obvious typos (decimal-place errors, swapped digits, wrong-day rates).

---

## Consequences

### Positive

- **The form asks only for data the user has.** Friction drops; silent miscategorisation becomes impossible because there is no Currency selectbox to mis-set.
- **Cost basis reconciles to the cent against the bank statement.** The dashboard captures Scalable's actual EUR debit, including spread, rather than a synthetic ECB-derived approximation. ADR-004's invariant ("cost basis frozen at trade date") strengthens to "cost basis frozen at trade date *and exact to broker reality*".
- **Multi-currency just works.** JPY, GBP, CHF tickers stop being special cases. The form does not care about the native currency; it only cares about EUR-in and ticker-out. The resolver does the rest.
- **The data model is unchanged.** No migration of `Transaction` schema. Tax engine (TICKET-010), valuation (TICKET-006), FIFO (TICKET-002), repository (TICKET-003) all see the same `Transaction` they always saw.
- **Defence in depth.** The 2% deviation warning catches the kind of typo a user would never notice on their own.

### Negative

- **The form needs network at submit time** (to resolve ticker and fetch historical native price). Offline entry is no longer possible.
  - *Mitigation:* if the resolver or historical price fetch fails, the form falls back to asking for native price and FX explicitly — same fields as the original TICKET-009 design — and surfaces a clear "we couldn't reach yfinance, please enter these manually" banner. The fallback path is exercised only when the network is down; in normal use it is invisible.
- **The implied FX rate depends on the historical native price we look up.** If yfinance returns a different end-of-day close than what Scalable used as their reference, the implied FX rate will be slightly off. In practice the deviation is small (<0.5%) and the user's EUR total is the source of truth — the FX rate is just a derived storage artefact.
- **The user loses the ability to enter "I bought NVDA at $198.48" directly.** This is a deliberate trade. If the user really wants to enter a USD-native trade (e.g., a non-Scalable broker, a manually-entered historical trade), the fallback mode handles it.
- **One more port and adapter** (`TickerResolver`) — adds surface area but is needed regardless for autocomplete UX.

### Neutral / observations

- Scalable's Jahressteuerbescheinigung (annual tax statement) reports cost basis in EUR using the broker's own conversion. Storing the EUR-debit-derived cost basis aligns the dashboard with what the German tax authority will see, which is *better* than ECB-derived approximation for tax-comparison purposes.
- This ADR makes the dashboard tightly Scalable-shaped. A user on Trade Republic or IBKR who sees a different breakdown on their confirmations can still use the fallback "native + FX" mode.

---

## Alternatives considered

### Alternative A — keep the original form, just fix the FX auto-fill bug

Patch the silent FX=1.0 default; add a yellow warning on fetch failure; add ticker→currency inference. This is the smallest possible change.

**Rejected because:** the user still does not have the native price in front of him. Fixing FX auto-fill is necessary but not sufficient. The form would still ask for "Price (per share, USD): 298.35" and the user would still have to look that up somewhere — exactly the friction we are trying to remove. This alternative addresses bugs #1 and #2 but not the underlying mismatch.

### Alternative B — pure EUR-only dashboard, drop currency tracking entirely

Strip `Currency` and `fx_rate_eur` from the data model. Every price is EUR. The dashboard fetches the EUR-quoted equivalent from yfinance (via the Frankfurt listing where available).

**Rejected because:**
- Many tickers do not have a clean EUR-quoted equivalent (notably 5631.T, US small-caps).
- Performance attribution becomes impossible — when a position moves, you cannot tell company-vs-FX.
- The German tax authority requires trade-date FX records; deleting them creates a tax-reporting gap.

### Alternative C — accept native-price input, but add live "EUR cost preview"

Keep all original fields; add a live readout: "this records €X cost basis based on what you typed". Never asks the user for EUR total directly.

**Rejected because:** the user still has to dig the native price out of somewhere. The whole problem is that the user's actual data flow starts from EUR, not from native price. Rearranging the form's read-out without changing its inputs does not solve the friction.

### Alternative D — chosen — EUR-native input, full-fidelity data model

The decision above. Combines the input ergonomics of (B) with the data fidelity of the original design.

---

## Implementation tickets

This ADR is implemented by:

- **TICKET-008c** — Currency-correctness audit and migration (extends `Currency` enum to include JPY; recomputes existing `data/portfolio.json` so 5631.T is no longer mislabelled).
- **TICKET-009-revised** — Replaces the in-review TICKET-009 with the EUR-native form, ticker autocomplete, and 2% deviation warning. The original TICKET-009 PR is closed without merging.
- **TICKET-020** — `TickerResolver` port + yfinance adapter. New file: `app/ports/ticker_resolver.py`. Adapter extends `YfinanceAdapter`. Returns `TickerMatch(symbol, name, exchange, currency, recent_price)`.

---

## Open questions parked

- **Should we eventually capture broker-reported FX explicitly** (so the user can paste it from the confirmation PDF when available, overriding the derived value)? Probably yes, as a future "advanced" expander on the form. Out of scope for this ADR.
- **What happens for currencies the resolver returns that are not in the `Currency` enum** (e.g., HKD, AUD)? For now: error out cleanly with a "currency not yet supported, please request via TICKET-XXX" message. Adding a currency is a one-line enum change plus a migration test. Future tickets handle this on demand.

---

## Amendment — TICKET-CSV-7 (2026-05-16)

**Scope of ticker→currency inference narrowed to manual entry only.**

### Problem

ADR-005 was written with the assumption that the only data path was the EUR-native manual form. When TICKET-CSV-7 introduced direct Scalable Capital CSV import, it produced transactions with `source="scalable_csv"` where `price_native.currency=EUR` and `fx_rate_eur=1` — even for US tickers like NVDA, JPY tickers like 5631.T, and CHF/GBP ETPs. These are not mistakes: Scalable always invoices in EUR and the dashboard stores prices at face value.

The original `validate_ticker_currency` model validator — and the Phase 1 pre-check in `JsonTransactionRepository.load_all()` — both called `infer_currency_from_ticker(ticker)` on every row regardless of source. Scalable CSV rows with NVDA+EUR raised `LegacyDataError` at load time, blocking the Manage Portfolio page and the import workbench.

### Decision

**Ticker→currency inference applies to manually-entered transactions only.**

- `Transaction.validate_ticker_currency` now short-circuits when `self.source != "manual"`. Broker rows carry their own settlement currency; the dashboard does not second-guess them.
- `JsonTransactionRepository` Phase 1 pre-check skips rows where `source != "manual"`.
- `migrate_currency.py` skips non-manual rows in `_collect_offenders`.
- `LegacyDataError` message updated to reflect the narrower scope.

### What stays the same

- Manual entry still enforces `ticker→currency` consistency. A user who manually enters NVDA with `currency=EUR` via the form will still see the validation error.
- The `validate_eur_fx_rate` invariant (`fx_rate_eur=1` for EUR transactions) is unchanged and still applies to all sources.
- The `validate_fees_currency` check (fees currency must match price currency) is unchanged.
