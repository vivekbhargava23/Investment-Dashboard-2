# TICKET-ROBUST-1 — Stop swallowing page errors; escape data interpolated into HTML

**Status:** QUEUED
**Priority:** MEDIUM
**Estimated session length:** 2 hr
**Drafted by:** Vivek + Claude (Cowork review 2026-06-02)
**Implemented by:** _pending_
**Recommended model:** Sonnet — localized changes (router + HTML helpers) with clear, testable criteria, though it touches every page during the escaping audit.
**Milestone:** Production hardening
**Depends on:** None.

> **After this ticket merges, a broken page shows an actual error instead of a misleading "Coming Soon", and data rendered into HTML can't break (or inject into) the page.** Two production-grade robustness fixes that currently bite silently.

---

## Problem

### 1. The router swallows every page exception

`app/ui/main.py::render_page` (main.py:43–54) wraps the page import + `render()` in
`except Exception: pass` and falls back to the "Coming Soon" placeholder. A real bug in,
say, `tax.py` therefore renders as a blank "Coming Soon" with **zero diagnostics** — hard to
debug, and misleading to the user (the page exists; it crashed).

### 2. Data is interpolated into HTML unescaped

`app/ui/pages/overview.py::_build_positions_table_html` interpolates the company `name`
(from `isin_map`) straight into an f-string HTML table (overview.py:153+) with no escaping.
A name containing `<`, `>`, or `&` breaks the table layout, and in principle injects markup
into the page (`render_html` uses `unsafe_allow_html=True`). The same risk exists anywhere a
data-derived string is interpolated into an HTML f-string and passed to `render_html`.

## Solution

### Router (main.py)

- Catch the exception, **log it** (`logging.exception`), and render a real error surface:
  in dev (`get_settings().app_env != "prod"`) show `st.exception(e)`; otherwise a friendly
  "This page failed to load" with the page id. Keep the "Coming Soon" placeholder **only** for
  pages that genuinely have no `render()` (the not-built case), not for crashes — distinguish
  "module/`render` missing" from "`render()` raised".

### HTML escaping (comprehensive audit)

- Add/centralize escaping for any **data-derived** string interpolated into HTML. Prefer
  doing it at the interpolation site with `html.escape(...)`, or add a tiny helper in
  `app/ui/render.py`.
- Audit every `render_html(...)` / HTML f-string builder for unescaped data interpolation and
  fix all of them — not just the positions table. Known starting points: `overview.py`
  (`_build_positions_table_html`, name + ticker), plus any page building HTML from tx
  notes, company names, or mapping labels. Static/computed-number interpolation (e.g.
  formatted EUR) does not need escaping; user/data strings do.

## Acceptance criteria

- [ ] A page whose `render()` raises shows a logged traceback + visible error (dev), not "Coming Soon".
- [ ] "Coming Soon" appears only for pages with no `render()` — verified by a test that distinguishes the two cases.
- [ ] A company name containing `<b>&"` renders as literal text in the positions table (unit/string test on the table builder), not as markup.
- [ ] Audit complete: no `render_html` call interpolates an unescaped data-derived string anywhere under `app/ui/`.
- [ ] All tests pass; ruff / mypy / lint-imports clean.

### Manual smoke

- Temporarily `raise` inside one page's `render()` → see the error surface, not "Coming Soon". Revert.
- Set a mapping name to `Acme <test> & Co` → Overview table shows it literally, layout intact.
