# TICKET-TAX-1 — Surface classification failures correctly: Tax-page duplicate key + Overview silent dash

**Priority:** HIGH
**Estimated session length:** 45 min
**Recommended model:** Sonnet — two UI pages, one cached-helper change, plus cache-key reasoning. Originally Haiku for Part A alone; Part B (added 2026-06-05) widens scope past a single-file mechanical fix.
**Drafted by:** Vivek + Claude Chat (2026-06-05); Part B added by Vivek + Claude Code (2026-06-05)
**Implemented by:** TBD
**Milestone:** Investment Panel

> **Theme:** when instrument classification can't complete (a held ticker is missing
> from the ISIN map), the app handles it wrong in two places. **Part A** — the Tax
> page crashes on a duplicate Streamlit key. **Part B** — the Live Overview silently
> swallows the error and renders `—` for the tax tiles, giving no hint why. Both are
> "classification failure surfaced badly"; fix them together.

---

## Part A — Tax page `StreamlitDuplicateElementKey`

### Problem

The Tax page crashes with `StreamlitDuplicateElementKey: ... key='tax_open_mappings'` whenever an `InstrumentClassificationError` is raised from more than one of the three cached helpers on the same render. The whole page fails to load — not just the failing section — because the duplicate-key exception escapes to `app/ui/main.py:render_page`.

Concrete observation on 2026-06-05 against `main`:

- Ticker `AY7.F` is present in `portfolio.json` but has no entry in `isin_map.json`. The tax classifier raises `InstrumentClassificationError("Ticker 'AY7.F' is not in the ISIN map. Open the Mappings page and create the mapping.")`.
- `_cached_tax_summary` raises that error → `_render_classification_warning(exc)` runs and creates a button with `key="tax_open_mappings"`.
- The render function does NOT return after the first warning (it does `return` only on line 637, but the next two `except InstrumentClassificationError` handlers fall through and continue rendering). In practice the first `return` triggers and the user sees a single warning — but the same code path is brittle: if any caller ever removes the `return`, or if a different exception path triggers the warning multiple times in one render, Streamlit dies on the duplicate key.
- The traceback in the bug report (tax.py:660 → tax.py:618) confirms `_render_classification_warning` was invoked from the harvest-report handler at line 660 with the same key, after another rendering of the warning had already registered it. The first `return` on line 637 evidently did not fire in that session, which means there's a real path where two of the three handlers run in one render — likely because the user reproduced this when the classification error was raised from `_cached_liquidation_summary` and `_cached_harvest_report` but NOT from `_cached_tax_summary` (which has its own data shape that may succeed where the others fail).
- Net effect: the Tax page is unrecoverable until the user adds the mapping. The warning banner that's supposed to *help* them fix it is the thing crashing the page.

## Solution

Two-part fix, both in `app/ui/pages/tax.py`:

1. **Make the button key unique per call site** so the duplicate-key state can't happen regardless of how the render path evolves.
2. **Render the warning at most once per request** so the user sees a single, clear banner instead of three identical ones. After the first classification-failure handler runs, downstream sections that depend on tax data should degrade gracefully (no extra warning) and the rest of the page should still render where it can.

### Decisions already made — do not re-litigate

- The warning UI itself does not change. Same copy, same single button, same `st.query_params["page"] = "mappings"` behaviour.
- The fix is **not** "return early after the first warning, full stop." The page should still render whatever sections *don't* depend on the failing helper. Today the YTD tiles render before the first exception path; we keep that. After a classification error in the liquidation or harvest helpers, the tiles should still be visible, and the only follow-up should be the single banner.
- Do **not** widen the `except` clauses. The fix is scoped to `_render_classification_warning` and its three call sites. No changes to the cached helpers or the tax engine.

---

## Execution

### Step 1: Add a regression test that reproduces the crash

**File:** `tests/unit/ui/test_tax_page_helpers.py` (extend) — or `tests/unit/ui/test_tax_page.py` if that's where rendering-path tests live; match the existing layout.

Add `test_classification_warning_renders_once_when_multiple_helpers_fail`:

- Patch `_cached_tax_summary`, `_cached_liquidation_summary`, and `_cached_harvest_report` so all three raise `InstrumentClassificationError("Ticker 'AY7.F' is not in the ISIN map.")`.
- Patch `get_live_positions_cached` to return an empty dict.
- Call `app.ui.pages.tax.render()` inside a Streamlit `AppTest` (use the existing pattern — check how other UI tests drive `render()`; if no pattern exists, the simpler form is to call `render()` directly with the Streamlit testing harness).
- Assert: the test does **not** raise `StreamlitDuplicateElementKey`.
- Assert: exactly one warning banner is rendered with the expected message.
- Assert: exactly one button with the "Open Mappings page" label is rendered.

If `AppTest` is not already used in the suite, an acceptable alternative is to call `_render_classification_warning(exc)` three times in a row inside a single render context with mocked `st.button` and assert that each call produces a distinct, non-colliding key. Either form proves the bug is gone.

**Acceptance for Step 1:** test exists and fails on `main` with `StreamlitDuplicateElementKey`.

### Step 2: Parameterize the button key

**File:** `app/ui/pages/tax.py`

Change `_render_classification_warning` to take an explicit call-site identifier:

```python
def _render_classification_warning(exc: InstrumentClassificationError, key_suffix: str) -> None:
    st.warning(
        f"⚠ Some tickers need a Tax kind before the full summary can be computed: {exc}\n\n"
        "Open the Mappings page to classify them."
    )
    if st.button("Open Mappings page", key=f"tax_open_mappings_{key_suffix}"):
        st.query_params["page"] = "mappings"
```

Update the three call sites:

- Line 636 (summary handler): `_render_classification_warning(exc, "summary")`
- Line 649 (liquidation handler): `_render_classification_warning(exc, "liquidation")`
- Line 660 (harvest handler): `_render_classification_warning(exc, "harvest")`

### Step 3: Render the warning at most once per request

**File:** `app/ui/pages/tax.py`

Inside `render()`, after the YTD tiles are rendered, introduce a local flag `classification_warned: bool = False` and gate `_render_classification_warning` calls on it. The first classification error that fires renders the banner and flips the flag; subsequent classification errors set their fallback (`liq_summary = summary`, empty `HarvestImpactReport`, etc.) without rendering a second warning.

Concretely:

```python
classification_warned = False

try:
    summary = _cached_tax_summary(...)
except InstrumentClassificationError as exc:
    _render_classification_warning(exc, "summary")
    return
except Exception as exc:
    st.error(f"Could not compute tax summary: {exc}")
    return

# YTD tiles — render before the next helpers in case they fail
_render_ytd_tiles(summary)

try:
    liq_summary = _cached_liquidation_summary(...)
except InstrumentClassificationError as exc:
    if not classification_warned:
        _render_classification_warning(exc, "liquidation")
        classification_warned = True
    liq_summary = summary
except Exception as exc:
    st.warning(f"Could not compute liquidation scenario: {exc}")
    liq_summary = summary

# ... same pattern for harvest
```

The summary-handler path still returns early (it must — the YTD tiles depend on `summary`). Liquidation and harvest handlers degrade gracefully and only the first one shows the banner.

### Step 4: Verify the rest of the page still renders under the failure path

Add a second test (or extend Step 1): when only the liquidation and harvest helpers fail (summary succeeds), assert that `_render_ytd_tiles` is called and that the warning banner appears exactly once. This is the canary that the "degrade gracefully" intent holds.

---

## Acceptance criteria

- [ ] `_render_classification_warning` takes a `key_suffix` parameter and uses it in the button key.
- [ ] All three call sites pass distinct suffixes (`"summary"`, `"liquidation"`, `"harvest"`).
- [ ] `render()` renders the classification warning **at most once** per request via a local flag.
- [ ] When `_cached_tax_summary` raises `InstrumentClassificationError`, `render()` still returns early (the YTD tiles cannot render without `summary`).
- [ ] When only `_cached_liquidation_summary` and/or `_cached_harvest_report` raise, the YTD tiles render and the banner appears exactly once.
- [ ] Regression test from Step 1 passes; would fail again if either fix is reverted.
- [ ] `pytest`, `ruff check .`, `mypy app/`, `lint-imports` all clean.

### Manual smoke (post-merge, by Vivek)

- Open the running Streamlit app on `main` after merge.
- Tax page should load: YTD tiles visible, single warning banner about `AY7.F`, one "Open Mappings page" button.
- Click the button → page query param should switch to `mappings` and the Mappings page renders.
- Map `AY7.F` (or whichever ISIN is missing today) on the Mappings page → return to Tax → full page renders without the banner.

---

## Part B — Live Overview tax tiles render `—`

### Problem

On the Live Overview, the **Sparerpauschbetrag** and **Tax Headroom** KPI tiles show
`—` even when the Tax Dashboard shows real numbers for the same portfolio. Observed
2026-06-05: a portfolio with realised gains shows values on Tax, dashes on Overview.

Root cause — two compounding mistakes in `app/ui/pages/overview.py`:

1. `_cached_tax_summary_for_overview` calls `compute_current_tax_summary(...)` **without
   passing `isin_map`** (`overview.py:62`). The service defaults `isin_map` to an empty
   `IsinMapDocument()` (`app/services/tax_planning.py:43`), so the engine can't classify
   the held instruments and raises `InstrumentClassificationError`. The Tax page does it
   right — it passes `isin_map=isin_map` (`tax.py`'s `_cached_tax_summary`).
2. The helper wraps the whole body in a blanket `except Exception: return None`
   (`overview.py:71`). The classification error is swallowed, `tax_summary` becomes
   `None`, and the tiles fall back to `—` with no banner — the banned "silent fallback
   to a default without surfacing it" anti-pattern (see `docs/METHODOLOGY.md`).

This is independent of Part A (different page, different helper) but is the same theme:
a classification failure handled badly.

> Note: RD1 (#140) did not introduce this — it only restyled the tiles. The `None →
> "—"` path predates it. Verify against `main` before implementing.

### Solution

In `app/ui/pages/overview.py`:

1. **Pass the real ISIN map** into `_cached_tax_summary_for_overview`:
   `compute_current_tax_summary(..., isin_map=get_isin_map_repo().load())`.
   `get_isin_map_repo` is already imported and used elsewhere in the file.
2. **Make the cache key honest.** The helper is `@st.cache_data` keyed on
   `(tx_sig, year)`; add an ISIN-map signature parameter (reuse the same
   `file_mtime_key`/signature approach the Tax page uses for its isin cache key) so the
   Overview tiles refresh when the user remaps a ticker.
3. **Stop swallowing the classification error silently.** Narrow the bare
   `except Exception`: on `InstrumentClassificationError`, still return `None` *but*
   have `render()` show a one-line caption under/near the tiles (e.g. "Tax tiles need
   ISIN mappings — open Mappings") instead of a bare `—`. Keep returning `None` for
   genuinely-unexpected exceptions, but do not hide the classification case. (Match
   Part A's "surface, don't crash or hide" intent; do not widen behaviour into a
   full second copy of the Tax-page banner — a caption is enough on the Overview.)

### Execution (Part B)

1. **Regression test first** (`tests/unit/ui/test_overview_helpers.py` or a sibling):
   build a portfolio whose held ticker is absent from the ISIN map, patch the price/FX
   ports so positions are live, and assert that `_cached_tax_summary_for_overview`
   (called with the real, populated map) returns a non-`None` `TaxYearSummary` — i.e.
   the tiles would render numbers. A companion test: with an *empty* map and a held
   ticker, the helper must not silently return `None` without the render path emitting
   the "needs mappings" caption. The first test fails on `main` today.
2. Apply the three solution changes above.
3. Manually verify on the running app (use `tools/app_sandbox.sh` + a seeded
   `portfolio.json` and a populated `isin_map.json`): the Overview Sparerpauschbetrag
   and Tax Headroom tiles show the same figures as the Tax Dashboard.

### Acceptance criteria (Part B)

- [ ] `_cached_tax_summary_for_overview` passes `isin_map=get_isin_map_repo().load()`.
- [ ] The helper's `@st.cache_data` key includes an ISIN-map signature so remapping a
      ticker refreshes the Overview tiles.
- [ ] The blanket `except Exception: return None` no longer hides classification
      failures: when classification can't complete, the Overview shows a short
      "needs ISIN mappings" caption rather than a bare `—`.
- [ ] With a fully-mapped portfolio, the Overview tax tiles match the Tax Dashboard
      figures (manual smoke).
- [ ] Regression test passes; would fail again if the `isin_map` argument is removed.

---

## Out of scope

- **Part A only:** no change to the Tax-page cached helpers
  (`_cached_tax_summary`, `_cached_liquidation_summary`, `_cached_harvest_report`) or to
  the tax engine — Part A is a pure UI presentation fix. (Part B *does* change exactly
  one Overview helper, `_cached_tax_summary_for_overview`, and the tax engine still is
  not touched.)
- Auto-creating ISIN entries from the warning button/caption. The control just
  navigates; the user still does the mapping work on the Mappings page.
- Hiding the Tax page (or the Overview tiles) from the nav when classification can't
  complete. Tracked separately if needed.
- The underlying missing mapping itself (`AY7.F` or whichever ticker) — that's a data
  fix the user does via the UI after this lands.

---

## Notes / assumptions

- Assumes Streamlit's testing harness (`AppTest` or equivalent) is available in this project. If no existing UI test uses it, the alternative test form in Step 1 (mocking `st.button` and asserting unique keys across three calls) is acceptable.
- Assumes the cached helpers raise `InstrumentClassificationError` independently — i.e. the same underlying classification failure could surface in one helper but not another, depending on which transactions and which `as_of` boundary each helper uses. The bug report's traceback (only the harvest handler raising) supports this.
- Assumes no other page renders a button with key `tax_open_mappings_*`. Quick grep before editing: `grep -rn "tax_open_mappings" app/ tests/`. Should match only `tax.py`.
- The classification error message ("Ticker 'X' is not in the ISIN map.") is produced by `app/domain/tax/classification.py`. Do not modify that copy here.
