# TICKET-CSV-13 — Zero-touch CSV import (auto-resolve ticker + tax kind)

**Status:** QUEUED
**Priority:** HIGH
**Estimated session length:** 90 min
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Milestone:** UX polish / Investment Panel

---

## Problem

Today, importing a Scalable Capital CSV is a multi-surface, per-row task:

1. **Workbench** (`app/ui/pages/import_workbench.py`) shows unmapped ISINs in a side panel where Vivek types a ticker into `st.text_input` and clicks **Save** — one row at a time. No fuzzy search, no auto-resolution.
2. To get a real fuzzy search **and** to set the German tax kind (Aktie / Aktienfonds / Mischfonds / …), Vivek has to leave the Workbench, jump to the **Mappings** page, search, pick a tax kind from a dropdown, save — again, one row at a time.
3. He then comes back to the Workbench, re-runs the plan, and applies.

The Scalable CSV does NOT carry a ticker, and its `assetType` column only says `Security` / `Cash` (no Aktie vs ETF distinction). So both the **ticker** and the **tax kind** must be derived from something outside the CSV. Today, "something outside the CSV" is Vivek's brain.

This is needless. yfinance Search accepts an ISIN as a query and returns the canonical ticker. yfinance `Ticker.info["quoteType"]` returns `EQUITY` / `ETF` / `MUTUALFUND`, which maps unambiguously to `AKTIE` / `AKTIENFONDS` / `MISCHFONDS` for 99% of holdings the user actually owns (current map: 19 AKTIE, 5 AKTIENFONDS, 0 of anything else). The app already has `_suggest_kind` in `mappings.py` doing exactly this lookup as a *hint* — but it doesn't auto-save.

## Solution

A single "Import" flow with one user decision: **Apply**.

### Step 1 — Add an auto-resolver

New module `app/services/isin_autoresolve.py`. Public API:

```python
@dataclass(frozen=True)
class AutoResolveResult:
    isin: str
    ticker: str | None
    name: str | None
    instrument_kind: InstrumentKind | None
    confidence: Literal["high", "medium", "low"]
    reason: str  # human-readable; e.g. "yfinance Search top match, quoteType=EQUITY"

def autoresolve_isin(
    isin: str,
    description_hint: str,                 # CSV "description" — used for name-similarity scoring
    *,
    resolver: TickerResolver,
    company_provider: CompanyDataProvider,
) -> AutoResolveResult: ...
```

Implementation:

- **Ticker lookup:** call `resolver.resolve(isin, limit=5)`. yfinance Search accepts ISINs as queries and returns ticker matches.
  - If 1 result → that's the ticker. Confidence `high`.
  - If >1 results → score each: prefer EUR-denominated, prefer `.DE` / `.F` suffix (Scalable is a German broker; the home listing is usually the one Scalable transacted on), prefer name-similarity to the CSV description (Jaro-Winkler or a simple normalized substring match; keep it dependency-free). Pick the top. Confidence `medium` if the top score is clearly ahead; `low` if it's a coin flip.
  - If 0 results → ticker = None, confidence `low`, reason `"yfinance Search returned no matches for ISIN"`.
- **Tax kind:** if ticker is non-None, fetch `quoteType` cheaply. **Do not** call the full `get_company()` — it pulls fundamentals, dividends, history, etc. (see `app/adapters/company_yfinance/adapter.py:62-97`). Add a narrow method:
  ```python
  # On CompanyDataProvider (port) and YfinanceCompanyAdapter (adapter):
  def get_quote_type(self, ticker: str) -> str | None: ...
  ```
  Map:
  - `EQUITY` → `InstrumentKind.AKTIE`
  - `ETF` → `InstrumentKind.AKTIENFONDS`
  - `MUTUALFUND` → `InstrumentKind.MISCHFONDS` (defaultable; the user has none of these today, so the default is "safe enough; flag for review")
  - anything else (`CURRENCY`, `INDEX`, `CRYPTOCURRENCY`, …) → kind = None, confidence drops to `low`.
- All network calls go through the existing `CachedTickerResolver` (30-day TTL) so re-running on the same CSV is free.

### Step 2 — Wire it into the Workbench flow

In `import_workbench.py::_render_upload_section`, immediately after `plan_import` produces the plan:

- Collect every `PlannedRow` with `status == RowStatus.UNMAPPED_ISIN`.
- For each unique ISIN, call `autoresolve_isin(...)`.
- For each result with `confidence` in `{high, medium}` AND `ticker is not None` AND `instrument_kind is not None`: write a new `IsinMapping(status="mapped", ticker=..., instrument_kind=...)` to `isin_map.json`. (Save once, not per row.)
- After saving, re-run `plan_import` against the updated ISIN map. Rows that were UNMAPPED_ISIN should now be NEW.

### Step 3 — Replace the per-row Workbench ISIN panel with a review card

Delete `_render_isin_mapping_panel` (`import_workbench.py:389-442`). Replace with:

- **If any auto-mappings happened:** a green banner: *"Auto-mapped 5 ISINs (3 high-confidence, 2 medium). [Review]"*. The expander lists each ISIN → ticker → kind with the reason and a one-click **Reject** button that demotes that ISIN back to status="unmapped" and re-plans.
- **If any ISINs failed to auto-resolve (low confidence or ticker=None):** a yellow banner: *"2 ISINs need manual review."* The expander shows the existing fuzzy searchbox + tax-kind dropdown (reuse `render_ticker_searchbox` and `_suggest_kind` from `mappings.py` — extract them to `app/ui/components/isin_mapper.py` so both pages share the same component).

### Step 4 — Mappings page becomes settings-only

`app/ui/pages/mappings.py` keeps its current functionality (edit existing mappings, delete, refresh) but is no longer a *required* stop during import. The closing footer text ("Re-run the importer after mapping new ISINs…") is removed — re-running is handled by the Workbench's re-plan.

### Step 5 — Logging

Every auto-resolve writes one line to `data/import_log.json` with the same shape as existing entries plus an `auto_resolved` array of `{isin, ticker, kind, confidence, reason}`. Audit trail for "why did the system pick this ticker?"

## Acceptance criteria

- [ ] Uploading a CSV with N previously-unmapped ISINs results in ≥80% being auto-mapped without manual ticker entry (measured on the user's current Scalable CSV).
- [ ] User flow for a clean CSV with all high-confidence ISINs: upload → see "Auto-mapped X ISINs" banner → click **Apply**. That's it. Two clicks total.
- [ ] Low-confidence ISINs still surface a fuzzy-search UI inline in the Workbench — no jumping to Mappings page required.
- [ ] Auto-resolved mappings are persisted in `isin_map.json` with `status="mapped"`, the inferred `instrument_kind`, and `name` populated from the CSV description.
- [ ] Re-uploading the same CSV is a no-op (already-imported rows + cached resolutions).
- [ ] yfinance is called at most once per unique ISIN per CSV upload (cache hit thereafter).
- [ ] `get_quote_type()` does NOT pull fundamentals / price history (verified by reading the adapter, or by mock-call assertions in a unit test).
- [ ] Reject button on the review card demotes a mapping back to unmapped and re-plans.
- [ ] Mappings page still works for editing / deleting existing mappings.
- [ ] All tests pass; ruff / mypy / lint-imports clean.

### Manual smoke

- Upload Scalable CSV with 5 net-new ISINs (rotate the test fixture). Confirm the banner reads "Auto-mapped 5 ISINs". Confirm `isin_map.json` has 5 new `mapped` entries with `instrument_kind` set. Click Apply. Confirm transactions are added.
- Force a low-confidence case: feed an ISIN that yfinance doesn't recognize (e.g. a delisted security). Confirm the inline fuzzy-search UI appears.
- Click **Reject** on one auto-mapped row. Confirm it returns to the manual-review panel and `isin_map.json` no longer contains the rejected ticker.

## Out of scope

- OpenFIGI integration. yfinance Search handles ISINs adequately for Scalable's coverage (US/EU equities + UCITS ETFs). Add OpenFIGI only if we hit a meaningful miss rate (>10%) — separate ticket.
- Auto-classification for `MISCHFONDS` vs `AKTIENFONDS` for borderline ETFs (e.g. multi-asset). Default to `AKTIENFONDS` and mark medium-confidence so the user sees the suggestion in the review card.
- Cash event types (Distribution, Interest, etc.) — still out of scope per CSV-3.
- Moving the German tax-kind logic out of the ISIN map. Same as today — kind is stored on `IsinMapping`.
- Merging the Workbench and Mappings pages into one. They keep distinct purposes (import vs. settings). The job of this ticket is to make the import flow not *require* the settings page.

## Notes / dependencies

- Depends on existing `TickerResolver` (yfinance Search) and `CompanyDataProvider` (yfinance Ticker.info).
- Add `get_quote_type` to the `CompanyDataProvider` port + `YfinanceCompanyAdapter`. Existing `get_company` callers unaffected.
- Name-similarity scoring: use `difflib.SequenceMatcher.ratio()` (stdlib). Threshold ≥ 0.6 for "matches the CSV description well".
- Per LEARNING-GOALS.md automation-first rule: the goal is to make Vivek's import a 2-click flow on the happy path. If the heuristics get this wrong often, file a follow-up ticket — don't add manual escape hatches preemptively.
