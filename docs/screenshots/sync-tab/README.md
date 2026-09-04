# TICKET-SYNC-6B — Sync with Scalable

Captured with the `screenshot-app` skill against an isolated sandbox data dir
(`tools/app_sandbox.sh`), never the real `data/`. Prices in the fixtures are the
real yfinance closes for those dates, so the feed check passes where it should.

| File | Scenario |
|---|---|
| `01_state_a_no_file.png` | State A — no file yet. Last-sync line, Undo disabled (nothing to undo). |
| `02_state_b_all_fine.png` | State B — second sync of a healthy export. "1 new trades imported · 3 already known", "Holdings match this Scalable export (3/3)", holdings table, cash-events line. |
| `03_state_c_tasks.png` | State C — three task kinds at once: a suspicious feed, an unmapped ISIN (`XX…`, no feed), and a share difference from an unpaired security transfer. |
| `04_duplicate_task.png` | Possible-duplicate task — a CSV row matching a hand-typed entry. Nothing is imported for that row until Replace / Keep both is pressed. |
