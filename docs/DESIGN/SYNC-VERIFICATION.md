# Sync tab — verification checklist (for the reviewing session after SYNC-1..7)

Run this in a fresh session **after all seven SYNC PRs are merged**. Read
`docs/DESIGN/SYNC-TAB.md` and `docs/DECISIONS/ADR-014-isin-identity-ticker-derived.md`
first. Report each item as PASS / FAIL with the file and line that proves it. Do not fix
anything in this session — file tickets for failures.

## A. Code facts (read, grep, no app launch)
1. `app/ui/pages/import_workbench.py` and `app/ui/pages/mappings.py` do not exist; sidebar
   has `sync` and no `import_workbench` / `mappings`.
2. `run_sync` in `app/services/sync_import.py` passes `isin=row.isin` when building
   transactions (grep `isin=`).
3. `JsonTransactionRepository.load_all` does **not** read the ISIN map; `change_feed` in
   `services/isin_remap.py` rewrites rows and raises `TickerAlreadyMappedError`.
4. `_tx_sig` in `services/valuation.py` includes tickers.
5. `manage.py` branches on `is_broker_row` and the broker edit form only writes `notes`.
6. `app/domain/feed_check.py`, `app/domain/reconcile.py`, `app/domain/sync_tasks.py`
   import nothing outside stdlib / pydantic / `app.domain` (also confirm `lint-imports`).
7. Thresholds match the design doc: 15 %, last 3 trades, mean for 2, transfer sign rule.
8. `undo_last` compares both md5s; `JsonSyncStore.restore` uses `os.replace` on both files
   then `nav_repo.clear()`; no load-and-resave anywhere in the undo path.
9. `app/services/sync.py` and `app/domain/*` contain no `open(`, `hashlib`, `os.`, `streamlit`.
10. `apply_safe` never touches rows with status `conflict_with_manual`.
11. `plan_import` never emits `UNMAPPED_ISIN` / `IGNORED_ISIN`; unmapped rows get `proposed_ticker == isin`.
12. `start_session` snapshots before `analyse` can write; `undo_last` restores the session's
    `session_start` snapshot, not the last action.
13. `change_feed` rewrites transactions before the caller saves the map; `check_consistency` +
    `repair` exist and `repair` is idempotent (test).
14. Manage page: Delete is disabled when a Scalable row is selected.

## B. Data facts (read-only python over `data/`; print counts, change nothing)
1. Count `scalable_csv` transactions with `isin is None` — expected 0.
2. Count transactions whose `id` starts with `SCAL` and `source != "scalable_csv"` — expected 0.
3. For every `scalable_csv` transaction with a mapped ISIN, stored `ticker` equals the
   mapping's ticker — list any mismatch. For unmapped/ignored ISINs, stored `ticker == isin`.
5. The count of executed Buy/Sell/Savings-plan rows in Vivek's latest CSV equals the count of
   `scalable_csv` transactions with those references — every trade is in the book.
4. `import_log.json`: the last entry has `applied_references`, `backup_path`,
   `portfolio_md5_after`.

## C. Behaviour (sandbox via `tools/app_sandbox.sh` + screenshot-app skill; never real data)
1. Upload the fixture CSV twice: first run inserts N > 0, second inserts 0 and shows the
   same holdings.
2. Fixture with one unmapped ISIN with open shares → exactly one task, headline `No price
   feed for …`; map it through the task → task disappears, row matches, no page change.
3. Fixture with a closed position with no feed → no task; it appears under All instruments.
4. Map an ISIN to a deliberately wrong ticker → the task `Price feed for … looks wrong`
   appears with the two averages in the detail.
5. Undo after a sync restores `portfolio.json` **and** `isin_map.json` byte-for-byte; the
   button is disabled after a manual-trade add on the Manage page or a mapping change.
8. A manual trade content-matching a CSV row → `Possible duplicate` task, nothing inserted
   for it until Replace / Keep both is pressed.
9. A date-range (partial) export → the partial task, new rows imported, no holdings sentence.
10. Mapping a second ISIN to an already used ticker is refused until the checkbox is ticked.
11. Fixture with one unmapped ISIN: shares match immediately; the Overview shows the position
    at last trade price with the label; after choosing a feed the shares are unchanged and
    only ticker/price change.
12. Undo after upload + auto-resolve + a conflict decision + a feed change returns both files
    to the pre-upload bytes (compare md5s before and after).
6. On Manage Portfolio, editing a Scalable row offers only Notes; the caption points to the
   Sync tab.
7. No "blocked" count, no status chips, no Apply button anywhere.

## D. Numbers (the actual goal)
Against Vivek's real CSV (he runs it; you read his pasted screen text): the holdings table
shows every open position with `Shares Scalable == Shares dashboard`, the sentence
"Holdings match this Scalable export", and no tasks. If any row differs, the cause sentence
must name one of causes 1–8 in SYNC-5 — "unknown" is a FAIL. Market values are labelled as
estimates with provider and timestamp.
