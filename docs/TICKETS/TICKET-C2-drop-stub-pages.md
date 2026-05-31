# TICKET-C2 — Drop stub pages from nav and delete stub files

**Status:** QUEUED
**Priority:** MEDIUM
**Estimated session length:** 30 min
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Milestone:** UI polish

---

## Problem

Per ADR-008: four pages (`decision.py`, `lots.py`, `performance.py`, `behaviour.py`) are 5-line stubs that render nothing. Sidebar still lists them. They make the app feel broken.

## Solution

### Step 1 — Delete the stub files

```
app/ui/pages/decision.py
app/ui/pages/lots.py
app/ui/pages/performance.py
app/ui/pages/behaviour.py
```

### Step 2 — Remove from nav

`app/ui/main.py` and `app/ui/components/sidebar.py` (whichever owns the nav definition — grep for `decision`, `lots`, `performance`, `behaviour` in the UI layer).

Remove the four entries from the page registry/router. If the registry uses a dict, delete those keys; if it's a list, delete those items.

### Step 3 — Remove any dead session-state handoffs

Grep for `current_page` and `query_params["page"]` set to any of the four. Remove or redirect:
- If something pointed at `performance` for a handoff, redirect to `analytics` (Performance tab lives there).
- The other three have no real handoffs.

### Step 4 — Update ARCHITECTURE.md

Strip the four page entries from the "File layout" section's `ui/pages/` block. Keep `lots.py` mentioned in a one-line note: *"Per-lot view is rendered inside the Tax page; a standalone Lots page is not currently in scope."*

### Step 5 — Regenerate CONTEXT.md

Run `python tools/regen_context.py` so the auto-snapshot stops re-advertising the dropped pages. Commit the regenerated CONTEXT.md alongside the file deletions.

## Acceptance criteria

- [ ] Four stub files deleted.
- [ ] Sidebar shows only working pages (Overview, Manage, Mappings, Research, Company, Analytics, Tax, Simulator, Import Workbench).
- [ ] No broken imports anywhere — `ruff` and `mypy` clean.
- [ ] `ARCHITECTURE.md` updated to remove the four pages.
- [ ] `CONTEXT.md` regenerated.
- [ ] No 404 / KeyError on app startup or page switch.
- [ ] All tests pass; ruff / mypy / lint-imports clean.

### Manual smoke

- Start app. Sidebar shows the working pages only. Clicking through each one renders normally.
- Force a query string `?page=lots` in the URL — gracefully redirects to Overview (or 404s clearly, depending on router behaviour).

## Out of scope

- Building any v1 of Decision Gates, Lots Ledger, Performance page, or Behavioural Ledger. Those are new tickets when there's a real spec.
- Reorganising any of the surviving pages.

## Notes

- The stub files in git history remain — if any of the four is ever worth building, the placeholder is preserved as a reference, not a working artifact.
- The Performance *tab* inside Analytics is unaffected.
