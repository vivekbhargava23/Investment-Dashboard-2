# TICKET-SYNC-7 — visual verification

Driven with Playwright against an isolated sandbox data dir seeded with **copies**
of the real `data/portfolio.json` and `data/isin_map.json`; the real `data/` was
never touched.

**Deviation from the ticket's Step 9:** the upload is the real September export
(`2026-09-03_21-02-01_ScalableCapital-Broker-Transactions.csv`), not the May
snapshot committed as `data/scalable_raw.csv`. The book was built from the
September file, so the May one is correctly flagged partial and skips the
reconciliation this step is meant to check. Both files carry the same knock-out
pair for `DE000HT41XN9`.

| Screenshot | What it shows |
|---|---|
| `01-upload-knockout-imported.png` | The export dropped in: 7 new trades, **Holdings match this Scalable export (39/39)**, the cash line ending `· €0,03 corporate actions`, and the instrument card on a task — feed state in words, Save feed, **Use last trade price**, Tax kind, Write off. The sidebar's SETTINGS section is Sync + Manage only. |
| `02-all-instruments.png` | The holdings table with its feed-check column, and the **All instruments** expander: `34 with a feed · 3 closed without one · 2 valued at last trade price`, with the Mapped table, Closed-no-feed and the Restore list. |
| `03-reupload-zero-new.png` | The same file uploaded again: **0 new trades imported · 220 already known**, still 39/39. The knock-out reconciles at 0 on both sides. |
| `04-write-off.png` | The write-off confirm (date + shares) and the feedback: *Wrote off 16 Japan Steel Works at €0 on 2026-09-05. The loss shows on the Tax Dashboard under Aktie.* **Undo last sync** is still enabled behind it. |
| `05-manage-write-off-row.png` | The write-off on Manage Portfolio: `J9R.F · SELL · 16 · €0.00`, Source **write-off**, notes `write-off: Japan Steel Works`. |
| `06-tax-dashboard.png` | The Tax Dashboard computing on the post-import book — the page that was down before this chain. |
| `07-live-overview.png` | Live Overview: 25 positions, **no Apple Short turbo row**. Before this ticket it held 26 phantom shares valued at €78 of last-trade price. |

## What was checked by driving the app, beyond the screenshots

- Changing only the tax kind on a card rewrote `isin_map.json` and left
  `portfolio.json` byte-identical, and **Undo last sync** stayed enabled.
- **Use last trade price** and **Write off** both left undo enabled, and undo
  restored both files to their pre-upload md5s (the write-off row was gone).

Two things are covered by unit tests rather than a click: selecting a row inside
the All-instruments tables (Streamlit paints those grids to a canvas, which
Playwright cannot address headlessly — the card behind the selection is the same
code path the task cards exercise here), and the write-off row being deletable on
Manage (`is_broker_row` is False for it, which is what the Delete button reads).
