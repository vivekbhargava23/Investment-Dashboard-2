# TICKET-CSV-17 — "Erase imported data": guarded full reset + scoped (partial) reset

**Priority:** MEDIUM
**Status:** IN_PROGRESS
**Estimated session length:** 2 hr
**Recommended model:** Opus — destructive data operation on the book of record; confirmation + backup correctness matter.
**Drafted by:** Vivek + Claude Code (session 2026-06-05)
**Implemented by:** TBD
**Milestone:** Investment Panel

---

## Problem

Import is **append-only**: the planner dedups against what already exists and only ever
*adds* rows. There is no way to wipe the book and start clean, and no way to erase a
*portion* of it (a bad import batch, everything from manual entry, everything before a date).
The user wants a reset they control — "erase everything" and "erase things in parts" — so a
botched import or a pile of stale rows can be cleared without hand-editing `portfolio.json`.

## Solution

A **Danger zone** on the Manage Portfolio page (`app/ui/pages/manage.py`) with two operations,
both behind explicit confirmation and an automatic backup.

1. **Erase everything** — delete all transactions. A checkbox optionally also clears
   `isin_map.json`. Requires the user to tick an explicit "I understand…" confirmation
   checkbox before the button enables. (Originally specced as a typed `ERASE` word; changed
   to a confirmation checkbox per Vivek's review on the CSV-17 branch.)
2. **Scoped erase (in parts)** — delete the subset matching a filter:
   - by **source** (`scalable_csv` vs manual / `source is None`), and/or
   - by **trade-date range** (from / to).
   Preview the count that *would* be deleted before the user confirms.

### Decisions already made — do not re-litigate

- Every erase writes a timestamped backup of `portfolio.json` first (reuse the existing
  workbench backup helper / `data/backups/` rolling window). The success message states the
  backup path so the user can roll back manually.
- Erase operations live in a **service** (`app/services/data_admin.py`, new), pure functions
  over the repository ports. UI only renders and confirms (ARCHITECTURE: no business logic in
  UI).
- Clearing the ISIN map is **opt-in** on the full erase only. Scoped erase never touches the
  map (you might be clearing one batch but keep your mappings).
- This is destructive and intentional — no soft-delete/trash. The backup is the safety net.

### Execution

1. **Service `app/services/data_admin.py`:**
   - `erase_all_transactions(tx_repo) -> int` — count, `save_all([])`, return count.
   - `erase_transactions(tx_repo, *, source: str | None | _Unset, date_from, date_to) -> int`
     — delete matching; return count. Pure, unit-tested with a fake repo.
   - (Map clear stays in the UI via the existing `IsinMapRepository.save(IsinMapDocument())`.)
2. **Backup:** before any erase, write a backup (lift `_write_backup` from
   `import_workbench.py` into a shared helper if it isn't already shared, or call the repo's
   backup path). Do not duplicate the rolling-window logic.
3. **UI Danger zone** in `manage.py`: an expander titled "Danger zone — erase imported data",
   collapsed by default, visually separated. Full-erase block (confirmation checkbox + optional
   "also clear ISIN mappings"); scoped-erase block (source select + date range + live
   "would delete N" preview + confirm).
4. **Tests** in `tests/unit/test_data_admin.py`: full erase empties the book and returns the
   count; scoped erase by source and by date range deletes only the matching subset and
   leaves the rest; empty selection deletes nothing.
5. **Gate.**

## Acceptance criteria

- [ ] `erase_all_transactions` and `erase_transactions` exist in a new `data_admin` service,
      are pure (ports in, count out), and are unit-tested.
- [ ] Full erase requires ticking the confirmation checkbox and writes a backup first.
- [ ] Full erase optionally clears the ISIN map when the checkbox is set; leaves it otherwise.
- [ ] Scoped erase deletes only transactions matching source and/or date range, previews the
      count first, and writes a backup.
- [ ] After any erase the Live Overview / Tax pages render without error.
- [ ] `pytest`, `ruff check .`, `mypy app/`, `lint-imports` clean.

## Files likely touched

- `app/services/data_admin.py` (new), `app/ui/pages/manage.py`
- a shared backup helper (extracted from `app/ui/pages/import_workbench.py` if needed)
- `tests/unit/test_data_admin.py` (new)

## Out of scope

- Per-ISIN purge (that's TICKET-CSV-16's Remove action).
- Undo/restore UI. Rollback is manual via the backup file this writes.
- Erase by ticker (covered well enough by per-ISIN Remove + scoped-by-source/date).

## Notes / assumptions

- Assumes `Manage Portfolio` (`manage.py`) is the right home for destructive data ops (it is
  the "Settings"-band page for editing the book). Confirm the page has room / an obvious
  Danger-zone slot before drafting layout.
- Assumes `TransactionRepository` exposes `load_all` / `save_all` and that `save_all([])` is a
  valid empty-book write that downstream FIFO/valuation handle gracefully (verify the
  empty-portfolio path renders, since some pages may assume ≥1 position).
- Assumes a reusable backup helper exists or can be lifted from the workbench without
  behavioural change.
