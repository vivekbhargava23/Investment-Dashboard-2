# TICKET-009-revised — Manage Portfolio (EUR-native input + ticker resolver)

**Status:** DRAFT
**Priority:** P1
**Estimated session length:** 3 – 3.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-04)
**Implemented by:** _pending_
**Depends on:** TICKETs 001 (domain), 002 (FIFO), 003 (repo), 004-005 (yfinance), 006 (valuation), 007 (UI shell), 008 (Live Overview), **TICKET-008c (currency correctness)**, **TICKET-020 (TickerResolver port)**
**Supersedes:** TICKET-009 (closed without merging — original form's input model was broker-incompatible; see ADR-005)

> **After this ticket merges, the daily-use loop is closed.** The user opens Scalable, sees a fill, types four numbers into the dashboard form, and the dashboard records a perfectly reconciled transaction with correct currency, FX, and EUR cost basis — without ever asking the user about FX or native price.

---

## Problem

The original TICKET-009 implemented a CRUD form whose inputs (Ticker, Currency, Native price, FX rate, Shares, Fees) match the data model exactly. In bench-testing on 2026-05-04, the form produced silent corruption in three independent ways:

1. FX field defaulted to 1.0 when auto-fill failed, with no warning. APD purchase recorded €298 cost basis instead of €256.
2. Currency dropdown defaulted to EUR. NVDA was recorded as a EUR-priced security, going stale immediately on Live Overview.
3. The form's information demand exceeds what Scalable's confirmations make available. Users do not have the native USD price in front of them; they have the EUR debit.

ADR-005 captures the architectural response: **input becomes EUR-native; currency and FX are derived from broker reality.** This ticket implements that.

The original TICKET-009 PR is closed without merging. Most of its scaffolding (session_state edit/delete flow, two-form pattern, FIFO sell validation) is reused unchanged — those parts were correct. Only the input fields and submit pipeline change.

---

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-04 (codified in ADR-005):

1. **Input is EUR-native.** Six fields: ticker, type, date, shares, total EUR paid, fees in EUR. No Currency dropdown. No native-price field. No FX rate field.

2. **Ticker autocomplete is mandatory.** As the user types, a dropdown surfaces matches with `(symbol, name, exchange, currency, recent_price)` from the `TickerResolver` port (TICKET-020). The user clicks one. The form now knows the security with certainty. Free-typing without selecting a match is allowed *only* via an explicit "use as-typed" affordance (for fallback offline use); the default flow requires a resolved match.

3. **Submit is a small pipeline, not a single write.** On submit:
   1. Resolve ticker (or use already-resolved value from autocomplete).
   2. Determine native currency from `infer_currency_from_ticker` (which agrees with the resolver — TICKET-008c established this as the single source of truth).
   3. If EUR-native: trivial — `price_native = (eur_total - fees_eur) / shares`, `fx_rate_eur = 1.0`.
   4. If non-EUR: fetch historical native-currency close for `trade_date`. Back-compute `fx_rate_eur = (eur_total - fees_eur) / (shares × historical_native_close)`.
   5. Construct the `Transaction`. The TICKET-008c validator catches any ticker↔currency mismatch automatically.
   6. Persist.

4. **Sanity check before submit.** A live "Recording…" panel shows the user what the form is about to write, with the implied FX rate cross-checked against the ECB rate for that date. **2% deviation tolerance**: warn if exceeded, do not block. (Rationale: broker spreads are 5–25 bps; 2% catches typos without false-alarming on legitimate spread.)

5. **Fallback to manual entry on resolver/price-fetch failure.** If the resolver or historical price is unavailable (offline, ticker not in yfinance, weekend gap that historical lookup couldn't bridge), the form transparently switches to a fallback mode that *does* ask for native price + FX. A clear banner explains why. The fallback mode is the original TICKET-009 form, kept as a code path for this purpose.

6. **Reuse from original TICKET-009:** the two-form pattern (Add and Edit are separate `st.form` containers), session_state edit/delete flow, inline delete confirmation, FIFO pre-trade validation, and per-row buttons in the All Transactions table. Those parts of the original implementation are not regressed by this ticket.

7. **Cache invalidation rule unchanged from original TICKET-009:** every successful CRUD clears `st.cache_data`; ADD also clears adapter caches (new ticker may need a fresh price); EDIT and DELETE on existing tickers skip the adapter clear.

---

## Acceptance criteria

### Top-level: replace `app/ui/pages/manage.py`

The page renders three sections, top-down:

1. **Add Transaction** form (always visible).
2. **All Transactions** table (per-row Edit and Delete buttons).
3. **Edit Transaction** form (visible only when `st.session_state.editing_tx_id` is set).

### Section 1 — Add Transaction form

#### Field-by-field specification

- [ ] **Ticker — autocomplete combobox**

  Implemented as a Streamlit `st.text_input` paired with a `st.selectbox` that updates as the user types. (Streamlit does not have a native combobox with live-search; the pattern is a text input that triggers a resolver call on each rerun, populating a selectbox with the top 5 matches.)

  Behaviour:
  - As the user types ≥2 characters, the form calls `ticker_resolver.resolve(query)` (TICKET-020).
  - Results render as a dropdown: `"NVDA · NVIDIA Corporation · NASDAQ · USD · ~$198.48"`.
  - Selecting a result fixes the form's known ticker and stores `(symbol, name, exchange, currency)` in `st.session_state.add_form_resolved`.
  - The text input value below the dropdown shows the selected symbol (e.g. `NVDA`).
  - A "Use as-typed (no validation)" affordance appears below the dropdown when no result is selected. Clicking it sets `st.session_state.add_form_resolved = None` and trusts the typed string. This is the offline-fallback escape hatch.

- [ ] **Type** — `st.radio("Type", ["Buy", "Sell"], horizontal=True)`. Default: `"Buy"`. Unchanged from original TICKET-009.

- [ ] **Trade date** — `st.date_input("Trade date")`. Default: today. Max: today. Min: `date(2000, 1, 1)`. Unchanged from original TICKET-009.

- [ ] **Shares** — `st.number_input("Shares", min_value=0.0001, step=0.0001, format="%.4f")`. Default: `1.0`. Unchanged from original TICKET-009.

- [ ] **Total EUR paid** — `st.number_input("Total EUR paid (from your broker confirmation)", min_value=0.01, step=0.01, format="%.2f")`. Default: `0.00` (forces user to fill). Help tooltip: "The total euro amount debited from your account, including any FX conversion the broker did. Read this off your Scalable confirmation or bank statement."

- [ ] **Fees (EUR)** — `st.number_input("Fees (EUR, optional)", min_value=0.0, step=0.01, format="%.2f")`. Default: `0.99` (Scalable's standard fee — a sensible default; user can override). Help tooltip: "Broker commission. Scalable typically charges €0.99 per trade."

- [ ] **Notes** — `st.text_input("Notes (optional)")`. Default: empty. Unchanged from original TICKET-009.

#### "Recording" preview panel

- [ ] Renders below the fields, above the Submit button. Updates live as the user types (Streamlit reruns on each input change).
- [ ] Three states:

  **State A — ticker resolved, EUR-native security:**

  ```
  Recording: 1 share of RHM.DE on 2026-05-04
    Native currency: EUR (Frankfurt)
    Per-share cost: €1,387.21
    EUR cost basis: €1,387.21 + €0.99 fees = €1,388.20  ✓ matches your input
  ```

  **State B — ticker resolved, non-EUR security:**

  ```
  Recording: 1 share of APD on 2026-05-04
    Native currency: USD (NYSE)
    Historical USD close on 2026-05-04: $298.35  (from yfinance)
    ECB EUR/USD rate on 2026-05-04: 0.8552
    Implied FX rate (from your EUR total): 0.8561
    Deviation from ECB: 0.1%  ✓ within tolerance
    EUR cost basis: €255.43 + €0.99 fees = €256.42  ✓ matches your input
  ```

  **State C — deviation warning:**

  Same layout as State B but with a yellow banner:

  > ⚠ Your EUR total (€280.00) implies an FX rate of 0.94, but the ECB rate on this date was 0.8552 — a 9.9% deviation. Did you enter the right amount, or pick the right trade date? You can submit anyway if this is correct (e.g., if your broker quoted a very different rate).

- [ ] When the resolver / historical price fetch fails, the panel shows the fallback banner (see "Fallback mode" below) and the form switches to manual-entry fields.

#### Submit handler

- [ ] On Submit click:

  1. Validate inputs (shares > 0, EUR total > 0, ticker non-empty).
  2. If `add_form_resolved` is `None` and "use as-typed" was not clicked → show error "Please select a ticker from the dropdown or click 'use as-typed' to proceed." Do not submit.
  3. Determine native currency:
     - If resolved → use `add_form_resolved["currency"]`.
     - If as-typed → call `infer_currency_from_ticker(ticker)`. If it raises `UnsupportedTickerError` → show error, abort.
  4. If native currency == EUR:
     - `price_native = Money((eur_total - fees_eur) / shares, EUR)`
     - `fx_rate_eur = Decimal("1")`
     - `fees_native = Money(fees_eur, EUR)`
  5. If native currency != EUR:
     - Call `price_provider.get_historical_close(ticker, trade_date)` → `Money(amount, native_currency)`.
     - On failure → show banner, switch form to fallback mode (preserve user's already-entered values).
     - On success: `fx_rate_eur = (eur_total - fees_eur) / (shares × historical_close.amount)` — quantized to 6 dp.
     - `price_native = historical_close`
     - `fees_native = Money(fees_eur / fx_rate_eur, native_currency)` — derived so that `Transaction.cost_native + fx → Transaction.cost_eur` round-trips.
  6. For SELL transactions: run FIFO validation with the proposed transaction prepended to existing transactions; catch `SellExceedsOpenSharesError` and show the error inline; do not write. (Preserved from original TICKET-009.)
  7. Construct `Transaction(...)`. The TICKET-008c validator double-checks ticker↔currency consistency.
  8. Persist via repository.
  9. Clear `st.cache_data`. If this is a new ticker (not previously in the portfolio), also call `service.clear_caches(price_provider, fx_provider)`.
  10. Set `st.session_state.form_feedback = ("success", f"Recorded {type} of {shares} {ticker} for €{eur_total}.")`. Rerun.

#### Fallback mode (resolver or historical price unavailable)

- [ ] When the form detects unavailable resolver or unavailable historical price, it renders a yellow banner:

  > ⚠ We couldn't fetch the historical price for {ticker} on {date}. You can still record the transaction by entering the native price and FX rate manually below. This usually means yfinance is offline or the ticker is unrecognised.

- [ ] Below the banner, an expander labelled "Manual entry" reveals the original TICKET-009 fields: Currency selectbox, Native price, FX rate. Filling these and clicking Submit follows the original-TICKET-009 submit pipeline.
- [ ] Fallback mode is *transparent*: the user does not have to click anything to enter it. The form decides based on resolver / fetch results.

### Section 2 — All Transactions table

Unchanged from original TICKET-009. Per-row Edit and Delete buttons; inline delete confirmation; sortable columns; ticker/type/date/shares/cost/notes columns. Reuse the `app/ui/styles/dark.css` `.tx-row` class added in original TICKET-009.

### Section 3 — Edit Transaction form

- [ ] Visible only when `st.session_state.editing_tx_id` is set (clicked from a table row).
- [ ] Renders the *same six EUR-native fields* as Add, pre-populated from the transaction being edited:
  - `ticker` ← tx.ticker (read-only — editing the ticker of an existing transaction is a delete + add, not an edit)
  - `type` ← tx.type
  - `trade_date` ← tx.trade_date
  - `shares` ← tx.shares
  - `total_eur_paid` ← tx.cost_eur.amount (computed back from the stored Transaction)
  - `fees_eur` ← (tx.fees_native or 0) × tx.fx_rate_eur (computed back to EUR)
  - `notes` ← tx.notes
- [ ] Same submit pipeline as Add. The historical price lookup may produce a slightly different `price_native` and `fx_rate_eur` than what was originally stored — this is expected and correct (the new values reflect the user's edited EUR total).
- [ ] On successful edit: clear `st.session_state.editing_tx_id`, rerun.

### Section 4 — Delete (preserved from original TICKET-009)

- [ ] Click trash on a row → row collapses to "Are you sure? [Confirm Delete] [Cancel]" inline.
- [ ] Confirm: delete via repository, clear `st.cache_data`, set `form_feedback`, rerun. (Adapter caches are NOT cleared — prices haven't changed.)
- [ ] Cancel: clear `deleting_tx_id`, rerun.

### `app/ui/wiring.py` — extend with resolver

- [ ] Add `get_ticker_resolver()` lazy singleton (TICKET-020 port).
- [ ] All other singletons unchanged.

### Tests

#### `tests/unit/ui/test_manage_form_pipeline.py` — pure-data tests of the submit pipeline

- [ ] **EUR-native happy path:** Resolver returns RHM.DE/EUR. User enters shares=1, eur_total=1388.20, fees=0.99. Pipeline produces `Transaction(ticker="RHM.DE", price_native=Money(Decimal("1387.21"), EUR), fx_rate_eur=Decimal("1"), …)`. The TICKET-008c validator passes.

- [ ] **USD happy path:** Resolver returns APD/USD. Historical close on 2026-05-04 is mocked at $298.35. User enters shares=1, eur_total=256.42, fees=0.99. Pipeline produces `Transaction(ticker="APD", price_native=Money(Decimal("298.35"), USD), fx_rate_eur=Decimal("0.856100"), …)`. Round-trip: `tx.cost_eur ≈ Money(256.42, EUR)`.

- [ ] **JPY happy path:** Resolver returns 5631.T/JPY. Historical close mocked at ¥4500. User enters shares=1, eur_total=27.50, fees=0.99. Pipeline produces a valid Transaction with `currency=JPY`. (This test only exists once TICKET-008c lands.)

- [ ] **Deviation warning:** USD resolver, mocked historical close $298.35, mocked ECB rate 0.8552. User enters eur_total=300.00. Pipeline returns `(transaction, deviation_pct=Decimal("17.4"))`. UI uses deviation_pct to render the yellow banner.

- [ ] **FIFO sell guard:** Existing portfolio has 5 NVDA. User submits SELL of 10 NVDA. Pipeline raises `SellExceedsOpenSharesError`. Caller catches and shows error.

- [ ] **Validator catches as-typed mismatch:** User clicks "use as-typed" on `5631.T`, but `infer_currency_from_ticker` returns JPY, and the user (somehow, via fallback) entered USD price. Validator raises `ValidationError`. (This is the safety net that makes the as-typed escape hatch safe.)

#### `tests/unit/ui/test_manage_page.py` — UI helper tests (preserved from original TICKET-009)

- [ ] Session-state initialisation idempotent.
- [ ] Edit pre-population fills all fields correctly.
- [ ] Delete confirmation flow toggles state correctly.

#### `tests/integration/test_manage_e2e.py` — end-to-end with fakes

- [ ] Construct `JsonTransactionRepository` over a temp file. Construct `FakeTickerResolver` (returns canned matches), `FakePriceProvider`, `FakeFxProvider`. Run the Add pipeline three times: one EUR ticker, one USD ticker, one JPY ticker. Assert: file contains three valid transactions; loading them via the repository succeeds.
- [ ] Run the Edit pipeline: load an existing tx, modify shares, submit. File is updated; round-tripping the loaded tx matches the new shape.
- [ ] Run the Delete pipeline: file shrinks by 1.
- [ ] Test the resolver-failure → fallback path: mock `FakeTickerResolver.resolve` to raise; assert pipeline switches to manual-entry mode and produces the same Transaction shape when given native price + FX inputs.

### Lints / quality

- [ ] `pytest` — all tests pass (existing + new).
- [ ] `ruff check .` — passes.
- [ ] `mypy app/` — passes; UI standard mode.
- [ ] `lint-imports` — passes; `app/ui/pages/manage.py` imports from `app.services.*`, `app.domain.*`, `app.ui.*`. Not from adapters.
- [ ] Manual: `streamlit run app/ui/main.py`, navigate to Manage Portfolio, perform Add/Edit/Delete cycles. Screenshot in PR description showing the live "Recording" panel with the deviation check.

### State updates (per CLAUDE.md session-end ritual)

- [ ] `docs/SESSION_LOG.md` appended.
- [ ] `docs/PROJECT_STATE.md` updated.
- [ ] `docs/TICKETS/BACKLOG.md` updated.
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.

---

## Files created

```
tests/unit/ui/test_manage_form_pipeline.py
tests/integration/test_manage_e2e.py
tests/fakes/ticker_resolver.py             ← FakeTickerResolver for tests
```

## Files modified

```
app/ui/pages/manage.py                     ← rewrite to EUR-native shape; preserve session_state and delete flow
app/ui/wiring.py                            ← add get_ticker_resolver()
app/ui/styles/dark.css                      ← any tweaks for the new "Recording" preview panel
docs/TICKETS/BACKLOG.md                     ← TICKET-009-revised → IN_REVIEW
README.md                                   ← update "First-time portfolio setup" section
```

## Files deleted

```
(none — original TICKET-009 PR is closed without merging, so no merged code is being deleted)
```

---

## Out of scope

- **The `TickerResolver` port itself.** That is TICKET-020. This ticket assumes it exists and consumes it.
- **The currency-correctness fixes.** TICKET-008c. This ticket assumes JPY is in the enum and the validator runs.
- **Pre-trade tax impact preview.** Same as original TICKET-009: that is TICKET-012.
- **Bulk import from broker CSV.** Future ticket.
- **Multi-line transactions** (e.g., a partial fill split across two prints with one fee). For now: one form submission = one `Transaction`. If Scalable reports a single fill that is actually two prints, the user enters one weighted-average row. Future ticket can split.
- **Transaction history audit log beyond git.** Same as original TICKET-009.
- **Scalable PDF parser** that auto-fills the form from a confirmation upload. Tempting; out of scope.

---

## Test cases (selected, illustrative)

1. **The original TICKET-009 bugs cannot recur:**
   - Bug #1 (silent FX=1.0): there is no FX field for the user to leave at 1.0. The pipeline computes FX from EUR-total ÷ historical-native-close. If the historical close fetch fails, the form switches to fallback mode with a *visible banner* — silent fallback is impossible.
   - Bug #2 (Currency=EUR for NVDA): there is no Currency dropdown to mis-set. Currency comes from the resolver (or from `infer_currency_from_ticker`). If the resolver returns USD for NVDA, USD is used.
   - Bug #3 (5631.T as USD): TICKET-008c's validator rejects this construction at `Transaction(...)` time. The form would never be able to submit it.

2. **The Scalable workflow works:**
   - User opens Scalable, sees "Bought 1 APD, €256.42 debited, fee €0.99".
   - User opens dashboard, types "AP", clicks APD from autocomplete, enters shares=1, eur_total=256.42, fees=0.99 (already defaulted), submits.
   - Result: `Transaction(ticker="APD", currency=USD, price_native=$298.35, fx_rate=0.8561, shares=1, fees_native=$1.156)` — perfectly reconciled.
   - Live Overview gain on the new lot is approximately €0 (1 share at price ≈ price the user just paid).

3. **The deviation guard works:**
   - User typo: enters eur_total=2564.20 instead of 256.42 (extra zero). Resolver knows APD is USD; historical close was $298.35 (1 share = ~$298). Implied FX = 2564.20 / 298.35 ≈ 8.6 — wildly off the ECB rate of ~0.86. Deviation banner fires. User notices and corrects.

4. **EUR-native transactions are trivially fast:**
   - User enters RHM.DE, eur_total=1388.20, no historical-price lookup happens (currency=EUR, FX=1.0 by definition). Submit completes without a network call to the resolver's historical-price method.

---

## Notes (for future AI sessions)

### Why the resolver call is on every keystroke

Streamlit's render-on-rerun model means that yes, every keystroke can trigger a resolver call. Two mitigations: (a) the resolver is cached aggressively at the adapter level (TICKET-020 spec), so repeated calls for the same prefix are local. (b) The form throttles by checking `len(query) >= 2` before calling. In practice, typing "APD" produces 2 calls ("AP" and "APD"), both cached after the first.

### Why "use as-typed" exists

For two cases: (a) resolver/network is down, user still wants to record a trade; (b) the user is entering a ticker the resolver does not yet know (rare but possible). The TICKET-008c validator is the safety net — even with as-typed, the construction will fail if the inferred currency disagrees with the user's input.

### Why we do not store the resolver match details on the Transaction

Tempting to store `name="NVIDIA Corporation", exchange="NASDAQ"` directly on the Transaction. We don't, because:
- The Transaction model is the book-of-record. Display metadata is presentational.
- The resolver can be queried at render time for these fields. If the company is renamed (Facebook → Meta), the historical Transaction stays correct.
- Schema bloat. Keep `Transaction` minimal.

The display-name dict in `app/ui/pages/overview.py` (placeholder from TICKET-008) becomes obsolete after this ticket — Overview can call the resolver instead. That cleanup is a one-liner, included in this ticket.

### Why the original TICKET-009 PR is closed without merging

Three reasons:
1. The form's input model is broker-incompatible (the central point of ADR-005). Merging would lock the user into a workflow that demands data they do not have.
2. The three silent-corruption bugs we observed are *symptoms* of the input-model mismatch, not random implementation defects. Fixing them in place would not address the root cause.
3. The session_state and delete-flow code we want to preserve is small enough to copy forward into the new implementation. Closing the PR loses ~80 lines of preservable code, which is cheaper than the cognitive cost of merging-then-rewriting.

The author of the original TICKET-009 implementation (Gemini per session log) is not penalised — the ticket spec they implemented was correct as drafted. The lesson belongs in METHODOLOGY.md: *bench-test the workflow on real broker data before declaring a ticket DRAFT-ready*.
