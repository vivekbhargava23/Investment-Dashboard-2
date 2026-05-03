# TICKET-008b — Positions table HTML leak fix + render_html helper

**Status:** TODO
**Priority:** P0 — blocks TICKET-008 merge
**Estimated session length:** 30–45 min
**Drafted by:** Vivek + Claude (chat 2026-05-03)
**Implemented by:** _pending_
**Depends on:** TICKET-008 (introduces the bug being fixed)

---

## Problem

The positions table on the Live Overview page renders raw HTML markup (`<tr>`, `<td>`, `<strong>`) as visible text inside a code block, instead of rendering as an actual table. See `docs/reference/screenshots/TICKET-008b-bug.png`.

**Root cause:** every `st.markdown(f"""...""", unsafe_allow_html=True)` call in `app/ui/pages/overview.py` passes an HTML string with leading whitespace (newline + indentation from being inside a function-scoped f-string). Markdown's parser treats any line indented 4+ spaces as a code block. Short HTML strings escape this; the deeply-nested positions table does not.

The bug surfaces in the table because (a) it is the longest HTML block, and (b) `tbody_rows` are themselves indented f-strings concatenated into another indented f-string template, multiplying the leading whitespace.

A previous attempt (commit `04578af`, "fix: reconcile TICKET-007 and TICKET-008 UI integration") modified `overview.py` and `dark.css` but did not fix the bug. The HTML leak persists in the current branch state.

## Architectural decision implemented by this ticket

**All HTML emitted to Streamlit must route through a single helper, `app/ui/render.py:render_html()`.** This helper applies `textwrap.dedent` and `.strip()` before passing to `st.markdown(..., unsafe_allow_html=True)`. The helper is the *only* place in the codebase where `unsafe_allow_html=True` is set.

This makes the leading-whitespace bug structurally impossible: even if a future page passes deeply-indented HTML, the helper strips it before rendering.

## Acceptance criteria

### `app/ui/render.py` — new file

- [ ] Module docstring explaining the markdown leading-whitespace bug and why this helper exists.
- [ ] Single function `render_html(html: str) -> None` that calls `st.markdown(dedent(html).strip(), unsafe_allow_html=True)`.
- [ ] Type-annotated, mypy strict-clean.
- [ ] Imported `from textwrap import dedent` and `import streamlit as st`.

### `app/ui/CLAUDE.md` — new file (or update existing)

- [ ] Add a "HTML rendering rule" section:
  > Any helper or page that emits HTML for `st.markdown` must use `render_html()` from `app/ui/render.py`. This is the *only* place in the codebase where `unsafe_allow_html=True` is set. Never call `st.markdown(..., unsafe_allow_html=True)` directly. The helper handles dedent + strip so leading-whitespace markdown-as-code-block bugs are impossible by construction.

### `app/ui/pages/overview.py` — refactor

- [ ] Replace **every** `st.markdown(..., unsafe_allow_html=True)` call with `render_html(...)`.
- [ ] Add `from app.ui.render import render_html` to imports.
- [ ] When building `tbody_rows`, ensure each row string is constructed without leading-whitespace indentation. Either:
  - Build rows as single-line strings (no `f"""..."""` blocks for rows), OR
  - Apply `dedent()` to each row when appending.
  - The choice is the implementer's; both work. Prefer the second for readability.
- [ ] No other logic changes. Do not touch the cache wrappers, signature function, placeholder dicts, sorting, formatting, or the `render()` function's data pipeline.

### Tests

#### `tests/unit/ui/test_html_helper.py` — new

- [ ] Test that `render_html` strips leading whitespace from indented input. Mock `st.markdown` and assert the string passed in starts with `<` as character 0.
- [ ] Test that `render_html` preserves internal HTML structure (only leading/trailing whitespace stripped).
- [ ] Test that `render_html` handles empty string gracefully.

#### `tests/unit/ui/test_overview_render.py` — extend

- [ ] **Regression test for the HTML leak:** extract the table-building logic from `overview.py:render()` into a pure helper function `_build_positions_table_html(positions, summary) -> str` (refactor as part of this ticket). Test asserts:
  - Returned string starts with `<` as character 0 (no leading whitespace).
  - Returned string contains exactly one `<table` tag.
  - Returned string contains `<tr` for each non-empty position row.
  - Returned string does **not** contain `&lt;` (would indicate double-escaping).
  - Returned string does **not** start with 4+ spaces (would trigger markdown code block).
- [ ] This test must FAIL on `main` (current state) and PASS after the fix.

### Lints / quality
- [ ] `pytest` — all tests pass (existing 97 + new 4–6 = 101–103 total)
- [ ] `ruff check .` — passes
- [ ] `mypy app/` — passes
- [ ] `lint-imports` — passes; `app.ui.render` is allowed to import streamlit (UI layer)

### Manual verification (in PR description)
- [ ] Run `streamlit run app/ui/main.py` (with `pip install -e .` done, no PYTHONPATH workaround needed).
- [ ] Live Overview page positions table renders as a proper HTML table — column headers visible, rows with ticker symbols, prices, gains, weight bars.
- [ ] No raw `<tr>` or `<td>` text visible anywhere on the page.
- [ ] Screenshot attached to PR showing the fixed table.
- [ ] All sidebar nav items still work (regression check).
- [ ] Refresh button still works (regression check).

---

## Files NOT to modify

The following files are explicitly out of scope. Touching them = ticket fails review:

- `app/ui/main.py` — entry point, no bugs here, leave it alone
- `app/ui/components/sidebar.py` — sidebar is fine, do not "improve" it
- `app/ui/components/topbar.py` — topbar is fine, do not "improve" it
- `app/ui/components/badges.py` — used as-is
- `app/ui/components/metric_card.py` — used as-is
- `app/ui/styles/dark.css` — theme is fine, do not "reconcile" it
- `app/services/*` — no service changes
- `app/domain/*` — no domain changes
- `app/adapters/*` — no adapter changes
- `app/ports/*` — no port changes
- Any test other than `tests/unit/ui/test_html_helper.py` and `tests/unit/ui/test_overview_render.py`

If during implementation a different file *seems* to need changes, **stop and flag it in the PR description.** Do not silently expand scope.

## Out of scope

- Sidebar placeholder cleanup (Analytics & Risk, Performance, etc.) — separate ticket TICKET-008c if needed.
- Any styling changes to the table — purely a rendering bug fix.
- Refactoring other pages to use `render_html` — those don't have visible bugs yet. The `app/ui/CLAUDE.md` rule will catch new pages going forward; old pages can be migrated lazily.
- Performance improvements, caching changes, additional features.

## Notes

### Why this is its own ticket and not a TICKET-008 amendment

TICKET-008's scope (live overview wiring + seed script) is complete and correct. The HTML leak is a rendering bug introduced by the table implementation specifically. Treating it as a separate ticket gives the fix a clean commit history, a focused PR, and a regression test that documents the bug for future AI sessions.

### Why a previous fix attempt failed

Commit `04578af` ("reconcile TICKET-007 and TICKET-008") modified `overview.py` (31 lines) and `dark.css` (114 lines) claiming to fix the HTML leak by "removing Python `# noqa` comments from within f-strings." This diagnosis was incorrect — the bug is markdown's leading-whitespace code-block rule, not f-string comment leakage. The fix did not address the actual cause and the bug persists.

The previous attempt also expanded scope (CSS theme reconciliation) without explicit ticket authorization. This ticket's "Files NOT to modify" section exists to prevent that recurrence.

### Why centralize through `render_html`

The bug is structural: any HTML in an f-string inside a function will be indented. Asking implementers to "remember to dedent" is asking the bug to come back. A single helper that always dedents + strips makes it impossible. The cost is a one-line import in every page; the benefit is the bug is fixed everywhere, forever.

### Methodology note

This ticket establishes two patterns:

1. **"Files NOT to modify" section** for bug-fix tickets where scope creep has happened or is likely. Use this for any ticket where a prior session expanded scope.
2. **Regression tests written first.** The test that asserts "string starts with `<`" must be written and confirmed failing before the fix is implemented. This guarantees the fix actually addresses the visible bug.

Both patterns should be added to `docs/METHODOLOGY.md` after this ticket lands.