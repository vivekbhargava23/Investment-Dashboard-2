# TICKET-CSV-7 — Scalable importer: EUR-native and Security-transfer pair fix

**Status:** QUEUED
**Priority:** CRITICAL
**Estimated session length:** 2 hr
**Drafted by:** Vivek + AI (chat session 2026-05-16)
**Implemented by:** _agent fills in_
**Milestone:** Foundation

## Problem

Two related bugs in `app/adapters/scalable_csv/` produce a portfolio that does not match the Scalable Capital app:

### Bug 1 — Security-transfer pair double-import

Scalable issues `Security transfer` rows in matched `+N / -N` pairs representing internal asset reshuffles (same ISIN, adjacent dates, near-identical prices). These are not economic events; they net to zero in the Scalable app and should be invisible to the user.

The current importer (`importer.py` line 168, `planner.py` line 90) correctly skips the **outgoing** leg (negative shares) but **imports the incoming leg as a BUY** (planner treats `Security transfer` as a buy: `tx_type_str = "buy" if row.type in ("Buy", "Savings plan", "Security transfer")`). Result: every Security-transfer pair leaves a phantom position equal to the inbound leg.

Verified against the 2026-05-14 CSV export (301 rows, 26 Security-transfer rows in 13 pairs):
- **NVDA** — Live Overview shows 24.440 shares; CSV reconciles to 17.220; delta is exactly the 7.220 `+7.22` Security-transfer leg from 2025-12-06.
- **DELL** — Live Overview shows 20 shares with €2,389.60 cost; CSV reconciles to 0 (fully sold by 2026-01-23); the phantom 20 shares are the `+20 @ 119.48 = 2,389.60` Security-transfer leg from 2025-12-06.
- **PARRO (FR0004038263)** — Live Overview shows 50 shares; CSV reconciles to 0 (fully sold by 2026-01-23); the phantom 50 shares are the `+50` Security-transfer leg from 2025-12-06.

Every position in the current portfolio that does not match Scalable has a Security-transfer pair in its history; every position that reconciles cleanly does not. The correlation is 1:1.

### Bug 2 — Fabricated USD prices and inferred FX rates

Every row in the Scalable CSV has `currency=EUR`, including US-listed securities like NVDA, DELL, MU, AAPL-style tickers. The `price` column reports the **per-share EUR price at execution**, and `amount` reports the **EUR cash flow** (`amount ≈ shares × price` per the existing `_check_amount` sanity check). There is no native-currency price anywhere in this CSV.

Despite this, `importer.py` lines 252–268 do the following for any ticker whose inferred native currency is not EUR:

```python
fx_rate_eur = fx_provider.get_historical_rate(native_ccy, Currency.EUR, row.date)
native_price_amount = row.price / fx_rate_eur
price_native = Money(amount=native_price_amount, currency=native_ccy)
```

This divides the **already-EUR** `row.price` by a historical FX rate, fabricating a "native USD price." The stored `price_native = $200.33` for an NVDA buy that actually executed at €171.46. The stored `fx_rate_eur = 0.856` was the USD→EUR rate that day, used for the back-derivation.

The total EUR cost basis happens to round-trip correctly (`fake_usd × fake_fx = real_eur`), but:
- Every USD figure shown in the UI is fiction. Live Overview's `NVDA … USD … 225.32 … 24.440 shares` is double-fabricated: phantom shares AND fake USD prices.
- The importer makes an unnecessary network call per non-EUR row.
- The importer has a `FX_UNAVAILABLE` failure mode that blocks perfectly good EUR data from importing when yfinance is offline.
- The user requirement is "everything in EUR to match the Scalable app." Storing USD is actively counter to this.

### Why this matters now

- **Sell Simulator and tax engine** produce nonsense for any post-CSV-5 position (downstream of incorrect shares and inflated USD cost bases).
- **Live Overview** misleads on every USD ticker.
- **Real Scalable values** (NVDA = 17.22 shares, current EUR value ≈ €3,333) cannot be cross-checked against the dashboard.
- The user has confirmed `portfolio.json` is disposable; full re-import is the chosen recovery path.

## Acceptance criteria

- [ ] **Both legs** of every `Security transfer` row are skipped in `planner.py` (status: new `INTERNAL_TRANSFER` row status with `SKIP` action). Remove the `row.shares < 0` guard.
- [ ] **Both legs** of every `Security transfer` row are skipped in `importer.py` (new summary counter `internal_transfers_skipped` replacing/augmenting `outgoing_transfers_skipped`).
- [ ] `Security transfer` is removed from `_IN_SCOPE_TYPES` in both files (it is no longer in scope at all).
- [ ] `tx_type_str` computation in `planner.py` no longer includes `Security transfer` in the buy branch.
- [ ] `importer.py` no longer calls `fx_provider.get_historical_rate(...)` from the Scalable code path. The `fx_provider` parameter on `run_import` is removed.
- [ ] `importer.py` no longer calls `infer_currency_from_ticker(...)` from the Scalable code path.
- [ ] For every imported `Transaction`: `price_native.currency == Currency.EUR`, `fx_rate_eur == Decimal("1")`, `fees_native.currency == Currency.EUR` (when fees present), and `price_native.amount == row.price` exactly (no rounding, no division).
- [ ] `planner.py` `fx_provider` parameter is removed. Row statuses `FX_UNAVAILABLE` and `NEEDS_CURRENCY_SUPPORT` are removed from `app/domain/csv_import.py` (no longer reachable from this importer).
- [ ] Workbench (`app/ui/pages/import_workbench.py`) and any callers are updated to stop passing `fx_provider` into planner/importer.
- [ ] `app/ui/wiring.py::get_import_fx_provider` is removed (dead code after this ticket).
- [ ] Reconciliation acceptance test passes against the uploaded fixture CSV — see "Test cases" below.
- [ ] Existing `_check_amount` and `_check_sign` sanity checks remain in place and continue to pass against the fixture.
- [ ] Tests pass: `pytest tests/unit/adapters/scalable_csv/`
- [ ] Lints pass: `ruff check . && mypy app/ && lint-imports`

## Files likely touched

- `app/adapters/scalable_csv/planner.py` — remove `_IN_SCOPE_TYPES` entry, remove FX path, update `tx_type_str`, skip both Security-transfer legs
- `app/adapters/scalable_csv/importer.py` — remove FX/native-currency branch, remove `fx_provider` parameter, replace `outgoing_transfers_skipped` with `internal_transfers_skipped`, skip both Security-transfer legs, drop `Security transfer` from `_IN_SCOPE_TYPES`
- `app/domain/csv_import.py` — remove `RowStatus.FX_UNAVAILABLE` and `RowStatus.NEEDS_CURRENCY_SUPPORT`, add `RowStatus.INTERNAL_TRANSFER`
- `app/ui/pages/import_workbench.py` — drop `fx_provider` arg in planner/importer calls
- `app/ui/wiring.py` — remove `get_import_fx_provider`
- `tests/fixtures/scalable_csv/full_export_2026_05_14.csv` — new fixture, exact copy of the user's CSV (301 rows, MD5 `0b296556b2b8519b7c39e6a8e109cb64`)
- `tests/fixtures/scalable_csv/full_export_2026_05_14_isin_map.json` — pre-populated ISIN→ticker map for all 27 ISINs in the fixture (see Notes)
- `tests/unit/adapters/scalable_csv/test_importer.py` — new `test_full_export_reconciliation` test
- `tests/unit/adapters/scalable_csv/test_planner.py` — update affected tests, add tests for new behaviour

## Out of scope

- Distributions ingestion (21 rows in CSV currently classified `OUT_OF_SCOPE_V1` — separate future ticket; do not extend `_IN_SCOPE_TYPES` to include them).
- Corporate actions ingestion (2 rows — separate future ticket).
- Stock-split handling for NVDA pre-June-2024 rows (these reconcile to 0 net shares in this dataset; do not introduce split logic).
- Live Overview UI changes (handled in TICKET-UI-2).
- Table filtering UI (handled in TICKET-UI-1).
- `TICKER_KIND` updates (handled in TICKET-TAX-1).
- Migration of existing `portfolio.json` data. The user has confirmed `data/portfolio.json` will be wiped and re-imported manually after this ticket merges. No data-migration script needed.
- Renaming the `fx_rate_eur` field on `Transaction` (still useful for hypothetical future non-EUR importers; just always set to `Decimal("1")` for Scalable rows).
- Keeping the `FxProvider` port. It stays — other adapters (`fx_yfinance`, valuation service) still use it.

## Test cases

The single critical test is **reconciliation against the user's real CSV**. Add a fixture file containing the full 301-row export and assert:

1. **`test_full_export_reconciliation`** — Given the uploaded CSV and a pre-populated ISIN map (see Notes), when `run_import` is called against an empty repo, then the resulting portfolio satisfies all of:

   | Ticker / ISIN | Expected shares | Notes |
   |---|---|---|
   | NVDA (US67066G1040) | 17.220 | was 24.440 before fix |
   | DELL (US24703L2025) | 0 | was 20 before fix |
   | FR0004038263 (Parrot) | 0 | was 50 before fix |
   | US00215W1009 (ASE) | 55 | |
   | IE000QDFFK00 (AXA Nasdaq Acc) | 5.708 | |
   | US0404132054 (Arista) | 10 | |
   | US11135F1012 (Broadcom) | 3 | |
   | IE00B8KQN827 (Eaton) | 5 | |
   | JP3721400004 (Japan Steel Works) | 16 | |
   | US5738741041 (Marvell) | 8.054176 | |
   | US5951121038 (Micron) | 8 | |
   | CA65704Y1079 (NIOB) | 400 | |
   | DE0007030009 (Rheinmetall) | 1 | |
   | US78392B1070 (SK Hynix GDR) | 6 | |
   | US81762P1021 (ServiceNow) | 4 | |
   | IE00BFMXXD54 (Vanguard S&P 500 Acc) | 13.612073 | |
   | IE00B3WJKG14 (iShares S&P 500 IT) | 2.086 | |
   | US0091581068 (APD) | 0 | fully sold |
   | US1717793095 (Ciena) | 0 | fully sold |
   | US50155Q1004 (Kyndryl) | 0 | fully sold |
   | IE00BMFKG444 (Xtrackers Nasdaq Acc) | 0 | fully sold |
   | IE00B42NKQ00 (iShares S&P 500 Energy) | 0 | fully sold |
   | CH1129538448 (21Shares Polygon ETP) | 0 | |
   | CH1109575535 (21Shares Stellar ETP) | 0 | |
   | CH0491507486 (21Shares Tezos ETP) | 0 | |
   | DE000HT41XN9 (HSBC Apple Turbo) | 0 | |
   | GB00BNRRF105 (CoinShares Algorand) | 0 | |

   The assertion is on **net shares per ticker** computed by summing `BUY` shares and subtracting `SELL` shares from the imported transactions. 15 ISINs end with non-zero positions; 12 end at zero.

2. **`test_security_transfer_pair_skipped`** — Given a minimal CSV with one `+5 / -5` Security-transfer pair on the same ISIN, when imported, then zero transactions are created and the summary's `internal_transfers_skipped == 2`.

3. **`test_all_transactions_are_eur_native`** — After importing the fixture, assert `tx.price_native.currency == Currency.EUR and tx.fx_rate_eur == Decimal("1")` for every imported transaction (using `pytest.mark.parametrize` or a loop).

4. **`test_no_fx_provider_required`** — Call `run_import(...)` without passing `fx_provider` (the parameter is removed). The import succeeds on the full fixture. (Also serves as a compile-time check that the parameter is gone.)

5. **`test_amount_sanity_check_still_passes`** — Existing `_check_amount` test continues to pass against the fixture (regression guard — if `_check_amount` raises on any fixture row, the importer is broken).

6. **Planner-level test `test_planner_skips_both_security_transfer_legs`** — Both legs receive `RowStatus.INTERNAL_TRANSFER` and `PlannedAction.SKIP`.

## Notes

### Pre-populated ISIN map for the fixture

The reconciliation test needs an ISIN map keyed by the 27 ISINs in the fixture, otherwise unmapped rows are skipped and the test reconciliation fails for a different reason. Build the fixture JSON like:

```json
{
  "version": 1,
  "entries": {
    "US67066G1040": {"ticker": "NVDA", "name": "NVIDIA", "status": "mapped"},
    "US24703L2025": {"ticker": "DELL", "name": "Dell Technologies C", "status": "mapped"},
    "...": "..."
  }
}
```

All 27 ISINs marked `status: "mapped"` with reasonable ticker symbols. The exact ticker strings do not affect the share-reconciliation test (the test groups by ISIN or by mapped ticker — pick whichever is more natural). Suggested tickers (any sensible identifier is fine — the test asserts on share counts, not on ticker spelling):

| ISIN | Ticker | Name |
|---|---|---|
| US67066G1040 | NVDA | NVIDIA |
| US24703L2025 | DELL | Dell Technologies C |
| US81762P1021 | NOW | ServiceNow |
| US5951121038 | MU | Micron Technology |
| US5738741041 | MRVL | Marvell Technology |
| US78392B1070 | HXSCL | SK Hynix GDR |
| US1717793095 | CIEN | Ciena Co |
| US50155Q1004 | KD | Kyndryl Holdings |
| US0091581068 | APD | Air Products & Chem |
| US0404132054 | ANET | Arista Networks |
| US11135F1012 | AVGO | Broadcom |
| US00215W1009 | ASX | ASE Technology Holding |
| CA65704Y1079 | NIOB | North American Niobium |
| IE00BFMXXD54 | VUAA.DE | Vanguard S&P 500 Acc |
| IE000QDFFK00 | AXNAS.DE | AXA Nasdaq 100 Acc |
| IE00BMFKG444 | XNAS.DE | Xtrackers Nasdaq 100 Acc |
| IE00B42NKQ00 | IUES.DE | iShares S&P 500 Energy |
| IE00B3WJKG14 | IUIT.DE | iShares S&P 500 IT |
| IE00B8KQN827 | ETN.DE | Eaton |
| JP3721400004 | 5631.T | Japan Steel Works |
| DE0007030009 | RHM.DE | Rheinmetall |
| FR0004038263 | PARRO.PA | Parrot |
| CH1129538448 | POLY.SW | 21Shares Polygon ETP |
| CH1109575535 | XLM.SW | 21Shares Stellar ETP |
| CH0491507486 | TEZS.SW | 21Shares Tezos ETP |
| DE000HT41XN9 | HT41XN9 | HSBC Apple Turbo |
| GB00BNRRF105 | ALGO.L | CoinShares Algorand |

### Assumptions to verify before implementation

- **Assumption 1:** `app/ui/wiring.py::get_import_fx_provider` is only consumed by Scalable CSV import code. Confirm by `grep -r get_import_fx_provider app/` before deletion. If used elsewhere, leave the function in place and remove only its connection to the importer call.
- **Assumption 2:** `RowStatus.FX_UNAVAILABLE` and `RowStatus.NEEDS_CURRENCY_SUPPORT` are not referenced from any UI badge/icon code outside the workbench. Grep both names; if referenced for visual handling, remove those references too.
- **Assumption 3:** `infer_currency_from_ticker` is still used by other parts of the codebase (e.g. manual entry, valuation). Keep the function; only remove the *call sites* in `planner.py` and `importer.py`.
- **Assumption 4:** No test currently relies on the FX-fabrication behaviour. If `tests/unit/adapters/scalable_csv/test_importer.py` has a `test_non_eur_ticker_fx_lookup` test or similar, delete it (its premise is now wrong).

### Sequencing

This is the first ticket in the post-incident cleanup. After this merges:
1. User wipes `data/portfolio.json` manually.
2. User re-imports the CSV via the workbench.
3. User verifies Live Overview shows NVDA = 17.22 shares.

Step 1–3 are part of the PR description's "verification" section, not a code ticket.

Subsequent tickets (do not block this one but follow it):
- TICKET-TAX-1 — TICKER_KIND gap fix and portfolio-wide regression test
- TICKET-UI-1 — Filterable, paginated tables (aggrid)
- TICKET-UI-2 — Live Overview EUR-everywhere + names from isin_map

### Why combined into one ticket

Bugs 1 and 2 touch the same five-to-eight lines in `planner.py` and `importer.py`. The reconciliation test fixture is identical for both. Splitting them would force two PRs to write conflicting diffs against the same lines, and the reconciliation test could not pass until both fixes land. One ticket, one test, one PR.
