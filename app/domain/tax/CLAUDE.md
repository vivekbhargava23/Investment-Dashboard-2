# app/domain/tax/CLAUDE.md

Pure domain tax engine. Zero I/O. Zero port imports. Same purity contract as the rest of app/domain/.

## Hard rules

- No `requests`, `httpx`, `urllib`, or any network I/O.
- No file I/O (`open`, `Path.read_*`, `json.load`).
- No `streamlit`, no `pandas`.
- No `datetime.now()` — the caller supplies the `year` integer.
- All money: `Decimal`, never `float`. Use the `Money` value object.
- All Pydantic models: `frozen=True` where applicable.

## What lives where

- `rates.py` — year-keyed tax-rate constants (`TaxYearRates`, `RATES_BY_YEAR`).
- `classification.py` — `InstrumentKind` enum and `TICKER_KIND` table.
- `models.py` — public output types (`TaxImpact`, `LossPotState`, `TaxYearSummary`, `TaxProfile`, `FilingStatus`).
- `pipeline.py` — internal `TaxYearLedger` dataclass and the ordered pipeline steps.
- `engine.py` — public entry point `compute_tax_year_summary`.

## Adding a new tax year

1. Add `TAX_RATES_<YEAR>: TaxYearRates` in `rates.py`.
2. Add the year to `RATES_BY_YEAR`.
3. Add year-specific test fixtures in `tests/unit/domain/tax/`.
All three changes go in one PR.

## Adding a new instrument kind

1. Extend `InstrumentKind` enum in `classification.py`.
2. Add the Teilfreistellung percentage in the `teilfreistellung` dict of each year's `TaxYearRates` in `rates.py`.
3. Add mapping rows to `TICKER_KIND` in `classification.py`.
4. Add tests in `tests/unit/domain/tax/test_classification.py`.
All four changes go in one PR.

## Never silent-default an unknown ticker to AKTIE

`classify_instrument` raises `InstrumentClassificationError` for unknown tickers.
A silent default of AKTIE would silently miscompute tax by the full Teilfreistellung
percentage (up to 30% of the gain). Loud failure forces the right fix.

## The pipeline order is law

The order in `pipeline.py` is set by German tax law (§ 20 EStG, InvStG). Reordering
requires an ADR. Do not refactor the composition order without one.

## No documented-approximation placeholders

Per METHODOLOGY.md: either implement a rule correctly or omit it with an explicit
out-of-scope note. Do not add "use X as approximation; Y not supported v1" comments.
