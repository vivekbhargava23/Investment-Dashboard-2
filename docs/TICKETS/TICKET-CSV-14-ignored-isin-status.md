# TICKET-CSV-14 — `ignored` ISIN status: skip rows from CSV permanently

**Priority:** MEDIUM
**Estimated session length:** 2 hr
**Recommended model:** Sonnet — schema change with migration, importer behaviour change, Mappings UI, and tests across all three layers. Coordinated but well-scoped.
**Drafted by:** Vivek + Claude Chat (2026-06-05)
**Implemented by:** TBD
**Milestone:** Investment Panel

---

## Problem

Some ISINs in Vivek's Scalable CSV will never be mapped to a real ticker because the underlying securities aren't worth tracking in this dashboard (crypto ETPs, knockout certificates with no relevant yfinance symbol, etc.). Today these sit forever in the "Unmapped ISINs" section of the Mappings page and re-appear in every fresh CSV import. The only way to make them stop nagging is to map them to a real ticker — which is wrong, because there is no real ticker.

Concrete observation on 2026-06-05 against `main` — the user wants these five permanently ignored:

- `CH0491507486` — 21shares Tezos ETP Staking
- `CH1109575535` — 21shares Stellar ETP
- `CH1129538448` — 21shares Polygon ETP
- `GB00BNRRF105` — CoinShares Physical Staked Algorand
- `DE000HT41XN9` — Apple Short 205,22 $ Turbo Open End HSBC

Today the importer treats every unmapped ISIN as either "new — add as unmapped" or "still unmapped — skip and report." Both paths log the ISIN to `summary.unmapped_isins`, which surfaces in the Import Workbench and Mappings page. The user has no way to say "this one is dead, don't ever mention it again."

## Solution

Extend the existing ISIN map schema with a third status, `"ignored"`. The CSV importer treats ignored ISINs the same way it treats mapped-but-skipped rows today — silently dropped, *not* counted in `summary.unmapped_isins`. The Mappings page gains an "Ignore" action on every unmapped row that flips its status to `"ignored"`, plus a collapsed "Ignored ISINs" section where the user can restore an entry to `"unmapped"` if they change their mind.

### Decisions already made — do not re-litigate

- The new status lives on the existing `IsinMapping.status` literal. **Do not** introduce a separate `ignored_isins: set[str]` field on `IsinMapDocument` — two places to look is worse than one place with three states.
- Ignored entries are still persisted to `isin_map.json`. We want a record of which ISINs were consciously ignored, including `name` and `last_seen_in_csv`.
- `ignored` is a terminal state for the importer's purposes (skipped, no counters bumped), but the user can move an entry back to `unmapped` from the UI. Moving `ignored → mapped` directly is also allowed (the user found a real ticker after all).
- Existing `mapped` and `unmapped` semantics are unchanged. No migration is needed beyond bumping the schema version, because the new status is additive on a `Literal`.
- ISIN map schema version bumps to `2`. The schema-1 → schema-2 migration is trivial: read, validate, write back — no field changes are required. We still add the migration so the version-bump path is exercised and future schema changes have a precedent.
- An ignored ISIN appearing in a fresh CSV does **not** auto-flip back to unmapped. Ignored means ignored until the user changes it.

---

## Execution order — one commit per step, tests pass between

### Step 1: Extend the schema

**File:** `app/domain/isin_map.py`

Change:

```python
status: Literal["mapped", "unmapped"]
```

to:

```python
status: Literal["mapped", "unmapped", "ignored"]
```

Bump `IsinMapDocument.version` default from `1` to `2`.

Add a docstring on the model noting the three statuses and their semantics:

- `mapped` — `ticker is not None`, used by importer to attach to transactions.
- `unmapped` — `ticker is None`, surfaced in the Mappings page for the user to resolve.
- `ignored` — `ticker is None`, rows for this ISIN are skipped by the importer with no warning and no counter bump.

No validator changes. `ticker` may be `None` for both `unmapped` and `ignored`.

### Step 2: Migration for isin_map.json

**File:** `app/adapters/isin_map/repo.py`

Add `_migrate_v1_to_v2(data: dict) -> dict`. The migration is a no-op on entries (the new status is additive) but does:

1. Set `data["version"] = 2`.
2. Return `data`.

In `JsonIsinMapRepository.load()`, if the loaded `data["version"]` is `1`, run the migration, then call `IsinMapDocument.model_validate(data)`. After validation, write the migrated document back to disk via the same atomic-write pattern used in `save()` (tmp + fsync + replace). Atomic write on first load ensures we don't re-migrate on every startup.

Bump `JsonIsinMapRepository.SCHEMA_VERSION` from `1` to `2`.

Tests in `tests/unit/adapters/isin_map/test_repo.py` (extend or create):

- `test_load_migrates_v1_to_v2`: write a v1 fixture, load via `JsonIsinMapRepository.load()`, assert the returned document has `version == 2` and matching entries. Assert the on-disk file has been rewritten with `version: 2`.
- `test_load_v2_no_migration`: write a v2 fixture, load, assert no rewrite happened (`mtime` unchanged).
- `test_load_ignored_status_roundtrip`: write a v2 fixture with one `ignored` entry, load it, assert the entry survives with `status == "ignored"`.

### Step 3: Importer skips `ignored` ISINs silently

**File:** `app/adapters/scalable_csv/importer.py`

Current flow (around lines 196–220):

- If `mapping is None` for an ISIN: add as `unmapped`, record in `summary.unmapped_isins`, increment `summary.unmapped`, continue.
- If `mapping.status == "unmapped"`: record in `summary.unmapped_isins`, increment `summary.unmapped`, continue.

Add the new branch **before** both:

```python
if mapping is not None and mapping.status == "ignored":
    # Ignored ISINs are skipped silently. No counter bump, no summary entry.
    continue
```

Place the check after the `mapping = entries.get(row.isin)` lookup and before the `mapping is None` branch. The `ignored` branch must also update `last_seen_in_csv` on the entry (so the user can see when the ignored security last appeared in a CSV), but **not** flip the status back. Add a small helper or inline the model_copy:

```python
entries[row.isin] = mapping.model_copy(update={"last_seen_in_csv": row.date})
```

The `ImportSummary` dataclass does not change. We deliberately do not add `ignored_count` — the user explicitly does not want these surfaced anywhere.

Tests in `tests/unit/test_scalable_csv_importer.py`:

- `test_ignored_isin_is_skipped_silently`: build a CSV with one row whose ISIN is pre-populated in the isin_map as `ignored`. Run the importer. Assert: no new transactions for that ISIN; `summary.unmapped == 0`; `summary.unmapped_isins == []`; the ignored entry's `last_seen_in_csv` is updated to the row's date.
- `test_ignored_isin_does_not_become_unmapped`: same fixture, but check that the entry's status stays `ignored` after import (not flipped back to `unmapped`).
- Existing `test_unmapped_isin_*` tests must still pass — the `unmapped` path is unchanged.

### Step 4: Mappings page — "Ignore" action on unmapped rows

**File:** `app/ui/pages/mappings.py`

In `_render_unmapped_section`, change the column layout from `[2, 2, 2, 2, 1]` to `[2, 2, 2, 2, 0.7, 0.7]` to fit two action buttons (Save + Ignore). Add an "Ignore" button in the new column:

```python
with col_ignore:
    if st.button("Ignore", key=f"mappings_ignore_unmapped_{isin}"):
        new_entries = dict(doc.entries)
        new_entries[isin] = mapping.model_copy(update={"status": "ignored"})
        get_isin_map_repo().save(IsinMapDocument(version=doc.version, entries=new_entries))
        st.session_state.mappings_feedback = ("success", f"Ignored {isin} ({mapping.name}). Future CSV rows for this ISIN will be skipped silently.")
        st.rerun()
```

Naming: column variable is `col_ignore`. The Save button stays where it is; the new Ignore button sits to its right.

### Step 5: Mappings page — "Ignored ISINs" section

**File:** `app/ui/pages/mappings.py`

After `_render_mapped_section`, add `_render_ignored_section(ignored: dict[str, IsinMapping], doc: IsinMapDocument) -> None`:

- Use `st.expander("Ignored ISINs", expanded=False)`.
- Caption: "These ISINs were intentionally ignored. CSV rows for them are skipped silently. Click Restore to move one back to Unmapped."
- For each entry: show ISIN (`st.code`), name, last seen date, and a single "Restore" button.
- Restore flips status back to `"unmapped"` and clears the entry's `instrument_kind` (defensive — ignored entries shouldn't have a kind, but if one was somehow set, we drop it).

In `render()`, build the `ignored` dict alongside `mapped` and `unmapped` and pass it to the new section. Update the counts caption at the top to include `· N ignored` when non-zero:

```python
caption = f"{len(mapped)} mapped · {len(unmapped)} unmapped"
if ignored:
    caption += f" · {len(ignored)} ignored"
if unclassified:
    caption += f" · ⚠ {unclassified} missing Tax kind"
```

The Ignored section renders only when `ignored` is non-empty (the same pattern the Unmapped section uses).

Tests in `tests/unit/ui/test_mappings_page.py`:

- `test_ignore_button_flips_unmapped_to_ignored`: render with one unmapped entry, click Ignore, assert the saved doc has that entry with `status == "ignored"`, success feedback set.
- `test_restore_button_flips_ignored_to_unmapped`: render with one ignored entry, click Restore in the expander, assert the saved doc has `status == "unmapped"` and `instrument_kind is None`.
- `test_unmapped_section_hidden_when_only_ignored_present`: render with zero unmapped and one ignored entry. Assert the Unmapped section header is not rendered; the Ignored section is rendered.

### Step 6: Import Workbench

**File:** `app/ui/pages/import_workbench.py`

Check whether the workbench surfaces `summary.unmapped_isins` independently. If so, no change is required — ignored ISINs were never added to that list in Step 3, so they naturally disappear. If the workbench reads `isin_map.json` directly to display unmapped entries, exclude `status == "ignored"` from the displayed unmapped list there as well.

Grep first: `grep -n "unmapped" app/ui/pages/import_workbench.py`. If only `summary.unmapped_isins` is read, no edit needed.

### Step 7: Backfill convenience — set the user's five ISINs to `ignored`

The user explicitly listed five ISINs to ignore. After the code is merged and the migration has run, Vivek will use the UI to ignore each one. **Do not bake the five ISINs into a migration or hardcode them anywhere.** The list is user data; the UI is the right tool to apply it.

Mention this in the PR description: "After merge, Vivek can flip the five ISINs listed in the ticket via Mappings → Unmapped → Ignore."

---

## Acceptance criteria

- [ ] `IsinMapping.status` literal extended to `"mapped" | "unmapped" | "ignored"`.
- [ ] `IsinMapDocument.version` default is `2`.
- [ ] `JsonIsinMapRepository.load()` migrates `v1 → v2` on first read and atomically rewrites the file.
- [ ] CSV importer skips `ignored` ISINs silently — no counter, no `summary.unmapped_isins` entry — and updates `last_seen_in_csv`.
- [ ] Mappings page Unmapped section has an "Ignore" button per row.
- [ ] Mappings page has an "Ignored ISINs" expander with a "Restore" button per row.
- [ ] Mapped, Unmapped, and Ignored counts shown in the page caption.
- [ ] All new tests pass; all existing tests still pass.
- [ ] `ruff check .`, `mypy app/`, `lint-imports` all pass.

### Manual smoke (post-merge, by Vivek)

- Open the Streamlit app. Mappings page → confirm the new "Ignore" button on each unmapped row.
- Ignore each of the five ISINs in the ticket. Confirm they move from Unmapped into the new Ignored expander.
- Trigger a re-import of the same Scalable CSV. Confirm:
  - The Import Workbench summary does not mention the five ignored ISINs.
  - The Mappings page Unmapped section does not re-add them.
  - No new transactions are created for any of them.
- Open the Ignored expander → click Restore on one entry → it moves back to Unmapped with no Tax kind set.
- Inspect `data/isin_map.json` on disk → confirm `version: 2` and the ignored entries have `status: "ignored"`.

---

## Out of scope

- Bulk "Ignore all" or "Restore all" actions. One row at a time is fine; the user has five entries to handle.
- Auto-ignoring entries based on heuristics (e.g. "ISIN looks like a knockout cert"). Manual decision only.
- Surfacing ignored counts in the Import Workbench summary. The whole point is that ignored is silent.
- Reflecting `ignored` status anywhere on the Live Overview or Tax pages. Those pages read from `portfolio.json`, which by definition contains no transactions for ignored ISINs (they're skipped at import).
- Schema versioning for the on-disk `IsinMapDocument` beyond v2. Future statuses or fields will get their own migration tickets.

---

## Notes / assumptions

- Assumes the existing `app/adapters/isin_map/repo.py` does not yet have a versioned migration pattern (it currently calls `IsinMapDocument.model_validate` directly without a version check). The Step 2 migration introduces the pattern; mirror the v1→v2 atomic-write style from `app/adapters/repo_json/migration.py` (`tmp` + `fsync` + `os.replace`).
- Assumes no other code reads `isin_map.json` outside `JsonIsinMapRepository`. Quick grep before editing: `grep -rn "isin_map.json" app/`. If anything bypasses the repository, file a follow-up to route it through the repo before this migration ships.
- The five ISINs the user wants ignored are listed in the Problem section as the canonical post-merge smoke list. Do not hardcode them.
- `instrument_kind` on an `ignored` entry: we clear it on Restore (Step 5). We do not clear it on Ignore — it's harmless to keep the existing classification if the user later restores the entry. Document this in a code comment near the Ignore button so future readers don't "fix" it.
- The status literal change is the only model change that could break callers. Quick grep before merging: `grep -rn 'status == "mapped"\|status == "unmapped"' app/ tests/`. Each call site should be reviewed to confirm it handles the new third state correctly (most will already be fine because they pattern-match on the two it cares about, but the Mappings page renderers explicitly need to partition all three).
