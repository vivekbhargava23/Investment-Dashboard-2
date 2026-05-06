# TICKET-010 — Tax engine (Sparerpauschbetrag, Verlustverrechnungstopf, Teilfreistellung, Abgeltungsteuer)

**Status:** IN_REVIEW
**Priority:** P1
**Estimated session length:** 2.5 – 3.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-04)
**Implemented by:** _pending_
**Depends on:** TICKETs 001 (domain models), 002 (FIFO + RealisedGain), 003 (repo), 006 (valuation service). Soft-depends on TICKET-008c (currency correctness) being merged first so the seed data is sane; this ticket is testable independently against fixture data.

> **After this ticket merges, every realised gain in the portfolio has a defensible after-tax number.** The Live Overview's "Sparerpauschbetrag" and "Tax Headroom" KPI tiles stop being hardcoded `€0,00 used of €1,000.00` placeholders and start showing real, computed values. TICKET-011 (Tax Dashboard page) and TICKET-012 (pre-trade sell simulator) consume this engine; both are blocked on this ticket landing.

---

## Problem

We have realised gains (`list[RealisedGain]` from `compute_realised_gains`, TICKET-002) and unrealised gains (`LivePosition.unrealised_gain_eur`, TICKET-006). What we do **not** have is the tax-aware view of those numbers. Specifically:

1. **Sparerpauschbetrag** is a €1,000 / year tax-free allowance for capital gains. The dashboard currently has no concept of "how much of this year's allowance has been consumed."
2. **Verlustverrechnungstopf** is the loss-offset pot. Realised losses in year N reduce taxable gains in year N (and unused losses carry forward). The dashboard currently treats every realised gain as fully taxable.
3. **Aktienverlustverrechnungstopf** is the *separate* loss pot for sales of individual shares (§ 20 Abs. 6 Satz 4 EStG). Losses from selling individual stocks (Aktien) can *only* offset gains from selling individual stocks — not ETF gains, not interest, not dividends. The general loss pot does the rest. The dashboard currently does not distinguish.
4. **Teilfreistellung** is the partial tax exemption for fund shares — 30% for Aktienfonds, 15% for Mischfonds, 60% for inland Immobilienfonds, 80% for foreign Immobilienfonds, 0% for Rentenfonds and individual shares. Applied *before* loss-offsetting and allowance. The dashboard currently does not apply it.
5. **Abgeltungsteuer** is the flat 25% withholding tax (plus 5.5% Solidaritätszuschlag on the tax → effective 26.375% before church tax). The dashboard currently does not compute it.

These five rules combine in a specific order that materially changes the after-tax number. Get the order wrong and a user underestimates their tax bill or misses a loss-harvest opportunity.

This ticket builds the **stateless, pure-Python tax engine** that consumes `RealisedGain`s and unrealised positions and returns a fully-resolved `TaxYearSummary`. The engine knows nothing about UI, persistence, or live prices — those are wired in TICKET-011 (page) and TICKET-012 (simulator).

The engine is **opinionated about its scope**: it implements the rules above for an unmarried private investor (Privatanleger, Einzelveranlagung), no church tax, no foreign-tax-credit (Quellensteueranrechnung), no Vorabpauschale on accumulating ETFs. Each of these omissions is documented as out-of-scope with a follow-up ticket pointer. The methodology rule from TICKET-008c applies: **no "documented approximation" placeholders inside the engine itself** — features are either implemented properly or omitted entirely with a clear out-of-scope note.

---

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-04. Several of them are deliberate departures from how the JS mockup (`Investment_Dashboard.html`) computes tax, because the mockup elides edge cases the engine cannot.

### 1. The tax engine lives in `app/domain/tax/` as a sub-package, not a single file.

Tax has enough internal structure (rules, tax-year aggregator, instrument classifier, ordering pipeline) that a single `tax.py` file would grow past 500 lines and obscure the layering. The sub-package decomposes:

```
app/domain/tax/
  __init__.py                ← public exports
  CLAUDE.md                  ← per-module rules
  rates.py                   ← year-keyed tax-rate constants
  classification.py          ← InstrumentKind enum + classifier
  models.py                  ← TaxLot, TaxYearLedger, TaxYearSummary, TaxImpact
  pipeline.py                ← the apply-rules-in-order function
  engine.py                  ← public entry: compute_tax_year_summary
```

This is a slightly larger surface than `app/domain/fifo.py` (TICKET-002) but the rules genuinely are independent enough to be testable in isolation.

### 2. The engine is *stateless and pure*, like FIFO. Same contract.

Inputs: a year, the user's profile (filing status, church-tax flag), all transactions in the portfolio (engine filters internally), and a `prior_year_carryforward` value. Outputs: an immutable `TaxYearSummary` with every component number broken out. No `datetime.now()`, no `as_of` defaults — the caller supplies the year. Same rule as FIFO and valuation.

### 3. There is **no separate "tax service"** in `app/services/` for this ticket.

The valuation service (TICKET-006) exists because it orchestrates *across ports* (price + FX). The tax engine has zero port dependencies — it is pure computation over already-computed `RealisedGain`s and `Position`s. A service-layer wrapper would be a one-line passthrough that adds no value. If TICKET-011 (page) or TICKET-012 (simulator) later need orchestration that combines the tax engine with live valuation (e.g., "what's my tax bill if I sell everything at current prices"), *that* lives in `app/services/tax_planning.py` — but it's not this ticket.

### 4. The order of rule application is fixed and documented as a "tax pipeline."

The order is not a design choice; it is set by German tax law. Documenting it explicitly and locking it down with tests prevents accidental reordering during refactors.

```
For each fiscal year, in this exact order:

(1) Group realised gains by instrument kind:
    AKTIE | AKTIENFONDS | MISCHFONDS | IMMOBILIENFONDS | IMMOBILIENFONDS_AUSLAND |
    RENTENFONDS | SONSTIGE | DIVIDENDE | ZINSEN

(2) Apply Teilfreistellung per group (reduces both gains AND losses).
    Aktienfonds × 0.70, Mischfonds × 0.85, Immobilien × 0.40, Immobilien_Ausland × 0.20,
    Rentenfonds × 1.00, Aktie × 1.00 (no Teilfreistellung), Sonstige × 1.00.

(3) Net within Verlustverrechnungstöpfe:
    - Aktien-pot: aktien-gains netted against aktien-losses (§20 Abs.6 S.4 EStG).
      Excess loss → carryforward in aktien-pot only. Excess gain → moves to general bucket.
    - General-pot: everything else (fonds, dividends, interest) netted together.
      Excess loss → carryforward in general-pot only. Excess gain → next step.

(4) Apply prior-year carryforward (separately per pot).

(5) Apply Sparerpauschbetrag against the *post-loss-offset* taxable amount, capped at €1,000
    (single) or €2,000 (joint). Allowance consumed reduces by exactly the amount used,
    capped at the available tax-base.

(6) Compute Abgeltungsteuer: taxable_after_allowance × 0.25.

(7) Add Solidaritätszuschlag: abgeltungsteuer × 0.055.

(8) (Out of scope, but the field exists, set to zero) Church tax.

(9) Return the full ledger: every step's input, output, and consumed-amount.
```

Every step is a function in `pipeline.py` that takes a `TaxYearLedger` and returns an updated `TaxYearLedger`. The engine entry point is the composition.

### 5. Instrument classification is a *pure function* keyed off ticker, with an explicit table.

The Teilfreistellung percentage depends on whether the instrument is a stock, an Aktienfonds, a Mischfonds, etc. There is no port for this — it is a hard mapping the user maintains in code. **No silent fallback to "treat as stock"** — if a ticker is unknown to the classifier, the engine raises `InstrumentClassificationError` with the ticker name and a pointer to where to add it. Better to crash than silently miscompute tax.

This mirrors `infer_currency_from_ticker` from TICKET-008c (same shape, same discipline). The single source of truth for "what kind of thing is this ticker" lives in `app/domain/tax/classification.py`.

For the existing seed portfolio:

| Ticker | Classification | Teilfreistellung |
|---|---|---|
| `VUSA.DE` | `AKTIENFONDS` (Vanguard S&P 500 UCITS ETF) | 30% |
| `NVDA`, `RHM.DE`, `MU`, `ANET`, `MRVL`, `APD`, `AVGO`, `ETN`, `ASX`, `5631.T`, `HY9H.F` | `AKTIE` | 0% |

Every ticker in the current seed is classifiable today. New tickers added through TICKET-009-revised that the classifier does not recognise will hit the loud error — and the user adds the row to the table in one line.

### 6. The Sparerpauschbetrag is consumed *across all capital income for the year*.

The engine receives the full year's gains across all pots. After Teilfreistellung and per-pot loss-offsetting, the remaining taxable amounts from the aktien-pot and the general-pot are summed; the allowance applies to that sum. Allowance consumption is reported as a single number, not split across pots. (This matches how Scalable and every other German broker reports it.)

### 7. We model exactly two prior-year carryforward inputs, not historical reconstruction.

The user supplies, for the year being computed:
- `prior_year_aktien_loss_carryforward: Money` (EUR; from the previous year's tax assessment)
- `prior_year_general_loss_carryforward: Money` (EUR; same)

The engine does not "rebuild history" by replaying every prior year's tax computation. Reasons:
- The user's actual carryforward comes from their Steuerbescheid, not the dashboard's reconstruction. Trying to reconstruct it would diverge from what the Finanzamt has on record.
- Years before the dashboard existed have no transaction data anyway.
- If the user wants to populate the field, they look at their last `Steuerbescheid` or `Jahressteuerbescheinigung` and type the number in.

This is a deliberate ergonomic trade — TICKET-011 will surface a single "Carryforward from prior year" input field with a help tooltip explaining where to find the number. **No silent default of zero.** If the user has never entered the value, the dashboard shows "Carryforward: not yet set" rather than "Carryforward: €0" — the same loud-fail discipline as TICKET-008c's currency validator.

### 8. Dividend and interest income are a *separate input channel*, not derived from transactions.

The current `Transaction` model has `BUY` and `SELL` types only (TICKET-001). Dividends and interest are out of scope as transaction types and will be added in a future ticket. For now, the tax engine accepts an optional `dividend_income_eur: Money` and `interest_income_eur: Money` parameter — both default to `Money.zero(EUR)` — that the user could supply via TICKET-011's UI. **They have a clear non-zero default mechanism** (TICKET-011 pulls from Scalable's annual report once that ticket lands), not a silent zero. For this ticket: the parameter exists, defaults to zero, and tests cover the non-zero case so the math is right when TICKET-011 wires it up.

### 9. The engine's output is *non-stateful and stable across reruns*.

`compute_tax_year_summary(year, transactions, profile, carryforward)` is referentially transparent. Same inputs, same output. Re-running it ten times produces the same `TaxYearSummary`. This is the same property valuation has, and the same property the Streamlit cache layer above will rely on (TICKET-011).

---

## Acceptance criteria

### `app/domain/tax/__init__.py` — public exports

- [ ] Re-exports the public surface exactly: `compute_tax_year_summary`, `TaxYearSummary`, `TaxImpact`, `InstrumentKind`, `FilingStatus`, `InstrumentClassificationError`, `classify_instrument`, `TAX_RATES_2026` (and any future-year tables).
- [ ] No re-exports of internal types like `TaxYearLedger` (those are an implementation detail of `pipeline.py`).

### `app/domain/tax/CLAUDE.md` — per-module rules

A short file (~40 lines) covering, with the specific care that recent post-mortems have highlighted:

- The engine is pure: no port imports, no `datetime.now()`, no random, no I/O.
- Adding a tax year requires (a) adding entries to the year-keyed rate tables in `rates.py` and (b) updating `compute_tax_year_summary`'s `year` parameter validation to accept the new year. Both go in one PR with year-specific test fixtures.
- Adding an instrument kind requires (a) extending the `InstrumentKind` enum, (b) adding the Teilfreistellung percentage in `rates.py`, (c) adding mapping rows to `classification.py`, (d) adding tests for the new kind. All four in one PR.
- **Never silent-default an unknown ticker to AKTIE**, even "for convenience." Raise `InstrumentClassificationError`. The tax-rule application order is fixed by German tax law. The order encoded in `pipeline.py` is described above. Reordering is an architectural change requiring an ADR.
- **No "documented approximation" placeholders** in this layer (per METHODOLOGY.md). Either implement a rule properly or omit it with a clear out-of-scope note.

### `app/domain/tax/rates.py` — year-keyed rate constants

- [ ] One module-level dict per fiscal year. Year 2026 gets `TAX_RATES_2026: TaxYearRates`. Year 2025 (for backfill of last year's transactions) gets `TAX_RATES_2025: TaxYearRates`. These two are the minimum for the seed data.

- [ ] `TaxYearRates` is a frozen Pydantic model with fields:
  - `sparerpauschbetrag_single: Money` — `Money(Decimal("1000"), EUR)` for both 2025 and 2026 (rate has been unchanged since 2023)
  - `sparerpauschbetrag_joint: Money` — `Money(Decimal("2000"), EUR)` for both
  - `abgeltungsteuer_rate: Decimal` — `Decimal("0.25")` (25%)
  - `solidaritaetszuschlag_rate: Decimal` — `Decimal("0.055")` (5.5% **of the tax**, not of the income)
  - `teilfreistellung: dict[InstrumentKind, Decimal]` — see §6 below.

- [ ] `RATES_BY_YEAR: dict[int, TaxYearRates] = {2025: TAX_RATES_2025, 2026: TAX_RATES_2026}`. The engine does `RATES_BY_YEAR[year]` and raises `UnsupportedTaxYearError` (clear message: "Tax year {year} is not configured. Add it to app/domain/tax/rates.py.") for unknown years. No silent fallback to "the most recent year I know about."

- [ ] Reference comment block above the constants: legal source for each value (StG section reference, link to gesetze-im-internet.de). This is documentation for future AI sessions verifying the numbers when laws change.

- [ ] `teilfreistellung` dict values (private investor, Privatvermögen):
  - `AKTIE: Decimal("0.00")`
  - `AKTIENFONDS: Decimal("0.30")`
  - `MISCHFONDS: Decimal("0.15")`
  - `IMMOBILIENFONDS: Decimal("0.60")`
  - `IMMOBILIENFONDS_AUSLAND: Decimal("0.80")`
  - `RENTENFONDS: Decimal("0.00")`
  - `SONSTIGE: Decimal("0.00")`
  - `DIVIDENDE: Decimal("0.00")` — dividends from individual shares; Teilfreistellung does not apply (it applies to fund-level dividends only, which are wrapped into AKTIENFONDS gain accounting)
  - `ZINSEN: Decimal("0.00")`

### `app/domain/tax/classification.py` — instrument kind + classifier

- [ ] `InstrumentKind(str, Enum)` with members exactly as listed above.

- [ ] `InstrumentClassificationError(Exception)` with a message format: `"Ticker '{ticker}' has no instrument-kind classification. Add it to TICKER_KIND in app/domain/tax/classification.py."`

- [ ] Module-level `TICKER_KIND: dict[str, InstrumentKind]` — explicit mapping, one row per ticker present in the current seed. Comment block above it explaining: this is the single source of truth; adding a row is the only way to extend.

  Initial contents (mirroring the seed CSV):

  ```python
  TICKER_KIND: dict[str, InstrumentKind] = {
      # ETFs (Aktienfonds — UCITS-compliant equity funds)
      "VUSA.DE": InstrumentKind.AKTIENFONDS,

      # Individual shares (Aktien — direct equity)
      "NVDA": InstrumentKind.AKTIE,
      "RHM.DE": InstrumentKind.AKTIE,
      "MU": InstrumentKind.AKTIE,
      "ANET": InstrumentKind.AKTIE,
      "MRVL": InstrumentKind.AKTIE,
      "APD": InstrumentKind.AKTIE,
      "AVGO": InstrumentKind.AKTIE,
      "ETN": InstrumentKind.AKTIE,
      "ASX": InstrumentKind.AKTIE,
      "5631.T": InstrumentKind.AKTIE,
      "HY9H.F": InstrumentKind.AKTIE,
  }
  ```

- [ ] `classify_instrument(ticker: str) -> InstrumentKind`:
  - Uppercase-normalise the ticker first.
  - Look up in `TICKER_KIND`. If not found, raise `InstrumentClassificationError`.
  - **No fallback heuristic** ("if it ends in `.DE` it's probably an Aktienfonds"). Heuristics are exactly the kind of silent assumption TICKET-008c was a post-mortem of.

- [ ] Type-annotated, mypy strict-clean.

### `app/domain/tax/models.py` — domain types

- [ ] `FilingStatus(str, Enum)`: `SINGLE = "single"`, `JOINT = "joint"`. (Married-but-separate is treated as `SINGLE` — the joint allowance only applies to actual joint filing. We do not model the more exotic German filing variants.)

- [ ] `TaxProfile` — frozen Pydantic model:
  - `filing_status: FilingStatus`
  - `church_tax_rate: Decimal = Decimal("0")` — placeholder, not yet applied (out of scope; the field exists so the public API does not change when it lands)

- [ ] `TaxImpact` — frozen Pydantic model. The fully-itemised "what tax does this gain produce" record. One field per pipeline step:
  - `instrument_kind: InstrumentKind`
  - `gross_gain_eur: Money` — pre-Teilfreistellung
  - `teilfreistellung_pct: Decimal` — the percentage applied (e.g., `Decimal("0.30")` for AKTIENFONDS)
  - `teilfreistellung_amount_eur: Money` — the amount excluded from tax (signed: positive for gains, negative for losses, since Teilfreistellung applies symmetrically)
  - `taxable_gain_after_teilfreistellung_eur: Money` — gross_gain × (1 − teilfreistellung_pct)
  - **Class validator**: `taxable_gain_after_teilfreistellung_eur == gross_gain_eur - teilfreistellung_amount_eur` within 0.01 EUR tolerance.
  - This is per-`RealisedGain`. The pipeline produces one `TaxImpact` per input `RealisedGain`.

- [ ] `LossPotState` — frozen Pydantic model. Tracks one of the two pots:
  - `prior_year_carryforward_eur: Money`
  - `current_year_losses_eur: Money` — sum of negative `taxable_gain_after_teilfreistellung_eur`'s for this pot's instrument kinds, expressed as a *positive* number
  - `current_year_gains_eur: Money` — sum of positive ones
  - `consumed_against_gains_eur: Money` — how much of (carryforward + current losses) was used against current gains
  - `remaining_carryforward_eur: Money` — what carries to next year
  - `taxable_after_offset_eur: Money` — current_year_gains − consumed_against_gains; never negative

- [ ] `TaxYearSummary` — frozen Pydantic model. The final output of the engine:
  - `year: int`
  - `profile: TaxProfile`
  - `aktien_pot: LossPotState`
  - `general_pot: LossPotState`
  - `realised_gain_impacts: tuple[TaxImpact, ...]` — the per-RealisedGain breakdown, in chronological order
  - `additional_dividend_income_eur: Money` — what the user supplied
  - `additional_interest_income_eur: Money` — what the user supplied
  - `total_taxable_after_loss_offset_eur: Money` — sum of both pots' `taxable_after_offset_eur` plus dividends and interest
  - `sparerpauschbetrag_total_eur: Money` — €1,000 or €2,000 depending on filing status
  - `sparerpauschbetrag_consumed_eur: Money` — capped at total_taxable; never exceeds total
  - `sparerpauschbetrag_remaining_eur: Money` — total − consumed
  - `taxable_after_allowance_eur: Money` — total_taxable − consumed
  - `abgeltungsteuer_eur: Money` — taxable_after_allowance × 0.25
  - `solidaritaetszuschlag_eur: Money` — abgeltungsteuer × 0.055
  - `church_tax_eur: Money` — `Money.zero(EUR)` for v1
  - `total_tax_owed_eur: Money` — sum of the three tax lines
  - `effective_tax_rate_pct: Decimal | None` — total_tax / gross_realised_gain × 100; `None` if gross_realised_gain ≤ 0
  - **Class validator**: `taxable_after_allowance_eur >= 0` (the engine never produces a negative taxable amount; that becomes carryforward).

### `app/domain/tax/pipeline.py` — the rule pipeline

- [ ] Internal mutable type `TaxYearLedger` (NOT exported). A dataclass that the pipeline functions hand to each other. Holds intermediate state between steps.

- [ ] One pure function per pipeline step. Each takes a `TaxYearLedger` and returns a new `TaxYearLedger`. Names:
  - `_classify_and_apply_teilfreistellung(ledger: TaxYearLedger) -> TaxYearLedger`
  - `_split_into_pots(ledger: TaxYearLedger) -> TaxYearLedger`
  - `_apply_within_year_offset(ledger: TaxYearLedger) -> TaxYearLedger`
  - `_apply_carryforward(ledger: TaxYearLedger) -> TaxYearLedger`
  - `_apply_sparerpauschbetrag(ledger: TaxYearLedger) -> TaxYearLedger`
  - `_compute_abgeltungsteuer(ledger: TaxYearLedger) -> TaxYearLedger`
  - `_compute_soli(ledger: TaxYearLedger) -> TaxYearLedger`
  - `_finalise(ledger: TaxYearLedger) -> TaxYearSummary`

- [ ] No step depends on more than the ledger; no globals; no imports of `app.domain.fifo` etc. (the `RealisedGain` list is already inside the ledger before the pipeline starts).

- [ ] `_apply_within_year_offset` correctly implements the **§ 20 Abs. 6 Satz 4 EStG** rule: aktien-pot losses can only offset aktien-pot gains; the general pot offsets across funds, dividends, interest. After this step, each pot has either zero gain or zero loss — never both. Excess loss in either pot stays in that pot's carryforward bucket. Excess gain goes through to the allowance step.

- [ ] `_apply_sparerpauschbetrag` consumption is capped at the available taxable amount. If the user has €600 of taxable gain and a €1,000 allowance, allowance_consumed = €600, remaining = €400 (not €1,000-€0=€1,000). This is the bug-prone spot.

### `app/domain/tax/engine.py` — public entry point

- [ ] `compute_tax_year_summary(year: int, transactions: Sequence[Transaction], profile: TaxProfile, prior_year_aktien_carryforward_eur: Money = Money.zero(EUR), prior_year_general_carryforward_eur: Money = Money.zero(EUR), additional_dividend_income_eur: Money = Money.zero(EUR), additional_interest_income_eur: Money = Money.zero(EUR)) -> TaxYearSummary`.

- [ ] Steps:
  1. Validate `year in RATES_BY_YEAR`. Raise `UnsupportedTaxYearError` otherwise.
  2. Validate all four `Money` parameters are EUR. Raise `CurrencyMismatchError` otherwise.
  3. Call `compute_realised_gains(transactions)` from FIFO (TICKET-002). Filter to `gain.sell_date.year == year`.
  4. Build the initial `TaxYearLedger` with the filtered gains, the user's profile, the rate table, and the carryforwards.
  5. Run the pipeline (compose the seven internal functions in order).
  6. Return the resulting `TaxYearSummary`.

- [ ] **The function is pure**: no `datetime.now()`, no random, no I/O. Same input → same output. (Test below verifies this.)

- [ ] Raises `InstrumentClassificationError` (from step 1 of the pipeline) propagated up unchanged if any RealisedGain's ticker is unclassified.

### `app/domain/__init__.py` — extend public exports

- [ ] Re-export from `app.domain.tax`: the same six names the sub-package re-exports. So that `from app.domain import compute_tax_year_summary` works alongside `from app.domain import compute_positions`.

### Tests

All tests are unit tests in `tests/unit/domain/tax/`. Zero I/O. Fast.

#### `tests/unit/domain/tax/__init__.py`

- [ ] Empty.

#### `tests/unit/domain/tax/test_rates.py`

- [ ] **2026 sparerpauschbetrag values**: assert single = €1,000 and joint = €2,000.
- [ ] **Soli rate is 5.5%**: regression — accidental change to 0.055 vs 5.5 vs 0.0055 has bitten German tax software before.
- [ ] **Teilfreistellung percentages**: each kind matches the spec table above. Three explicit asserts.
- [ ] **Unknown year raises**: `RATES_BY_YEAR[2099]` → `KeyError`. Engine wraps this in `UnsupportedTaxYearError` (tested below).

#### `tests/unit/domain/tax/test_classification.py`

- [ ] **Every seed-portfolio ticker classifies**: a parametrized test over the 12 tickers in `TICKER_KIND` confirms `classify_instrument(ticker)` returns the expected kind.
- [ ] **Unknown ticker raises with helpful message**: `classify_instrument("FOO.BAR")` → `InstrumentClassificationError` whose message contains both `"FOO.BAR"` and `"app/domain/tax/classification.py"`.
- [ ] **Lowercase input is normalized**: `classify_instrument("nvda") == InstrumentKind.AKTIE`.
- [ ] **No silent fallback**: explicitly assert that an unknown `.DE` ticker raises (negative-test the kind of heuristic this ticket bans).

#### `tests/unit/domain/tax/test_pipeline.py`

These are unit tests on the internal pipeline functions. They use a small `_make_ledger(...)` test helper.

- [ ] **Teilfreistellung: 30% of a €1000 ETF gain becomes €300 exempt, €700 taxable**: exact arithmetic.
- [ ] **Teilfreistellung applies symmetrically to losses**: a €100 ETF loss becomes €70 deductible loss (€30 of the loss is "exempt" — i.e., not deductible). This is a frequent misunderstanding worth its own test.
- [ ] **Aktien-pot does not absorb general-pot losses**: 1 aktien gain of €100, 1 ETF (after Teilfreistellung €70) loss of €70 → aktien_taxable = €100, general_taxable = -€70 → offset stops there → general_pot.remaining_carryforward = €70 (loss survives), aktien_pot.taxable = €100 (cannot be reduced). This is the §20 Abs.6 S.4 firewall.
- [ ] **General-pot DOES absorb across kinds**: ETF gain €100 + dividend €50 - bond loss €30 → general_taxable = €120. (All in general pot; cross-kind netting is fine within general.)
- [ ] **Carryforward from prior year**: aktien gain €500 this year, prior_year_aktien_carryforward €700 → aktien_taxable = 0, remaining_carryforward = €200. Prior carryforward is consumed first; current-year losses (none here) would also stack.
- [ ] **Sparerpauschbetrag is capped at the taxable amount**: €600 taxable, €1000 allowance → consumed = €600, remaining = €400. Not "consumed = €1000."
- [ ] **Sparerpauschbetrag consumes from the combined post-offset pots**: €400 taxable in aktien + €300 taxable in general = €700 total → consumed = €700, remaining = €300. The split between pots does not matter for allowance consumption (a frequent confusion).
- [ ] **Joint filing doubles the allowance**: same input as the cap-test, profile=JOINT, allowance = €2000.
- [ ] **Abgeltungsteuer = 25%**: €1000 taxable → tax = €250.
- [ ] **Soli = 5.5% of tax** (not 5.5% of taxable!): €250 tax → soli = €13.75.
- [ ] **Effective rate**: €1000 gross, total tax €263.75 → effective rate = 26.375%.

#### `tests/unit/domain/tax/test_engine_end_to_end.py`

- [ ] **The seed portfolio's 2026 ETN sells produce the right tax bill**:
  Input: the seed portfolio's ETN buy (5 shares @ $320, FX 0.93) and the two 2026 sells (1 share @ $340 FX 0.918, 1 share @ $355 FX 0.92), profile=SINGLE, no carryforward.
  Expected:
  - 2 RealisedGain records in 2026, both AKTIE, both positive
  - aktien_pot.current_year_gains = sum of the two
  - aktien_pot.taxable_after_offset = same (no losses)
  - sparerpauschbetrag_consumed = the smaller of allowance and gain
  - tax = (taxable_after_allowance × 0.25 × 1.055)
  - All numbers asserted to ± €0.01.
- [ ] **An empty year produces a zero summary, never `None` and never raise**: year 2024 with no transactions in 2024 → summary with all zeros, and `effective_tax_rate_pct = None` (cost basis zero protection). Critical regression for empty-portfolio rendering.
- [ ] **An unclassified ticker propagates `InstrumentClassificationError`**: synthesise a `Transaction` with ticker "ZZZZ" (unclassified). Engine raises with a message naming the ticker.
- [ ] **An unsupported year raises `UnsupportedTaxYearError`**: `compute_tax_year_summary(2099, [], TaxProfile(SINGLE))` → clear error.
- [ ] **Determinism / purity**: call `compute_tax_year_summary` twice with the same inputs (where one input list is the same list shuffled). Both calls produce equal `TaxYearSummary`s. (FIFO already guarantees this; this test ensures the tax engine doesn't introduce non-determinism via dict iteration.)
- [ ] **Negative path: dividend income flows through**: same seed portfolio + `additional_dividend_income_eur=Money(Decimal("250"), EUR)`. Verify the dividend is added to the general-pot gains (after €0 Teilfreistellung) and the final tax bill increases by exactly the right amount.

#### `tests/unit/domain/tax/test_known_scenarios.py` — worked examples from German tax authority guidance

These tests assert against numbers from the BVI / NRW tax authority worked examples cited in the chat, so a future change to the engine that breaks them is a clear flag.

- [ ] **BVI Aktienfonds dividend example** (BVI worked example): €1000 fund distribution, 30% Teilfreistellung → €700 taxable. Plug into the engine as a single AKTIENFONDS gain; verify `taxable_gain_after_teilfreistellung_eur == €700`.
- [ ] **NRW Aktienfonds example**: same setup, slightly different number from the NRW Finanzamt page. Use a fresh fixture file (`tests/fixtures/tax/nrw_aktienfonds_2024.json`) — committed — to make the source clear and the test legible.
- [ ] **Loss-pot firewall worked example**: aktien gain €1500 + ETF loss (post-Teilfreistellung) €1000 → aktien remains €1500, ETF carryforward = €1000 (general pot). Allowance applies to €1500 → €500 taxable → tax €125 + Soli €6.875.

### Lints / quality

- [ ] `pytest` — all tests pass (existing + new). Target: ~30+ new tests in `tests/unit/domain/tax/`.
- [ ] `ruff check .` — passes.
- [ ] `mypy app/` — passes; **strict mode on `app/domain/tax/`** (per existing strict rule for `app/domain/`).
- [ ] `lint-imports` — passes; specifically:
  - `app.domain.tax` may import from `app.domain.money`, `app.domain.models`, `app.domain.realised_gain`, `app.domain.fifo`, `app.domain.positions`. Stdlib only beyond that.
  - `app.domain.tax` does NOT import from `app.services`, `app.adapters`, `app.ports`, `app.ui`, `streamlit`, `requests`, `yfinance`. (Same purity rule the rest of `app/domain/` follows.)

### State updates (per CLAUDE.md session-end ritual)

- [ ] `docs/SESSION_LOG.md` appended.
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-010 → IN_REVIEW; "Done" gains TICKET-008c if it is in the same merge window).
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-010 row → IN_REVIEW).
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.

---

## Files created

```
app/domain/tax/__init__.py
app/domain/tax/CLAUDE.md
app/domain/tax/rates.py
app/domain/tax/classification.py
app/domain/tax/models.py
app/domain/tax/pipeline.py
app/domain/tax/engine.py
tests/unit/domain/tax/__init__.py
tests/unit/domain/tax/test_rates.py
tests/unit/domain/tax/test_classification.py
tests/unit/domain/tax/test_pipeline.py
tests/unit/domain/tax/test_engine_end_to_end.py
tests/unit/domain/tax/test_known_scenarios.py
tests/fixtures/tax/nrw_aktienfonds_2024.json
```

## Files modified

```
app/domain/__init__.py                ← re-export tax public API
docs/TICKETS/BACKLOG.md               ← TICKET-010 row → IN_REVIEW
```

## Files NOT to modify

Same discipline as TICKET-008b's "files NOT to modify" — protects against scope creep:

- `app/domain/fifo.py` — engine consumes FIFO output unchanged.
- `app/domain/realised_gain.py` — model is the contract; do not extend it for tax-specific fields.
- `app/domain/models.py` and `app/domain/money.py` — no domain-model changes belong in this ticket; if a tax computation needs a new field, that is a separate ticket.
- `app/services/valuation.py` — service layer changes are out of scope.
- `app/ui/*` — no UI changes in this ticket. TICKET-011 is the page.

If during implementation a different file *seems* to need changes, **stop and flag it in the PR description.** Do not silently expand scope.

---

## Out of scope (and why)

- **Vorabpauschale** (annual deemed-distribution tax on accumulating ETFs, § 18 InvStG). This is a real liability for the portfolio's `VUSA.DE` holding, but computing it correctly requires the year-start fund value, the year-end fund value, the Bundesbank-published `Basiszins` for the year, and a treatment of partial-year holdings. **Future ticket TICKET-010b — Vorabpauschale.** The math is well-defined; we just are not doing it in this ticket. The engine produces a `TaxYearSummary` that does not include vorabpauschale, and the UI in TICKET-011 will show a clearly-flagged "Vorabpauschale: not computed (TICKET-010b)" line so the user knows their tax bill is *under-estimated* for accumulating ETFs.
- **Foreign withholding tax credit (Quellensteueranrechnung)**. US dividends taxed at source can be partially credited against German Abgeltungsteuer (typically 15% of 15% = 2.25 percentage points). Not modelled. Future ticket.
- **Church tax (Kirchensteuer)**. The `church_tax_rate` field exists on `TaxProfile` and the `church_tax_eur` field exists on `TaxYearSummary` so the public shape does not break when this lands. The engine sets `church_tax_eur = Money.zero(EUR)` regardless. Future ticket.
- **Joint filing (Ehegattensplitting) for Sparerpauschbetrag specifically.** The engine doubles the allowance for `FilingStatus.JOINT`, which is correct for capital gains. The full income-tax `Ehegattensplitting` calculation is out of scope (no income tax computation in this dashboard at all).
- **Reconstructing prior-year carryforwards from full transaction history.** The user supplies the carryforward as an explicit input.
- **Vor-2009 bestandsgeschützte Altanteile** (special tax treatment for fund shares purchased before 2009 with the €100,000 lifetime exemption). Not modelled — the user has no pre-2009 holdings. If a user with such holdings ever arrives, they are flagged for ticket triage rather than silently miscomputed.
- **Dividend income at the transaction level.** Currently a flat scalar input to `compute_tax_year_summary`. Adding a `DIVIDEND` `TransactionType` is a future ticket that touches FIFO and the repo. The flat-scalar input is the bridge until then.
- **Per-lot identification for tax reporting** (e.g., "this sell consumed lot X with cost basis Y on date Z"). The data is already in `RealisedGain`; the *aggregation* is what the tax engine does. UI surfacing of per-lot tax detail is TICKET-011.
- **Tax-loss harvesting recommendations** ("you have €300 of unrealised losses you could realise to offset gains"). That is TICKET-012 (pre-trade simulator).
- **Wash-sale rules** — Germany has no equivalent of the US wash-sale rule for individual stocks (it has the very narrow §20 Abs. 4a EStG for very-close-to-identical securities, which we do not need for the seed portfolio). Not modelled. If it ever matters, the relevant gains would just be flagged for manual review.

---

## Test cases (selected, illustrative)

In addition to the test list above, the **acceptance gate** is that this end-to-end scenario produces the expected number, asserted to ± €0.01:

**Scenario:** Vivek's actual 2026 realised gains (per seed CSV at the start of TICKET-010 implementation):

| Sell Tx | Ticker | Sell Date | Shares | Proceeds EUR | Cost Basis EUR | Realised Gain EUR | Kind |
|---|---|---|---|---|---|---|---|
| 1 | ETN | 2026-03-12 | 1 | 312.12 | 297.60 | +14.52 | AKTIE |
| 2 | ETN | 2026-05-01 | 1 | 326.60 | 297.60 | +29.00 | AKTIE |
| 3 | HY9H.F | 2026-01-02 | 1 | 165.00 | 178.50 | -13.50 | AKTIE |

Total aktien gain = €43.52, aktien loss = €13.50 → aktien_pot.taxable_after_offset = €30.02.
Allowance €1,000 covers it entirely. Sparerpauschbetrag consumed = €30.02. Remaining = €969.98.
**Total tax owed: €0.00.**

(The actual numbers will move slightly with whatever values the migrated `data/portfolio.json` ends up with after TICKET-008c. The test should be written against a deterministic fixture that does not move, not against `data/portfolio.json` directly.)

The corresponding test asserts each ledger field matches, then asserts the bottom-line `total_tax_owed_eur == Money(Decimal("0.00"), EUR)`. If a future refactor accidentally drops the carryforward step or applies Soli to taxable instead of to tax, this test fails loudly.

---

## Notes (architectural and methodological — for future AI sessions)

### Why no Vorabpauschale in v1

It is the most-asked-for tax feature for German private investors with accumulating ETFs, and `VUSA.DE` is exactly that. So why omit it?

- The math depends on the Bundesbank's annual `Basiszins` (2026: 3.20%; 2025: 2.53%; 2024: 2.55%), which is a fact-of-the-world the engine has to know. That is a port — `BasiszinsProvider` — not a constant. Adding a port + adapter + cache + tests is its own ticket.
- The math also depends on year-start fund value, which historically was easy ("look at portfolio.json on Jan 1") but only if the user actually had a Jan 1 snapshot. Implementing Vorabpauschale without snapshot infrastructure means the user has to type the year-start NAV in by hand for every accumulating fund — bad UX.
- Doing it half-right (e.g., default Basiszins to a hardcoded value) reproduces exactly the "documented approximation" anti-pattern from the seed CSV's 5631.T row that bit us in TICKET-008c. Better to omit cleanly with a visible "not computed" flag.

The follow-up TICKET-010b drafts the Basiszins port and the snapshot infrastructure together.

### Why a sub-package and not one file

`app/domain/fifo.py` is one file (TICKET-002) and that was right. The tax engine has more independent moving parts: rates, classification, models, pipeline, public entry. One file would mix concerns and make code review harder. The sub-package's per-file scope is small and each file has a clear single responsibility.

### Why the pipeline functions don't return a final answer until `_finalise`

The pipeline is structured so that the order of step composition is the only way the rules can be applied. If `_apply_sparerpauschbetrag` were a public function, somebody could call it before `_apply_within_year_offset` and get a wrong number. Keeping the steps internal and only exposing `compute_tax_year_summary` enforces order at the type system level (the steps don't return a `TaxYearSummary`; only `_finalise` does).

### Why instrument classification crashes on unknown tickers

This is the same lesson as TICKET-008c (and the same shape of solution): German tax depends critically on whether something is an Aktie, an Aktienfonds, or a Mischfonds. A silent default of "treat as Aktie" would produce a tax answer that is *plausible* (no Teilfreistellung is a rounding for AKTIE so it would not error), and *wrong by 30% of the gain* for any ETF the classifier did not know about. That is exactly the silent-corruption pattern METHODOLOGY.md banned. The fix is the same: crash loudly, force the user to add one line.

### Why no `as_of` parameter

The tax engine computes a calendar-year tax bill. The year is the "as of." There is no notion of "tax bill as of mid-year" because the Sparerpauschbetrag and the loss pots are calendar-year-anchored constructs. If the user wants a "year-to-date" view (TICKET-011's KPIs), the page filters the input transactions before calling the engine; the engine itself is whole-year.

### Why dividend/interest are scalar inputs and not synthetic transactions

We could fake them as `Transaction(type=DIVIDEND, ...)` and feed them through FIFO, but that would (a) require a domain-layer change just to support tax aggregation, and (b) commingle tax-only data into the book of record. The cleaner separation is: tax engine consumes `RealisedGain`s for capital gains and additionally consumes scalar income for dividends + interest. When the dashboard eventually models dividends as proper transactions, the tax engine will sum them inside its boundary and the public scalar inputs become "additional non-Transaction-modelled income, e.g., from external accounts." The signature stays the same.

### Why this ticket is P1, not P0

Live Overview shows hardcoded €0 values for the two tax tiles. That is wrong but not *misleading* — anyone looking at it can see it is a placeholder. A wrong-but-plausible computed value would be misleading. So the dashboard is "honestly missing" rather than "lying," which is the better state to ship in until this ticket lands.

The thing that made TICKET-008c P0 was that the dashboard was *displaying a wrong number that looked right*. None of the current tax tiles do that; they all show their placeholder status (`€0,00 used of €1.000,00` is unmistakably "not yet wired"). So P1 is the right priority — we should build this soon, but the dashboard is not actively misleading anyone in the meantime.

---

## Appendix: Bench-test findings (2026-05-04)

Review of real-world Scalable Capital monthly statements surfaced several requirements that broaden the scope of the data model upstream of the tax engine (though the engine's core math logic remains unchanged):

1. **Tax withholding vs. Year-end filing**: Scalable statements show tax withholding (Abgeltungsteuer + Soli) or refunds *per-trade*. The dashboard needs to track "tax already withheld by broker" to show a "remaining tax liability / refund due" view, alongside the theoretical "as-filed" bill.
2. **New Transaction Types**: Real statements include five types currently unmodelled:
   - `DIVIDEND`: Dividend payments.
   - `INTEREST`: Interest income (e.g., from cash balances).
   - `WITHHOLDING_TAX_FOREIGN`: e.g., US withholding tax on dividends.
   - `TAX_CAPITAL_GAINS_DEDUCTED`: Abgeltungsteuer withheld by broker.
   - `TAX_SOLI_DEDUCTED`: Solidarity surcharge withheld by broker.
3. **CAD Support**: Real holdings include CAD-priced tickers (e.g., Niobium, ISIN CA65704Y1079). The `Currency` enum and `TickerResolver` must support CAD to prevent "unknown currency" crashes.

These findings are documented here to ensure that when TICKET-010 is implemented, the `TaxYearSummary` and `TaxImpact` models include fields for "withheld" amounts, and the upstream data migration (TICKET-008c) and resolver (TICKET-020) are aware of the CAD requirement.
