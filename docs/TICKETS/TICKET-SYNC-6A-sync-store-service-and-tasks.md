# TICKET-SYNC-6A — Sync engine: store port + JSON adapter, sync service, completeness check, task derivation (no UI)

**Priority:** CRITICAL
**Milestone:** Investment Panel
**Recommended model:** Opus — orchestration of writes, snapshots and undo; must respect the layer rules exactly.
**Estimated session length:** 2.5 hr
**Drafted by:** Vivek + Claude (Cowork session 2026-09-03, revised after review)
**Depends on:** TICKET-SYNC-1, TICKET-SYNC-1B, TICKET-SYNC-2, TICKET-SYNC-3, TICKET-SYNC-4, TICKET-SYNC-5.
**Required reading:** `docs/DESIGN/SYNC-TAB.md` and `docs/ARCHITECTURE.md` in full.

> **After this ticket merges:** everything the Sync page needs exists as tested services and adapters: analyse a file, apply the safe part, snapshot + undo both data files byte-for-byte, detect partial files, and turn reconciliation + feed checks into the six task types. No page yet.

## Layer placement (non-negotiable)
- Parsing bytes, temp files, backups, md5, log file: **adapters**.
- Decisions (what is safe, what is a task, what a cause sentence says): **domain**.
- Orchestration with ports as parameters: **services**. No `open`, no `hashlib` on files, no `streamlit`.

## Execution — one commit per step

### Step 1 — parse from bytes (adapter)
`app/adapters/scalable_csv/parser.py`: add `parse_csv_bytes(data: bytes) -> list[ParsedCsvRow]`
(decode `utf-8-sig`, reuse the row loop; `parse_csv(path)` delegates to it). Raise
`ParseError(row_number, "duplicate reference <ref>")` when a non-empty reference appears
twice. Tests in `tests/unit/test_scalable_csv_parser.py`.

### Step 2 — sync store port + adapter
`app/ports/sync_store.py`:
```python
class SyncSnapshot(BaseModel):  # frozen
    id: str; created_at: datetime; portfolio_md5: str; isin_map_md5: str

class SyncStore(Protocol):
    def snapshot(self) -> SyncSnapshot: ...            # copies portfolio.json + isin_map.json into backups_dir/sync/<id>/
    def restore(self, snapshot_id: str) -> None: ...   # os.replace both files back, byte-for-byte; then nav_repo.clear()
    def current_md5s(self) -> tuple[str, str]: ...     # (portfolio, isin_map)
    def append_log(self, entry: dict[str, object]) -> None: ...
    def read_log(self) -> list[dict[str, object]]: ...
```
`app/adapters/sync_store/json_store.py::JsonSyncStore(portfolio_path, isin_map_path, backups_dir, log_path, nav_repo)`.
Keep the 10 newest snapshot folders. Wire `get_sync_store()` in `app/ui/wiring.py`.
Integration test `tests/integration/test_sync_store.py` on `tmp_path`: snapshot → mutate
both files → restore → bytes identical to the snapshot; log round-trips.

### Step 3 — completeness (domain)
`app/domain/sync_completeness.py::check_completeness(rows: Sequence[PlannedRow], book: Sequence[Transaction]) -> CompletenessResult`
(`partial: bool`, `reason: str | None`, `file_start: date | None`, `book_start: date | None`)
using the three rules in the design doc (book start, earlier logged `file_start`, missing
reference); signature gains `earliest_logged_file_start: date | None`. Tests: full file;
later-start file; later than logged start; a book reference missing; empty book (never partial).

### Step 4 — sync service
`app/services/sync.py`:
```python
@dataclass(frozen=True)
class SyncAnalysis:
    plan: ImportPlan; completeness: CompletenessResult
    safe_rows: list[PlannedRow]        # status NEW
    decision_rows: list[PlannedRow]    # status CONFLICT_WITH_MANUAL

def start_session(file_name: str, file_md5: str, store: SyncStore) -> str
    # store.snapshot() BEFORE any write; log {"event": "session_start", "session_id", "snapshot_id", "filename", "file_md5"}; return session_id

def analyse(rows: Sequence[ParsedCsvRow], session_id: str, tx_repo, isin_repo, resolver, company_provider, store: SyncStore) -> SyncAnalysis
    # plan → auto-resolve unmapped ISINs (persist high/medium via isin_repo.save, then rewrite placeholder rows via change_feed;
    # a shared ticker counts as low) → log {"event": "auto_resolve", "session_id", ...} → re-plan
    # analyse never runs before start_session — enforced by requiring session_id.

@dataclass(frozen=True)
class SyncApplied:
    inserted: int; already_known: int; snapshot_id: str | None; log_entry: dict[str, object]

def apply_safe(analysis: SyncAnalysis, session_id: str, tx_repo, store: SyncStore) -> SyncApplied
    # build txs for safe rows (move _build_transaction here, with isin; ticker = proposed_ticker incl. placeholder)
    # → tx_repo.save_all(existing + new) → log {"event": "apply", "session_id", inserted, already_known,
    #   applied_references, partial, file_start, portfolio_md5_after, isin_map_md5_after}. No snapshot here.

def resolve_conflict(row: PlannedRow, choice: Literal["replace", "keep_both"], session_id: str, tx_repo, store: SyncStore) -> None
    # replace: delete row.conflict_tx_id + insert built tx; keep_both: insert built tx. Log with session_id and md5s after.

def change_feed_in_session(isin, ticker, kind, session_id, isin_repo, tx_repo, store, *, allow_shared_ticker=False) -> int
    # SYNC-2 change_feed + isin_repo.save, then log with session_id and md5s after. Used by the Sync page's tasks.

class UndoNotPossible(Exception): ...
def undo_last(store: SyncStore) -> str
    # latest session_id in the log; its session_start entry gives snapshot_id; the session's LAST entry gives the md5s;
    # require store.current_md5s() == those md5s else raise UndoNotPossible;
    # store.restore(snapshot_id); log {"event": "undo", "session_id"}; return session_id
```
Every log entry carries `timestamp`, `event`, `session_id`, `portfolio_md5_after`,
`isin_map_md5_after`. `analyse` on the same bytes twice yields `safe_rows == []` the second
time. A session with zero writes still has its snapshot (cheap; the store keeps 10). Tests `tests/unit/services/test_sync.py`
with fake repos/resolver and a `FakeSyncStore` (`tests/fakes/sync_store.py`): first apply
inserts N, second 0; `apply_safe` never touches conflict rows; `resolve_conflict` both
choices; **undo after auto-resolve + apply + one conflict decision + one feed change restores
the pre-upload bytes of both files**; undo refuses after a Manage-page write; partial file
still inserts safe rows and sets `partial`; first-ever sync (empty book) logs `file_start`
and is never partial; a later file starting after that `file_start` is partial.

### Step 5 — task derivation (domain)
`app/domain/sync_tasks.py::SyncTask(kind: Literal["no_feed","feed_suspicious","shares_differ","sell_exceeds","possible_duplicate","partial_file"], isin, name, headline, detail, impact_eur)`
(`no_feed` = `feed_state == "unmapped"` with shares > 0; its detail says the position is
valued at last trade price and never implies trades are missing)
and `build_tasks(rows, checks, sell_errors, decision_rows, completeness) -> list[SyncTask]`.
Only ISINs with `shares_csv > 0` produce `no_feed`/`feed_suspicious`; `shares_differ` only
when no other task exists for that ISIN; sorted by `impact_eur` desc with `partial_file`
first. Headlines are exactly the design-doc sentences. One test per kind + ordering +
"closed position without feed → no task" + "partial → only the partial task".

### Step 6 — gate, commit, session log, PR.

## Acceptance criteria
- [ ] `lint-imports` clean; no I/O in `app/services/sync.py` or `app/domain/*`.
- [ ] Undo restores both files to the pre-upload bytes after a multi-step session (test) and refuses after a later write.
- [ ] The snapshot is taken before auto-resolve can write (test: auto-resolve persists a mapping, undo removes it).
- [ ] Conflicts are never applied by `apply_safe`.
- [ ] Gate clean.

## Out of scope
Any page; deleting old pages.
