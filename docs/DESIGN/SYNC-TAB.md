# Sync tab — design and execution plan

**Drafted by:** Vivek + Claude (Cowork session 2026-09-03)
**Status:** Revised twice 2026-09-03 after external review; approved for execution once Vivek files the SYNC tickets
**Replaces:** Import CSV workbench + ISIN Mappings tab (retired in TICKET-SYNC-7)

## Goal (the only success criterion)

After uploading the current Scalable Capital CSV, every number on the dashboard equals
Scalable, with the fewest clicks, and every intervention is a one-line task anyone can
understand without knowing how the app works.

## Four principles

1. **The CSV is the book. The ISIN is the identity.** A ticker is only the *price feed*
   used to value an ISIN. Tickers are never edited on transactions; the ISIN→feed mapping
   is edited once and the mapping write rewrites every transaction with that ISIN (ADR-014).
2. **The app decides when a feed is wrong.** Each CSV trade carries the EUR price Scalable
   charged. Compare it to the feed's close on that date (in EUR). Median deviation over the
   last 3 trades > 15 % → "feed looks wrong". No feed → "no feed". Nothing else is a task.
3. **Only ask about things that change a number on screen.** Tasks are only raised for
   ISINs with an open position (shares per CSV > 0). Closed positions without a feed sit in
   a collapsed section (they only affect tax history). Cash events (Deposit, Withdrawal,
   Distribution, Interest, Taxes) and cancelled/expired/rejected rows are information, never
   "blocked".
3b. **Shares match the moment the file is in.** Every executed trade is imported whether or
   not a price feed exists; a missing feed only affects valuation (last trade price is used
   and labelled). Picking a feed never changes which trades are in the book.
4. **Import is automatic where it is safe, and undoable.** Rows that are new by exact
   Scalable `reference` are imported on upload with no further click. Anything that needs a
   decision (a row that looks like a duplicate of a manual entry, a partial file) is shown
   as a task and applied only when the user chooses. One "Undo last sync" restores
   `portfolio.json` and `isin_map.json` together, byte-for-byte, to the state **before the
   file was uploaded** — the snapshot is taken before anything (including auto-resolve)
   writes, and every action taken while that file is open belongs to the same sync session.
5. **Holdings can match Scalable; market values cannot be promised.** Shares and cost come
   from the broker file. Prices and FX come from independent providers, so the screen says
   "Holdings match this Scalable export" and, separately, "Market values are estimates from
   yfinance as of <timestamp>".

## The screen (page id `sync`, label "Sync with Scalable")

**State A — no file.** Drop zone + one line: `Last sync: <date> · <n> trades · holdings
matched Scalable` (or `… <k> holdings differed`). Nothing else.

**State B — file dropped, everything fine.** The import already happened. One card:

    ✅ 20 new trades imported · 196 already known · Holdings match this Scalable export (17/17)
    Market values are estimates from yfinance as of 03 Sep 2026 19:20.
    [Undo last sync]

Then the **holdings table** (one row per ISIN with shares > 0 in CSV or in book):
`Name (Scalable) · Shares Scalable · Shares dashboard · Feed (ticker · ccy) · Feed check ·
Tax kind`. Shares only — cost per open lot including fees is not derivable from the CSV, so
cost is shown from the book and not compared. Selecting a row shows an action bar: **Change feed** (search box + kind
selector + Save) and **Ignore**. Saving a feed change re-runs the import of the current
file automatically so previously skipped rows come in.

**State C — something needs you.** Same screen; a numbered **task list** above the table,
ordered by |shares diff × last trade price| descending. Task types (exactly these six):

| Task | Trigger | Action shown |
|---|---|---|
| No price feed for *Name* (n shares, valued at last trade price) | ISIN unmapped, shares_csv > 0 | inline mapper row (search + kind + Save) · Ignore (= keep last-trade valuation, stop asking) |
| Price feed for *Name* looks wrong — your trades avg €x, feed *T* closed €y | FeedCheck.status == suspicious | inline mapper row prefilled placeholder = CSV name |
| Shares differ: *Name* — Scalable a, dashboard b | reconcile diff ≠ 0 | text only, with the cause sentence |
| Sell exceeds shares held: *Name* | FIFO raises for that ISIN | text only, with the cause sentence |
| Possible duplicate: *Name* on *date* matches a manual entry | planner status `conflict_with_manual` | **Replace with Scalable row** · **Keep both** (nothing applied until chosen) |
| This file looks partial (starts *date*; your book starts *date*) | completeness check fails | text only: new trades were imported, holdings comparison skipped |

Below the table: `Cash events in this file: €d dividends · €i interest · €t taxes` (from
the current CSV only, not stored). At the bottom, one collapsed expander **Details**: raw
CSV table, per-row plan status table, last 5 import-log entries. A second collapsed
expander **All instruments** holds the old Mappings page content (mapped / ignored / closed
positions) with Change feed · Kind · Ignore · Restore · Remove.

## What disappears

Import CSV workbench page, ISIN Mappings page, plan/review/apply step, status chips,
"blocked" counts, conflict radios, exclude checkboxes, auto-resolve reject flow, ticker
editing on Scalable rows in Manage Portfolio. Manage Portfolio keeps: manual trades (other
brokers), notes edits, delete, danger zone.

## Thresholds and rules (fixed — do not re-litigate in tickets)

- Completeness: a file is **partial** if its earliest row date is later than the earliest
  `scalable_csv` trade in the book, or later than the `file_start` recorded by any earlier
  sync, or if any `csv_reference` in the book is absent from the file. Partial files still
  import new rows; reconciliation and the feed check are skipped and the partial task is
  shown. On the first-ever sync (empty book) nothing can be checked: the card says
  "First sync — make sure the export covers all time" and `file_start` is logged for later
  comparison. Two identical `reference` values in one file → parse error, nothing imported.
- Import scope: every row with status Executed and type Buy / Savings plan / Sell is
  imported, ticker = mapping ticker if `mapped`, else the ISIN itself. `ignored` and
  `unmapped` are valuation states, not import filters.
- Sync session: one snapshot per uploaded file, taken before the first write (auto-resolve
  included). Auto-resolve, safe apply, conflict decisions and feed changes made while the
  file is open all log the same `session_id`. "Undo last sync" restores that session's
  snapshot.

- Feed check is a **warning, not proof of identity**: last 3 scalable trades per ISIN;
  deviation = |csv_price − close_eur| / close_eur. Central value = median for 3, mean for 2,
  the value itself for 1. `ok` if ≤ 15 %, `suspicious` if > 15 %, `no_feed` if no close
  could be fetched for any trade, `unchecked` if the ISIN has no mapped ticker. The UI always
  shows both averages so the user judges.
- Reconcile expected shares per ISIN from the CSV: Executed rows only; Buy and Savings
  plan add `shares`; Sell subtracts; Security transfer adds `shares` as signed in the file
  (inbound positive, outbound negative). Net transfer ≠ 0 for an ISIN → cause
  "transfer imbalance".
- Book shares per ISIN = Σ buy − Σ sell over transactions with that `isin`.
- Rows whose content matches a manual transaction are **never applied automatically**;
  they become the "Possible duplicate" task.
- Mapping guard: a ticker already used by another `mapped` ISIN is refused unless the user
  ticks "same instrument (ISIN change)".
- Undo is offered only for the last session and only while `md5(portfolio.json)` and
  `md5(isin_map.json)` still equal the values recorded by that session's latest log entry.
  Undo copies both snapshot files back (`os.replace`), clears the NAV cache and Streamlit
  caches; it never loads-and-resaves.
- Mapping change order: rewrite transactions, then save the map, both inside the session
  snapshot. On page load a consistency check (stored ticker == map ticker for every mapped
  ISIN) shows a one-click **Repair** that re-runs the rewrite when they differ.

## Execution order (one ticket = one branch = one PR)

| # | Ticket | Model | What it unlocks |
|---|---|---|---|
| 1 | TICKET-SYNC-1 stamp ISIN on import + repair backfill tool | Sonnet | every later step needs `isin` on every scalable row |
| 1B | TICKET-SYNC-1B always import executed trades; placeholder ticker; last-trade valuation | Opus | shares match without a feed |
| 2 | TICKET-SYNC-2 mapping write path: rewrite + guard + cache keys (ADR-014) | Sonnet | "change once, applies everywhere" |
| 3 | TICKET-SYNC-3 Manage: broker rows are read-only except notes | Sonnet | closes the wrong door |
| 4 | TICKET-SYNC-4 feed verification service | Sonnet | "feed looks wrong" task |
| 5 | TICKET-SYNC-5 reconciliation service | Sonnet | "shares differ" task + holdings table |
| 6a | TICKET-SYNC-6A sync store port/adapter, sync service, completeness check, task derivation | Opus | all logic, no UI |
| 6b | TICKET-SYNC-6B the Sync page | Sonnet | the user-facing screen |
| 7 | TICKET-SYNC-7 retire workbench + mappings pages (after two real syncs) | Haiku | one door |

After 1 merges, Vivek runs the backfill on real data (steps in SYNC-1). After 6b merges,
Vivek uses the Sync tab for two real exports before 7. After 7 merges, a Fable 5.1 session
runs `docs/DESIGN/SYNC-VERIFICATION.md`.

## Deferred (own ADR if a real case appears)
FIFO / cost basis / realised gains keyed by ISIN instead of ticker; a multi-signal feed
confidence score (name, quote type, exchange, corporate actions).
