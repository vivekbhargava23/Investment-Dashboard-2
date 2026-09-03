# TICKET-SYNC-2 — Mapping write path: rewrite every row, guard shared tickers, invalidate caches (ADR-014)

**Priority:** CRITICAL
**Milestone:** Investment Panel
**Recommended model:** Sonnet — small, fully specified changes in services, wiring and one page.
**Estimated session length:** 1 hr
**Drafted by:** Vivek + Claude (Cowork session 2026-09-03, revised after review)
**Depends on:** SYNC-1 and SYNC-1B merged. Read `docs/DECISIONS/ADR-014-isin-identity-ticker-derived.md` in full first.

> **After this ticket merges:** changing an ISIN→ticker mapping rewrites every transaction with that ISIN in the same operation, refuses to merge two different instruments by accident, and every cached view invalidates. The repository is untouched — reads return stored facts.

## Execution — one commit per step

### Step 1 — one service function for "change the feed of an ISIN"
File `app/services/isin_remap.py`, add:
```python
class TickerAlreadyMappedError(Exception):
    def __init__(self, ticker: str, other_isin: str) -> None: ...

def change_feed(isin: str, ticker: str, kind: InstrumentKind, isin_doc: IsinMapDocument,
                tx_repo: TransactionRepository, *, allow_shared_ticker: bool = False) -> tuple[IsinMapDocument, int]:
    """Set (ticker, kind, status='mapped') for isin, rewrite every tx with that isin, return (new_doc, rewritten_count).
    Raises TickerAlreadyMappedError if another mapped ISIN already uses `ticker` and allow_shared_ticker is False."""
```
Body: guard → build entry (`name=existing.name if existing else isin`,
`last_seen_in_csv=existing.last_seen_in_csv if existing else None`) →
`rewrite_ticker_for_isin(tx_repo, isin, ticker)` → return. **Write order is fixed:
transactions first (inside `change_feed`), then the caller saves the map.** If the map save
fails, stored tickers are ahead of the map; `check_consistency` detects it and `repair`
re-runs the rewrite, which is idempotent. Also add:
```python
def check_consistency(isin_doc, txs) -> list[tuple[str, str, str]]   # (isin, map_ticker, stored_ticker) mismatches
def repair(isin_doc, tx_repo) -> int                                  # rewrite every mapped ISIN; returns rows changed
```
Placeholder rows (ticker == ISIN, SYNC-1B) are rewritten by the same call.

Tests `tests/unit/services/test_isin_remap.py` (create; add an in-memory
`FakeTransactionRepository` in `tests/fakes/repository.py` if none exists): rewrite count;
guard raises; guard bypassed with `allow_shared_ticker=True`; ISIN with no transactions → 0;
`check_consistency` finds a mismatch and `repair` fixes it (second call → 0).

### Step 2 — both UI save paths use it
`app/ui/pages/mappings.py` (`_render_unmapped_section` save, `_render_edit_row` save) and
`app/ui/pages/import_workbench.py` (manual Save in `_render_autoresolve_panel`): replace the
`build_mapping`/`_save_mapping` + `rewrite_ticker_for_isin` sequence with `change_feed(...)`
then `get_isin_map_repo().save(new_doc)`. On `TickerAlreadyMappedError` show
`st.warning("<ticker> is already the feed for <other isin>. Tick 'Same instrument (ISIN change)' to merge on purpose.")`
next to a checkbox `Same instrument (ISIN change)` whose value is passed as
`allow_shared_ticker`. Auto-resolve (`_run_autoresolve`) must also refuse a shared ticker:
treat that result as `low` confidence (not persisted).

### Step 3 — caches
`app/services/valuation.py::_tx_sig` becomes
`f"{len(transactions)}:{hashlib.sha1('|'.join(sorted(f'{tx.id}:{tx.ticker}' for tx in transactions)).encode()).hexdigest()[:12]}"`.
Grep `app/services/nav.py`, `app/ui/cache_keys.py`, `app/ui/pages/overview.py` for keys built
from ids only and apply the same rule; list the hits in the PR. After every mapping save in
Step 2 call `st.cache_data.clear()` and `clear_caches(get_price_provider(), get_live_fx_provider())`.

### Step 4 — wiring
`app/ui/wiring.py::get_repository`: pass `isin_map_path=Path(settings.isin_map_json_path)`
(used only by the v2→v3 migration). Add a test asserting `load_all` returns the stored ticker
even when the map says otherwise — the repository must never derive.

### Step 5 — repair surface
`app/ui/pages/mappings.py::render`: call `check_consistency`; if non-empty show
`st.warning("n mapping(s) are out of sync with the book")` and a **Repair** button that calls
`repair`, clears caches, reruns. (SYNC-6B moves this to the Sync page.)

### Step 6 — gate, commit, session log, screenshot of the guard warning, PR.

## Acceptance criteria
- [ ] After a mapping change, `portfolio.json` shows the new ticker on every row with that
      ISIN and the Live Overview shows it without restart.
- [ ] Mapping a second ISIN to an existing ticker is refused until the checkbox is ticked.
- [ ] `JsonTransactionRepository.load_all` has no reference to the ISIN map.
- [ ] Gate clean.
