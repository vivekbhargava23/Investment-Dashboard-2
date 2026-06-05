# TICKET-TAX-1 — Fix `StreamlitDuplicateElementKey` on the Tax page when classification fails

**Priority:** HIGH
**Estimated session length:** 30 min
**Recommended model:** Haiku — mechanical bug fix in a single UI file plus one regression test. Low blast radius.
**Drafted by:** Vivek + Claude Chat (2026-06-05)
**Implemented by:** TBD
**Milestone:** Investment Panel

---

## Problem

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

## Out of scope

- Any change to the cached helpers (`_cached_tax_summary`, `_cached_liquidation_summary`, `_cached_harvest_report`) or to the tax engine. This is a pure UI presentation fix.
- Auto-creating ISIN entries from the warning button. The button just navigates; the user still does the mapping work on the Mappings page.
- Hiding the Tax page from the nav when classification can't complete. Out of scope; tracked separately if needed.
- The underlying `AY7.F` mapping itself — that's a data fix the user will do via the UI after this lands.

---

## Notes / assumptions

- Assumes Streamlit's testing harness (`AppTest` or equivalent) is available in this project. If no existing UI test uses it, the alternative test form in Step 1 (mocking `st.button` and asserting unique keys across three calls) is acceptable.
- Assumes the cached helpers raise `InstrumentClassificationError` independently — i.e. the same underlying classification failure could surface in one helper but not another, depending on which transactions and which `as_of` boundary each helper uses. The bug report's traceback (only the harvest handler raising) supports this.
- Assumes no other page renders a button with key `tax_open_mappings_*`. Quick grep before editing: `grep -rn "tax_open_mappings" app/ tests/`. Should match only `tax.py`.
- The classification error message ("Ticker 'X' is not in the ISIN map.") is produced by `app/domain/tax/classification.py`. Do not modify that copy here.
