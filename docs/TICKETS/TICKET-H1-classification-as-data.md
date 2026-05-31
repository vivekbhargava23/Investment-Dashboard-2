# TICKET-H1 — Move instrument classification from source code to ISIN map

**Status:** QUEUED
**Priority:** CRITICAL
**Estimated session length:** 2 hr
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Milestone:** Tax engine

---

## Problem

After the Scalable CSV importer landed, transactions for new tickers (DELL, CIEN, KD, etc.) enter the system via the Mappings page, but those tickers are never added to `TICKER_KIND` in `app/domain/tax/classification.py`. The tax pipeline (`tax/pipeline.py:91`) calls `classify_instrument(gain.ticker)` for every realised gain and aborts on the first unclassified one. Today this manifests as:

- Tax page: `Could not compute tax summary: Ticker 'DELL' has no instrument-kind classification.`
- Sell Simulator: `Simulation error: Ticker 'DELL' has no instrument-kind classification.`

Both pages are broken until source code is edited and merged for every new ticker. See ADR-006 for the architectural rationale.

## Solution

Per ADR-006: move classification from a hardcoded dict to a per-ticker field on `IsinMapping`. Preserve loud-failure semantics; preserve "no silent defaults". Add a "Tax kind" dropdown to the Mappings UI so the user can classify in 5 seconds.

### Step 1 — Domain model

`app/domain/isin_map.py`:

```python
from app.domain.tax.classification import InstrumentKind

class IsinMapping(BaseModel):
    model_config = ConfigDict(frozen=True)
    ticker: str | None
    name: str
    status: Literal["mapped", "unmapped"]
    last_seen_in_csv: date | None = None
    instrument_kind: InstrumentKind | None = None   # NEW
```

`instrument_kind` is `None` for legacy entries until migration runs. Pydantic round-trips the StrEnum cleanly.

### Step 2 — Refactor `classify_instrument`

`app/domain/tax/classification.py`:

```python
def classify_instrument(ticker: str, isin_map: IsinMapDocument) -> InstrumentKind:
    """Look up by ticker across all entries. Raise if missing or unclassified."""
    upper = ticker.upper()
    for entry in isin_map.entries.values():
        if entry.ticker and entry.ticker.upper() == upper:
            if entry.instrument_kind is None:
                raise InstrumentClassificationError(
                    f"Ticker '{ticker}' has no tax classification. "
                    f"Open the Mappings page and pick a Tax kind."
                )
            return entry.instrument_kind
    raise InstrumentClassificationError(
        f"Ticker '{ticker}' is not in the ISIN map. "
        f"Open the Mappings page and create the mapping."
    )
```

The `TICKER_KIND` dict and the parameterless `classify_instrument(ticker)` are deleted.

### Step 3 — Update pipeline callers

`tax/pipeline.py:91` and any other call site updates to pass the loaded `IsinMapDocument`. The pipeline already accepts a `TaxYearLedger`; add `isin_map: IsinMapDocument` to the ledger and thread it through. Service-layer callers (`services/tax_planning.py`, `services/sell_simulator.py`) load the map once via `get_isin_map_repo()` and pass it in.

### Step 4 — Mappings UI dropdown

`app/ui/pages/mappings.py`:

- Add a `_KIND_OPTIONS = list(InstrumentKind)` next to the ticker picker.
- In `_render_unmapped_section` and `_render_edit_row`: render `st.selectbox("Tax kind", _KIND_OPTIONS, format_func=...)` after the searchbox.
- Pre-fill: if the user has a `CompanyDataProvider` available, call `get_company(ticker).quote_type` and suggest:
  - `EQUITY` → `AKTIE`
  - `ETF` → `AKTIENFONDS`
  - `MUTUALFUND` → `MISCHFONDS`
  - else → no preselection
- Save button: disabled until both ticker and kind are picked. Error toast on save attempt with `kind is None`.
- `_save_mapping` writes `instrument_kind` alongside `ticker`.

### Step 5 — Migration script

`tools/migrate_classification_to_isin_map.py`:

- Reads the (about-to-be-deleted) `TICKER_KIND` dict from a git-history snapshot or an embedded constant inside the script.
- Loads `data/isin_map.json`.
- For each entry whose `ticker` is in `TICKER_KIND`, sets `instrument_kind` to the matching kind.
- Saves the document. Logs a warning for any ticker in `TICKER_KIND` that is not present in the ISIN map (the user manually added it without going through CSV — they need to map the ISIN first).
- Idempotent: re-running is a no-op.

Run once before deleting `TICKER_KIND`. The script does not need to live forever — commit it, run it, leave it; future use is rare.

### Step 6 — Error UX

The error message users see when classification is missing should link to the page that fixes it:

- Tax page: catch `InstrumentClassificationError`, render `st.warning` with a button "Open Mappings page" that switches to the Mappings tab.
- Sell Simulator: same pattern.

## Acceptance criteria

- [ ] `IsinMapping.instrument_kind: InstrumentKind | None` added; existing `isin_map.json` loads without error (field defaults to `None`).
- [ ] `classify_instrument(ticker, isin_map)` signature in place; `TICKER_KIND` dict deleted; the parameterless form is gone.
- [ ] All pipeline callers pass the loaded `IsinMapDocument`.
- [ ] Mappings page shows a "Tax kind" dropdown for both unmapped-section and edit-row.
- [ ] Save is blocked until both ticker and kind are picked. Error toast on attempted save without kind.
- [ ] `CompanyData.quote_type` suggests a default kind (if provider is reachable) but never auto-saves.
- [ ] `tools/migrate_classification_to_isin_map.py` runs successfully against the current `isin_map.json`; the 11 legacy tickers all gain their `instrument_kind` set.
- [ ] Tax page renders without aborting on DELL or any other CSV-imported ticker — it shows a clear "Some tickers need a tax kind" warning with a link to Mappings.
- [ ] Sell Simulator behaves the same way: warning with a link, not a Python exception.
- [ ] All tests pass; ruff / mypy / lint-imports clean. The "Never silent-default" rule in `app/domain/tax/CLAUDE.md` is updated to reference `IsinMapping.instrument_kind` instead of `TICKER_KIND`.

### Manual smoke

- Start app, open Tax page. Currently crashes on DELL. After fix: shows yellow warning, link to Mappings.
- Mappings page → DELL row → set Tax kind = AKTIE → Save. Return to Tax page → numbers compute.
- Add a brand-new ticker via the Manage form. Visit Mappings, see the new entry unclassified. Set kind. Tax/Simulator both work.

## Out of scope

- Adding more InstrumentKind variants (REIT, derivatives). The existing 9 are sufficient.
- Reading `quote_type` from any provider other than the existing `CompanyDataProvider`. Finnhub fallback is fine but not required.
- Bulk-classify UI ("classify all unclassified tickers at once"). Each one is a one-click pick; no need.
- A separate `classification.json` file. ADR-006 explicitly rejects this.

## Notes / assumptions

- Assumes `CompanyData` has or will have a `quote_type` field. If it doesn't, the dropdown still works — the auto-suggest hint is optional. Confirm before implementing; if absent, add the field in this ticket (~10 lines) or open a follow-up.
- Assumes `IsinMapDocument` is loaded once per page render and is small enough to pass by value (it is — even 1000 entries is well under a KB).
- Assumes `_KIND_LABEL` in `tax.py:41` is reused for human-readable dropdown labels — don't duplicate the German names.
- Risk: any cached `TaxYearSummary` from before migration may have stale `instrument_kind` values. The summary is recomputed on every page render; no persistent cache exists for it. Safe.
- The "Open Mappings page" button uses the same `st.session_state["current_page"]` + `st.query_params["page"]` handoff already used by the simulator-buy link in `research.py:97`.
