# ADR-006 — Instrument classification is user-editable data, not source code

**Status:** Proposed
**Date:** 2026-05-31
**Drafted by:** Vivek + Claude (Cowork session 2026-05-31)
**Supersedes / amends:** Extends the classification rules in `app/domain/tax/CLAUDE.md`

---

## Context

Before CSV import, every ticker in the dashboard was hand-seeded by Vivek. The set was small (~11 tickers) and stable. `TICKER_KIND: dict[str, InstrumentKind]` in `app/domain/tax/classification.py` was therefore a hardcoded source-code dict: adding a ticker meant a code change, a PR, and a merge. Loud failure for an unknown ticker (`InstrumentClassificationError`) was a feature — it forced the right fix.

After TICKET-CSV-* shipped, transactions arrive via Scalable CSV import. The Mappings page (`app/ui/pages/mappings.py`) lets the user assign ISIN → ticker through the UI. New tickers (DELL, CIEN, KD, etc.) land in `data/isin_map.json` via that flow, but **never reach `TICKER_KIND`**. The result, observed in the running app on 2026-05-31:

- Tax page: *"Could not compute tax summary: Ticker 'DELL' has no instrument-kind classification."*
- Sell Simulator: *"Simulation error: Ticker 'DELL' has no instrument-kind classification."*

A single unclassified ticker aborts the whole tax pipeline, because `_classify_and_apply_teilfreistellung` (`tax/pipeline.py:91`) calls `classify_instrument(gain.ticker)` for every realised gain in a loop with no fallback.

The "code as source of truth" pattern is incompatible with the "data arrives from CSV" workflow. Every new holding becomes a code change. That is exactly what the CSV-import work was supposed to remove.

## Decision

**Instrument classification moves from source code to user-editable data, stored alongside the ISIN mapping. The loud-failure semantic is preserved — but the user can fix the failure from the Mappings UI in 5 seconds instead of opening a PR.**

### What changes

1. `IsinMapping` (`app/domain/isin_map.py`) gains a new field:
   ```python
   instrument_kind: InstrumentKind | None = None
   ```
   `None` means "unclassified" and behaves the same as today's missing-ticker case (loud failure on tax compute).

2. `classify_instrument(ticker)` reads from the loaded `IsinMapDocument`, not from a hardcoded dict. The function signature changes:
   ```python
   def classify_instrument(ticker: str, isin_map: IsinMapDocument) -> InstrumentKind
   ```
   It looks up the entry whose `ticker == ticker`, returns `entry.instrument_kind`, raises `InstrumentClassificationError` if `instrument_kind is None`.

3. The Mappings page gains a "Tax kind" dropdown next to the ticker picker. Default value: auto-suggested from `CompanyData.quote_type` (EQUITY → AKTIE, ETF → AKTIENFONDS, MUTUALFUND → MISCHFONDS) but **never silently applied** — the user must explicitly pick before Save is enabled. This preserves the "no silent defaults" rule from ADR-005.

4. The existing `TICKER_KIND` hardcoded dict is removed. The 11 entries are migrated into `isin_map.json` via a one-shot script (`tools/migrate_classification_to_isin_map.py`).

### What doesn't change

- `InstrumentKind` enum stays in `app/domain/tax/classification.py` (it's domain-pure; no I/O).
- `classify_instrument` stays pure (it accepts the loaded document as a parameter — no file I/O inside the domain).
- The pipeline order, Teilfreistellung percentages, Sparerpauschbetrag mechanics — all unchanged.
- Loud failure semantics — unchanged. The Mappings page just makes the fix one click instead of one PR.

## Reasoning

1. **Source of truth follows the data flow.** Tickers enter the system via CSV import → Mappings UI. Classification should sit at the same boundary, not three layers deeper in source code.
2. **The "code = source of truth" pattern depended on a hand-curated ticker set.** That set no longer exists. CSV import broke the assumption.
3. **No silent defaults.** A naive fix ("default unknown tickers to AKTIE") would silently miscompute tax by up to 30%. We keep `app/domain/tax/CLAUDE.md`'s "Never silent-default" rule. The dropdown just makes the user the decider, not the source code.
4. **Auto-suggestion is safe because it isn't auto-applied.** `quote_type` from yfinance gives us a high-confidence guess, but Save stays disabled until the user confirms.
5. **The Mappings page is already the right place.** It's where the user maps ISIN → ticker. Adding "and tax kind" is a natural extension, not a new page.

## Consequences

- **Pro:** New tickers from CSV are classified through the UI; no code change required.
- **Pro:** Pipeline failure message becomes actionable ("Open Mappings → set tax kind for DELL") instead of "edit source code".
- **Pro:** `app/domain/tax/classification.py` shrinks; `TICKER_KIND` dict disappears.
- **Pro:** ETFs and exotic instruments (REITs, bond funds) get first-class user control instead of needing a code update for each one.
- **Con:** `classify_instrument` gains a parameter (`isin_map`). Callers need to pass it. Acceptable: it stays pure and explicit.
- **Con:** Migration script needed to seed existing 11 tickers into `isin_map.json`. One-shot, low risk.
- **Con:** Auto-suggestion ties the Mappings UI to the company-data provider for a hint. The hint is optional — if the provider fails, the dropdown still works.

## Reversal cost

If we ever want classification back in code: the `IsinMapDocument` schema field stays read-only, and a `_TICKER_KIND_OVERRIDE` dict in code wins over the data file. ~30 minutes. Low.

## Alternatives considered

- **Auto-default unknown tickers to AKTIE in code.** Rejected — silent miscomputation by up to 30% of gain (the AKTIENFONDS Teilfreistellung). Banned by `app/domain/tax/CLAUDE.md`.
- **Heuristic on ticker suffix (`.DE` → ETF, etc.).** Rejected — fragile; `.DE` covers both ETFs (VUSA.DE) and direct equity (RHM.DE).
- **Separate `classification.json` file.** Rejected — splits the per-ticker metadata across two files; users would have to remember to update both.
- **Pull classification from yfinance `quoteType` automatically.** Rejected as the *only* source — `quoteType=EQUITY` doesn't distinguish a German Aktie from a US ADR for tax purposes; the user's call is required. Used only as a default-suggestion hint.

## Implementation ticket

TICKET-H1.
