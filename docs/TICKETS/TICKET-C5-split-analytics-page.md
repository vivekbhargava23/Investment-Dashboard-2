# TICKET-C5 — Split analytics.py into per-tab files

**Status:** QUEUED
**Priority:** LOW
**Estimated session length:** 1 hr
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Milestone:** UI polish

---

## Problem

`app/ui/pages/analytics.py` is ~1000 lines holding five tabs (Performance, Concentration, Correlation, Technicals, Position Sizer). Each tab has its own ~150–250 line `_render_*_tab` function plus tab-local helpers. Editing one tab forces context-loading the other four.

## Solution

Split each tab into its own file under `app/ui/pages/analytics/`:

```
app/ui/pages/analytics/
├── __init__.py          re-exports render()
├── _shell.py            the top-level render() with tab routing
├── performance.py       _render_performance_tab + tab-local helpers
├── concentration.py     same
├── correlation.py       same
├── technicals.py        same
└── sizer.py             same
```

`_shell.py::render()` is the only public entry; it does:

```python
def render() -> None:
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Performance", "Concentration", ...])
    with tab1: performance.render()
    with tab2: concentration.render()
    ...
```

Each tab module owns its own caches (the existing page-local `@st.cache_data` wrappers move with the tab). Shared dependencies (live positions cache) come from `services/valuation.py::get_live_positions_cached` per TICKET-R5.

### Migration steps

1. Create `app/ui/pages/analytics/__init__.py` that re-exports `render` from `_shell.py`.
2. Move each `_render_*_tab` function into the matching module as `render()`.
3. Move tab-local helpers into the same file.
4. `_shell.py` imports and calls each tab.
5. Update imports in `app/ui/main.py` (nav route still points at `app.ui.pages.analytics` — the package's `__init__.py` provides `render`).
6. Delete the old `app/ui/pages/analytics.py`.

## Acceptance criteria

- [ ] `app/ui/pages/analytics/` package created with the five tab files + `_shell.py` + `__init__.py`.
- [ ] No tab module exceeds 300 lines.
- [ ] Old `analytics.py` deleted.
- [ ] Nav still routes "Analytics & Risk" to the new package; tab switching works identically to today.
- [ ] All tests pass; ruff / mypy / lint-imports clean.
- [ ] No behaviour changes — only file layout.

### Manual smoke

- Open Analytics page. All five tabs render correctly. Switching tabs preserves filters (existing session-state keys still work because keys are unchanged).
- KPIs, charts, and badges look identical to before.

## Out of scope

- Any change to tab content or computations.
- Splitting other large pages (`manage.py` at 846 lines, `tax.py` at 652 lines) — separate tickets if pursued.
- Extracting shared helpers across tabs into a `_helpers.py` — do it only if a clear duplication shows up during the split.

## Notes

- Be careful with session-state key collisions during the split — each tab function may have local constants like `_TECHNICALS_EMPTY_STATE` that need to come along.
- Test imports: `from app.ui.pages.analytics import render` must continue to work.
