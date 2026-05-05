# TICKET-008c — Currency-correctness audit, JPY support, and `data/portfolio.json` migration

**Status:** IN_REVIEW
**Priority:** P0 (blocks TICKET-009-revised; live app currently shows €4,000+ in fake gains)
**Estimated session length:** 1.5 – 2 hr
**Drafted by:** Vivek + Claude (chat 2026-05-04)
**Implemented by:** _pending_
**Depends on:** TICKETs 001 (domain), 002 (FIFO), 003 (repo), 004-005 (yfinance adapter), 008 (seed CSV)

> **This ticket fixes silent data corruption discovered on 2026-05-04.** The Live Overview is currently displaying €4,031.89 of fake unrealised gain on the 5631.T (Japan Steel Works) position because a JPY-priced security is being stored and valued as if its native currency were USD. This ticket extends the `Currency` enum, fixes the seed CSV, migrates `data/portfolio.json`, and adds a domain-level guard that prevents the same class of bug from recurring.

---

## Problem

The seed for TICKET-008 included this row:

```csv
5631.T,buy,2025-11-10,1.0000,4200.0000,USD,0.9300,Japan Steel Works (use USD as approximation; KRW/JPY not supported in v1)
```

The "v1 approximation" is producing wildly wrong numbers in the live app. Reproducing the math:

- Recorded as: 1 share at "$4,200" with FX 0.93 EUR/USD → cost basis €3,906
- Engine computes live value as: 1 × `live_price_native(5631.T)` × `live_fx(USD,EUR)` = 1 × 9,283 (actually JPY) × ~0.855 (USD→EUR) = **€7,937**
- Reported gain: **+€4,032 (+103%)**

The truth:

- 5631.T trades on Tokyo in **JPY**, not USD. Today's price is ~9,049 JPY ≈ **€52**.
- A 1-share position is worth roughly €52, not €7,937.
- The cost basis (whatever Vivek actually paid) is also wrong because €3,906 is roughly 150× the true cost.

Three independent failures stacked:

1. **Domain enum gap.** `Currency` is `EUR | USD` only. JPY tickers have no correct representation.
2. **No domain-level ticker→currency check.** The seed loader and (in TICKET-009) the manual entry form happily accept any ticker with any currency. Nothing rejects "5631.T as USD."
3. **Live valuation is unaware of the lie.** The valuation service multiplies a JPY price by a USD→EUR rate and produces nonsense. Per-ticker failure isolation hides nothing because no exception is raised — the math succeeds, it just produces a fictional number.

This ticket addresses all three.

---

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-04 (see ADR-005):

1. **Extend `Currency` to `EUR | USD | JPY`.** GBP and CHF are obvious next neighbours but are not seeded in any current transaction; we add JPY only and document the one-line extension path. Speculative enum members are not added.
2. **Add a domain-level invariant: `Transaction.ticker` must be consistent with `Transaction.price_native.currency`.** This is enforced via a class validator that calls a pure-function helper `infer_currency_from_ticker(ticker)`. If the ticker's inferred currency does not match the price's currency, construction fails. This is the "shut the door before the horse leaves" fix — once this validator is in place, the bug class becomes structurally impossible.
3. **`infer_currency_from_ticker` is the single source of truth for ticker → currency mapping.** It lives in `app/domain/tickers.py` as a pure function. The yfinance adapter (TICKET-004-005), the seed loader, and the new resolver (TICKET-020) all defer to it. Changing the mapping happens in exactly one place.
4. **Migration is a one-shot Python script with a dry-run preview.** Run once to upgrade `data/portfolio.json` and `docs/reference/seed_portfolio.csv`. After this ticket merges, the migration script is preserved at `app/scripts/migrate_currency.py` for documentation purposes but is not part of the daily workflow.
5. **The dashboard fails *loudly* on legacy bad data.** When `JsonTransactionRepository.load_all()` encounters a transaction whose ticker disagrees with its currency, it raises `LegacyDataError` with instructions to run the migration. Better to crash on startup than to silently display lies.
6. **Cost basis for the affected 5631.T lot is recomputed from Vivek's memory of what he actually paid in EUR**, not synthesised from a guessed JPY price × historical FX. We already established (ADR-005) that EUR-debit is the most reliable source; the migration treats Vivek's recollection of "I paid roughly €X" as the truth and back-computes consistent native price + FX from there.

---

## Acceptance criteria

### `app/domain/money.py` — extend the `Currency` enum

- [ ] `Currency` enum gains `JPY = "JPY"`.
- [ ] `Money.__str__` formatting: JPY uses `¥` prefix and **zero decimal places** (yen is not subdivided in market data — `¥9,049` not `¥9,049.00`). Update the format dispatch table.
- [ ] All existing `Money` arithmetic and comparison rules apply unchanged (same-currency only, etc.).
- [ ] Tests: `tests/unit/domain/test_money.py` gains JPY-specific cases:
  - `Money(Decimal("9049"), JPY)` constructs and `__str__`'s as `"¥9,049"`.
  - `Money(JPY) + Money(USD)` raises `CurrencyMismatchError`.
  - `Money.zero(JPY)` works.

### `app/domain/tickers.py` — new module

- [ ] New file. Pure function with no I/O imports:

  ```python
  from app.domain.money import Currency

  _SUFFIX_TO_CURRENCY: dict[str, Currency] = {
      ".DE": Currency.EUR,
      ".F":  Currency.EUR,
      ".MI": Currency.EUR,
      ".PA": Currency.EUR,
      ".AS": Currency.EUR,
      ".T":  Currency.JPY,
      ".HK": Currency.JPY,  # placeholder — HKD not yet supported, see notes
  }

  def infer_currency_from_ticker(ticker: str) -> Currency:
      """
      Map a ticker symbol to its native trading currency.

      Rules:
      - Suffix-based for non-US exchanges (.DE → EUR, .T → JPY, etc.)
      - Default to USD for unsuffixed symbols (NVDA, ASX, MU)

      Raises UnsupportedTickerError if the suffix is recognised but maps to
      a currency we do not yet support in the Currency enum.
      """
  ```

- [ ] `UnsupportedTickerError` exception class defined in this module.
- [ ] **The `.HK` (Hong Kong, HKD) entry is commented out in v1** with a `TODO` referencing a future ticket. The function raises `UnsupportedTickerError` for `.HK` tickers. We do not pretend HKD support exists.
- [ ] `app/domain/__init__.py` re-exports `infer_currency_from_ticker` and `UnsupportedTickerError`.

### `app/domain/models.py` — add the consistency validator

- [ ] `Transaction` gains a class validator (`@model_validator(mode="after")`):
  - Calls `infer_currency_from_ticker(self.ticker)`.
  - If result does not equal `self.price_native.currency`, raises `ValidationError` with message: `"Ticker {ticker} trades in {inferred} but transaction recorded as {actual}. See ADR-005."`
- [ ] If `infer_currency_from_ticker` itself raises `UnsupportedTickerError`, the validator re-raises as a `ValidationError` with the same message — Pydantic's expected error type.
- [ ] Tests in `tests/unit/domain/test_transaction.py`:
  - `Transaction(ticker="NVDA", price_native=Money(100, USD), …)` — succeeds.
  - `Transaction(ticker="NVDA", price_native=Money(100, EUR), …)` — `ValidationError`.
  - `Transaction(ticker="5631.T", price_native=Money(9000, JPY), …)` — succeeds.
  - `Transaction(ticker="5631.T", price_native=Money(4200, USD), …)` — `ValidationError`. **This is the regression test for the original bug.**
  - `Transaction(ticker="RHM.DE", price_native=Money(1452, EUR), …)` — succeeds.

### `app/adapters/repo_json/json_repo.py` — fail loudly on legacy data

- [ ] New exception in this module: `LegacyDataError(Exception)`. Constructor takes `(path: Path, count: int, first_offender: dict)`. Message format:

  > Found {count} transaction(s) in {path} that fail the ticker↔currency consistency check. First offender: {first_offender}. Run `python -m app.scripts.migrate_currency --input {path}` to upgrade.

- [ ] `JsonTransactionRepository.load_all()` catches `ValidationError` during `Transaction` construction and re-raises as `LegacyDataError` collecting all offending rows. (The first offender is included in the message; the full list is `.offenders` attribute on the exception.)
- [ ] Tests in `tests/integration/test_json_repo.py`:
  - Load a fixture `tests/fixtures/portfolio_legacy_jpy_as_usd.json` containing the original bad 5631.T row → expect `LegacyDataError`, message contains "5631.T".
  - Load a clean fixture → succeeds.

### `app/adapters/yfinance_feed.py` — extend currency inference, add JPY ticker support

- [ ] `_infer_currency` (existing helper) is replaced by a delegation to `infer_currency_from_ticker` from the domain module. Single source of truth.
- [ ] `get_current_price` and `get_historical_close`: no logic change beyond the new currency support — yfinance returns JPY prices for `.T` tickers natively, so the only change is that the wrapped `Money` now accepts `Currency.JPY`.
- [ ] `get_current_rate` / `get_historical_rate`: extend supported pairs from `{(EUR, USD), (USD, EUR)}` to also include `{(EUR, JPY), (JPY, EUR), (USD, JPY), (JPY, USD)}`. Implementation pattern unchanged: yfinance ticker `f"{base}{quote}=X"`. Add tests in `tests/integration/test_yfinance_adapter.py` (gated behind `@pytest.mark.integration` as existing).
- [ ] Update `UnsupportedCurrencyPairError` message to reflect the new supported set.

### `app/scripts/migrate_currency.py` — one-shot migration tool

- [ ] New file. CLI:

  ```
  python -m app.scripts.migrate_currency --input data/portfolio.json [--output data/portfolio.json] [--dry-run] [--force]
  ```

- [ ] Reads JSON via raw `json.load` (NOT through `JsonTransactionRepository`, which would refuse to load legacy data).
- [ ] For each transaction, runs `infer_currency_from_ticker(tx["ticker"])` and compares to `tx["price_native"]["currency"]`.
- [ ] When they disagree, the script does **not** silently rewrite the price. It looks up the historical native price for `tx["trade_date"]` via `YfinanceAdapter.get_historical_close(ticker, trade_date)`, then back-computes a corrected `(price_native, fx_rate_eur)` pair such that the recorded EUR cost basis is *preserved*:

  ```
  total_eur_cost = old_price_native * old_fx_rate * shares + old_fees   # what we believed
  new_price_native = historical_close_in_correct_currency               # from yfinance
  new_fx_rate_eur  = (total_eur_cost - fees_eur) / (new_price_native * shares)
  ```

  **Why preserve total EUR cost rather than native price × FX?** Because for the 5631.T row specifically, the recorded "USD price" was a fabrication — it was Vivek's *guess at the JPY price labelled as USD*. The historical JPY price from yfinance is the truth, and the EUR cost basis the user has been seeing in the dashboard is the value we want to preserve as their reference point. If Vivek wants to override with what he *actually* paid, he can re-edit via TICKET-009-revised after this lands.

- [ ] **For 5631.T specifically the migration is interactive.** The script prints:

  > Found legacy 5631.T row recorded as USD with price=4200, fx=0.93, shares=1, fees=0.
  > Recorded EUR cost basis: €3,906
  > yfinance historical JPY close on 2025-11-10: ¥X
  > Inferred new fx_rate_eur: Y
  > Vivek: is €3,906 the right cost basis, or do you want to override? [enter to accept / type a EUR amount to override]

  This is the *only* row with this special handling because it is the only one where the original "USD" was a known fabrication. All other USD-priced rows are correctly USD; the migration leaves them untouched.

- [ ] `--dry-run`: prints the diff to stdout, writes nothing.
- [ ] `--force`: overwrites the output file (default refuses if output exists, same convention as `seed_portfolio.py`).
- [ ] Validates the output by round-tripping through `JsonTransactionRepository` before writing — if the migrated data still fails to load, abort with a clear error.
- [ ] Tests in `tests/integration/test_migrate_currency.py`:
  - **Dry-run leaves files untouched**.
  - **Migrates 5631.T fixture correctly**: input has `currency=USD price=4200`, output has `currency=JPY price=<yfinance close>` and the same EUR cost basis. (Use a `FakePriceProvider` that returns a known JPY close.)
  - **Leaves clean rows alone**: NVDA at USD stays USD-priced.
  - **Validates output loads**: after migration, `JsonTransactionRepository(out_path).load_all()` succeeds.

### `docs/reference/seed_portfolio.csv` — fix the seed at source

- [ ] The 5631.T row is rewritten to use JPY:

  ```csv
  5631.T,buy,2025-11-10,1.0000,4200.0000,JPY,0.0061,Japan Steel Works (Tokyo, JPY-priced)
  ```

  *(The exact `price_native` and `fx_rate_eur` values are placeholders — the chat-reviewed seed CSV will use values consistent with whatever historical close Vivek's actual purchase resolved to. The migration script will compute these from yfinance during implementation.)*

- [ ] Top of the CSV gains a comment row noting the schema convention:

  ```csv
  # Currency must match infer_currency_from_ticker(ticker). See ADR-005, TICKET-008c.
  ```

- [ ] The "use USD as approximation; KRW/JPY not supported in v1" note in the original 5631.T row is **deleted**. That comment was the seed of this bug; leaving it would invite repetition.

### `data/portfolio.json` — migrated artefact

- [ ] Migration is run as part of this ticket's PR. The new `data/portfolio.json` is committed *only if* it is currently tracked (which it now is per TICKET-008b's `.gitignore` fix — confirm). If the rule is "user data is gitignored", the migration runs locally and is documented in the PR description rather than committed.
- [ ] Either way: after this ticket merges, the live app shows 5631.T with a sane EUR value (~€52 for 1 share at current price) and a sane gain (close to zero, because Vivek bought it for roughly that amount).

### Lints / quality

- [ ] `pytest` — all tests pass (existing + new).
- [ ] `ruff check .` — passes.
- [ ] `mypy app/` — passes; **strict mode on `app/domain/`** including the new `tickers.py`.
- [ ] `lint-imports` — passes; `app/domain/tickers.py` imports only from `app.domain.money` (and stdlib).
- [ ] Manual: `streamlit run app/ui/main.py` — confirm 5631.T row no longer shows €7,937 value or +€4,032 gain. Screenshot in PR description.

### State updates (per CLAUDE.md session-end ritual)

- [ ] `docs/SESSION_LOG.md` appended.
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-008c → IN_REVIEW; "Done" gains relevant predecessors).
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-008c row → IN_REVIEW).
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.
- [ ] PR description includes: **before/after screenshots of the Live Overview** showing the 5631.T row going from "€7,937 / +€4,032" to a sane value.

---

## Files created

```
app/domain/tickers.py
app/scripts/migrate_currency.py
tests/unit/domain/test_tickers.py
tests/integration/test_migrate_currency.py
tests/fixtures/portfolio_legacy_jpy_as_usd.json
```

## Files modified

```
app/domain/money.py                       ← Currency enum gains JPY; __str__ formatting
app/domain/models.py                      ← Transaction gains ticker↔currency validator
app/domain/__init__.py                    ← export new symbols
app/adapters/repo_json/json_repo.py       ← LegacyDataError on malformed load
app/adapters/yfinance_feed.py             ← delegate to infer_currency_from_ticker; JPY pairs
tests/unit/domain/test_money.py           ← JPY cases
tests/unit/domain/test_transaction.py     ← regression test for 5631.T-as-USD bug
tests/integration/test_json_repo.py       ← LegacyDataError test
tests/integration/test_yfinance_adapter.py ← JPY price + JPY/EUR rate cases
docs/reference/seed_portfolio.csv         ← 5631.T row rewritten as JPY
data/portfolio.json                       ← migrated (committed only if tracked)
docs/TICKETS/BACKLOG.md                   ← TICKET-008c → IN_REVIEW
```

---

## Out of scope

- **GBP, CHF, HKD, AUD support.** Adding more currencies is a one-line enum change and a few lines in `tickers.py`. We add only what current data needs (JPY for 5631.T). Future tickets handle other currencies as transactions in those currencies appear.
- **Ticker autocomplete / resolver.** That is TICKET-020. This ticket only fixes the data; the resolver UX comes with the new form.
- **Form changes.** This ticket leaves `app/ui/pages/manage.py` alone. TICKET-009-revised replaces it.
- **Verifying every other holding's currency is correct beyond what the validator catches.** The new validator runs on every `Transaction.load`, so the migration is automatic for all rows. There is nothing extra to verify by hand.
- **Schema versioning bump.** The JSON file already has `version: 1` (TICKET-003). The migrated data is still version 1 in shape — only the values of `currency` and `price_native` change for one row. No bump needed.

---

## Test cases (selected, illustrative)

1. **The original bug, regression test:** `Transaction(ticker="5631.T", price_native=Money(Decimal("4200"), Currency.USD), shares=1, …)` raises `ValidationError`. Before this ticket, that construction succeeded silently.

2. **Inferred-currency happy path:** `Transaction(ticker="5631.T", price_native=Money(Decimal("9049"), Currency.JPY), fx_rate_eur=Decimal("0.0061"), shares=1, …)` constructs successfully. `cost_eur` returns `Money(Decimal("55.20"), Currency.EUR)` (within precision tolerance).

3. **Legacy data refusal:** `JsonTransactionRepository(legacy_fixture_path).load_all()` raises `LegacyDataError`, message references "5631.T", `.offenders` list has length 1.

4. **Migration round-trip:** Run `migrate_currency.py` on legacy fixture → `JsonTransactionRepository(migrated_path).load_all()` succeeds and returns N transactions where N matches the input row count.

5. **Migration preserves EUR cost basis:** For the legacy 5631.T row with EUR cost basis €3,906 (= 4200 × 0.93), after migration `tx.cost_eur == Money(Decimal("3906"), Currency.EUR)` (within precision tolerance, ignoring the interactive Vivek-overrides-it path).

6. **Yfinance live JPY:** `YfinanceAdapter().get_current_price("5631.T")` returns `Money(amount=<some JPY value>, currency=Currency.JPY)`, not USD. (Integration-tagged.)

7. **Live valuation correctness:** End-to-end with seeded JPY data, the `compute_live_positions` result for 5631.T has `live_value_eur` in the €40–€60 range (single share at current Tokyo close × current JPY/EUR), not €7,000+. (Integration-tagged.)

---

## Notes (for future AI sessions)

### Why this is P0

The Live Overview is currently displaying a fake €4,032 of gain. A user looking at the dashboard to make decisions could trim the wrong position based on this lie. P0 means "drop everything else and fix this." This is exactly that case.

### Why the validator goes in `domain/`, not `services/` or `adapters/`

Because the invariant is *about the data itself*, not about how it is fetched, stored, or displayed. A `Transaction` whose ticker disagrees with its currency is a malformed `Transaction`, the same way a `Transaction` with negative shares is a malformed `Transaction`. The domain layer rejects it. Services and adapters get to assume validity, which is the existing architectural pattern (see TICKET-001 `cost_native` derived property — the engine assumes valid input).

### Why `infer_currency_from_ticker` is a pure function and not a port

A port would suggest "this is a thing we might swap implementations of." We do not. The mapping from `.T` to JPY is a hard fact, not a strategic choice. A pure function is the right shape. If a future feature needs a *real* security-master lookup (full company name, CUSIP, ISIN, exchange, etc.), that becomes the new `TickerResolver` port (TICKET-020) — and the resolver's first job at startup will be to reconcile its richer data against `infer_currency_from_ticker` to catch any disagreements.

### Why the migration script is not deleted after one use

Two reasons. First, documentation: a future session reading this ticket can see exactly what transformation was done. Second, future migrations: if we add GBP support later, the same script structure handles "rows that were stored as USD but should be GBP." The migration script becomes a small library of one-shot transforms, growing only as needed.

### Why we crash on legacy data instead of auto-migrating

Auto-migration on load would mask the migration step from the user. The user might never know their data was rewritten. Crashing forces them to run the migration explicitly, see the diff, and consent. Quiet rewrites of user data violate the principle that the dashboard should never lie about what it has done.
