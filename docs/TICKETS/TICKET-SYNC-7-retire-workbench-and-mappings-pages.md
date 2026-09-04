# TICKET-SYNC-7 — Retire the Import CSV workbench and ISIN Mappings pages

**Priority:** MEDIUM
**Milestone:** Investment Panel
**Recommended model:** Haiku for the deletions; Sonnet if the "All instruments" move needs judgement.
**Estimated session length:** 1 hr
**Drafted by:** Vivek + Claude (Cowork session 2026-09-03)
**Depends on:** TICKET-SYNC-6B.
**Additional gate:** The Sync page has been used for **two real Scalable exports** with holdings matching and no `unknown` cause; Vivek confirms this before the ticket is started.

> **After this ticket merges:** there is one door for broker data — the Sync tab. The old workbench and mappings pages, their sidebar entries, tests and screenshots are gone; their remaining useful parts live in the Sync tab's **All instruments** expander.

## Execution — one commit per step

### Step 1 — move "All instruments" into the Sync tab
From `app/ui/pages/mappings.py` move into `app/ui/pages/sync.py` (expander `All
instruments`, collapsed by default): the mapped table (`build_mapped_dataframe`, single-row
select, actions Change feed / Kind / Unmap / Remove with the same confirmations), the
unmapped list restricted to ISINs with `shares_csv == 0` (closed positions — open ones are
tasks already), and the ignored list with Restore. Move the pure helpers
(`_save_mapping`, `_delete_mapping`, `_ignore_isin`, `_restore_isin`, `_unmap_isin`,
`_set_instrument_kind`) to `app/services/isin_admin.py` with their tests moved to
`tests/unit/services/test_isin_admin.py`. Keep the cache clears added in SYNC-2.

### Step 2 — delete
`app/ui/pages/import_workbench.py`, `app/ui/pages/mappings.py`,
`tests/unit/ui/test_import_workbench.py` (after moving any still-relevant tests to
`test_sync_page.py` / `test_sync.py`), `tests/unit/ui/test_mappings_page.py`
(same), sidebar entries `import_workbench` and `mappings`, and the `mappings` references in `tests/unit/ui/test_sidebar_structure.py` and
`test_main_router.py`. Grep the repo for `import_workbench` and `mappings` (page id) and
resolve every hit; list them in the PR.

### Step 3 — archive, don't delete evidence
`git mv` the old pages' folders under `docs/screenshots/` to `docs/screenshots/_archive/`;
leave every ticket file and session-log entry untouched.

### Step 4 — docs
`docs/ARCHITECTURE.md` file layout: replace the two pages with `sync.py`. `README.md`: the
"Import" paragraph now describes the Sync tab in three sentences. Mark ADR-014 `Accepted`.

### Step 5 — gate, commit, session log, screenshots of the All instruments expander, PR.

## Acceptance criteria
- [ ] Sidebar shows Sync with Scalable, Manage Portfolio — no Import CSV, no ISIN Mappings.
- [ ] Every action the Mappings page offered is reachable from All instruments.
- [ ] `grep -rn "import_workbench\|pages.mappings" app tests docs` returns nothing.
- [ ] Gate clean.
