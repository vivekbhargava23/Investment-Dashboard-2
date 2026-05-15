# TICKET-CSV-6 — Operational: re-import existing CSV through the workbench

**Status:** QUEUED
**Priority:** MEDIUM (becomes HIGH once CSV-4 + CSV-5 merge)
**Estimated session length:** 15-30 min operational, no code
**Drafted by:** Vivek + Claude (chat session 2026-05-15)
**Implemented by:** Vivek (operational, hands-on)
**Milestone:** Foundation
**Depends on:** TICKET-CSV-4 (workbench shipped), TICKET-CSV-5 (native-currency support shipped)

## Problem

After CSV-4 ships, the migration runs automatically on first launch and tags existing transactions with `csv_reference` and `source`. After CSV-5 ships, the importer can handle USD/JPY/etc. tickers natively. At that point, the portfolio is *capable* of containing the missing 70+ transactions (NVDA, DELL, NOW, etc.) — but they're not in it yet, because nobody has run the import.

This ticket is the operational step to do that run. No code. Just a checklist Vivek follows, and a verification step at the end.

## Pre-flight checklist

Before starting:

- [ ] CSV-4 merged to main, the migration script has run successfully on launch (check `data/portfolio.v1.pre-migration.json.bak` exists; check `portfolio.json` schema version is 2; check logs for migration summary).
- [ ] CSV-5 merged to main.
- [ ] Current `portfolio.json` has been backed up manually outside the app (copy to `~/Desktop/portfolio.{date}.json` or similar — belt and suspenders, the workbench will also backup but extra safety is cheap).
- [ ] `data/scalable_raw.csv` is the latest export from Scalable Capital. Re-download from Scalable if it's been more than a week since you last did so.
- [ ] `data/isin_map.json` contains all 27 ISINs from the CSV. If any are still `status: "unmapped"` for tickers you actually hold, resolve them first via the Mappings page or inline in the workbench during this step.

## The run

1. Open the app, navigate to **Tools → Import CSV**.
2. Upload `data/scalable_raw.csv`.
3. Verify the **Raw CSV preview** section shows ~301 rows (the count in your latest export — adjust expectation if the file is newer).
4. Review the **Planned changes** table. Filter by status chip to check each bucket:
   - `already_imported` — should be most of the previously-applied rows. Verify the count roughly matches what's already in your portfolio.
   - `new` — these are the rows that will be added. Spot-check 3-5 of them to confirm they look right (date, shares, price, type).
   - `conflict_with_manual` — if any exist, review each one carefully. The default action is "Replace manual with CSV." For the APD manual entry you added on 2026-05-15, decide whether you want the CSV version (more accurate fee data) or your manual one. Document the choice.
   - `unmapped_isin` — should be empty if pre-flight was complete. If not, resolve inline.
   - `fx_unavailable` — should be empty if you're online and yfinance is reachable. If any rows are here, decide whether to enter manual rates or skip them for a later run.
   - `out_of_scope_v1` — Distribution / Interest / Taxes / Withdrawal / Deposit / Corporate action. These cannot be imported until CSV-3 ships. Confirm the count matches expectation (~95 rows in the reference export).
   - `outgoing_transfer` — should be 13 (the broker-migration outgoing side, per CSV-1-hotfix).
   - `cancelled_or_expired` — should be 18.
5. Note the "Apply N changes" button count. Cross-reference: `new` count + chosen `conflict_with_manual` replacements should equal N.
6. Click **Apply**.
7. Verify the success message names the backup file (`data/backups/portfolio.{timestamp}.json.bak`).
8. Note the timestamp — write it down so you can find this backup later if needed.

## Post-flight verification

- [ ] Navigate to **Live Overview**. Verify the position count has increased from 6 to roughly 18 (matches the number of mapped ISINs minus any you chose to skip).
- [ ] Sanity-check 3 positions you know off the top of your head — does the share count look right? Does the current price look right?
- [ ] Check `data/import_log.json` for a new entry with today's timestamp.
- [ ] Check `data/backups/` contains the new `.bak` file.
- [ ] Run the existing test suite (`pytest`) to confirm nothing regresses — the additional positions shouldn't break any tests, but a sanity run is cheap.
- [ ] Open the Manage Portfolio page. Verify the "All Transactions" list now shows ~75+ rows (up from ~12).

## Rollback procedure

If something looks wrong:

1. Stop using the app immediately. Don't make any more changes.
2. From the terminal: `cp data/backups/portfolio.{timestamp-from-step-7}.json.bak data/portfolio.json`.
3. Restart the app. Verify Live Overview shows the pre-import state.
4. File a bug ticket with a description of what went wrong and which backup you restored from.

## Notes

### Why this is a ticket and not just "go do it"

Tickets in this project exist partly to make work visible to future-Vivek and future-Claude-in-a-fresh-chat. Without this ticket, after CSV-4 + CSV-5 merge, the natural assumption is "everything's done." It's not — there's still a manual run to do. A queued ticket makes the gap explicit so it doesn't fall through the cracks.

### Why "no code"

Everything code-side is in CSV-4 and CSV-5. The hard problems (visibility, native currency, dedup) are solved there. CSV-6 is just running the tools we built. If you find a bug during this run, that's a new ticket, not a scope expansion of CSV-6.

### Estimated wall-clock time

15-30 min if everything goes smoothly. Most of the time is in the review step (4), where you're scanning rows and making conflict-resolution decisions. The Apply itself is one click.

### After this ticket

Portfolio should be complete (modulo CSV-3 non-trade events, which are tax-relevant but not lot-affecting). The Live Overview should show real positions. Tax dashboard may still be broken pending its own fix — that's outside this ticket's scope and was noted as a separate issue during the chat session that spawned these tickets.
