# TICKET-CSV-3 — Design Distribution / Interest / Vorabpauschale / Corporate-action handling

**Status:** QUEUED
**Priority:** MEDIUM
**Estimated session length:** chat-only design session, then 2-3 hr impl
**Drafted by:** Vivek + Claude (chat session 2026-05-15)
**Implemented by:** TBD (design first, then code)
**Milestone:** Tax engine

## Problem

TICKET-CSV-1 imports trade events from Scalable Capital exports (Buy / Sell / Savings plan / Security transfer). It explicitly skips five other event types that the CSV contains:

| CSV `type` | Example row | What it represents | Why deferred |
|---|---|---|---|
| Distribution | `Cash;Distribution;US0091581068;;;3,64;0,00;2,51;EUR` | Cash dividend paid into account, with Abgeltungsteuer already withheld at source (`tax` column) | Need to decide: dividend income flows into the tax engine's `additional_dividend_income_eur` input — does it auto-populate from CSV? Does it count against Sparerpauschbetrag automatically? Currently Vivek enters dividend totals manually in the tax profile. |
| Interest | `Cash;Interest;;;;3,29;0,00;0,00;EUR` | Cash interest (typically on Scalable Instant deposit balance) | Same flow as dividends — `additional_interest_income_eur`. Should it auto-populate? |
| Taxes (Vorabpauschale) | `Cash;Taxes;;;Vorabpauschale: Vanguard S&P 500 ETF (IE00BFMXXD54);-3,84;0,00;;EUR` | Pre-paid annual tax on accumulating ETFs. Reduces future capital-gains tax when the ETF is sold. | This is the trickiest one — it creates a tax credit that must be tracked per-ticker per-year and netted against future SELL realised-gain tax. Requires changes to the tax pipeline. |
| Taxes (other) | `Cash;Taxes;;;;71,04;0,00;;EUR` (no Vorabpauschale prefix) | Generic tax payment — could be Abgeltungsteuer settlement, church tax, etc. | Need to distinguish from Vorabpauschale by description prefix and handle each. |
| Corporate action (with shares) | `Security;Corporate action;DE000HT41XN9;-26;0,001;-0,026;;;EUR` | Delisting / writeoff / merger / split / reverse-split. The reference export has one such row — the Apple Short Turbo writeoff. | Negative-share events break FIFO's "shares must be positive" invariant. Each subtype (delisting, merger, split) needs its own model. |
| Deposit / Withdrawal | `Cash;Deposit;;;;1.000,00;9,90;;EUR` | Cash flow into/out of the broker. Not a portfolio event. | Cleanly out of scope — no plans to handle. |

## What this ticket is

This ticket is a **placeholder reminder**. It sits in Backlog as a marker that we know these events exist and we haven't dealt with them. It is NOT yet a complete spec — the design work has to happen first.

Before this ticket can move to Ready, we need a chat session that produces:

1. **Domain decision: new TransactionType values or a separate event type?**
   - Option A: extend `TransactionType` enum with `DIVIDEND`, `INTEREST`, `VORABPAUSCHALE`, `CORP_ACTION`.
   - Option B: introduce a separate `CashEvent` or `TaxEvent` model alongside `Transaction`.
   - Option C: hybrid — corp actions become Transactions, dividends/interest/Vorabpauschale become separate.

2. **Tax-engine integration design:**
   - How does Distribution income flow into `TaxYearSummary.additional_dividend_income_eur`? Does the engine accept a per-event list or just a yearly aggregate?
   - How does Vorabpauschale create a per-ticker tax credit? Where is it stored? How does the FIFO realised-gain → tax pipeline net against it on sell?
   - Already-withheld Abgeltungsteuer (the `tax` column on Sell and Distribution rows) — currently captured as a note in CSV-1 but not used. Should it net against the tax engine's computed `total_tax_owed_eur` as "already paid"?

3. **Corporate action subtype taxonomy:**
   - The reference export has exactly one corp-action-with-shares row (Apple Short Turbo writeoff, -26 shares at 0.001 EUR). That's a delisting / writeoff specifically.
   - Future events will include splits, reverse splits, mergers, spinoffs, name changes. Each has its own FIFO behaviour.
   - Decide: implement only what's in current exports, or build the taxonomy up front?

4. **Re-import migration:** when CSV-3 lands, the next CSV import will start picking up these events. Existing portfolio.json (from CSV-1 imports) won't have them. Does the next import retroactively pull them from the still-present CSV? (Yes, probably — the importer treats the CSV as source of truth.)

5. **ADR:** this work likely warrants an ADR documenting the chosen approach.

## When to pick this up

- Vivek manually entered dividend / interest totals into the tax profile recently and felt friction → pull this in.
- Vivek hits a tax-engine inaccuracy due to missing Vorabpauschale → pull this in.
- Vivek hits a corp action that affects a real holding (split, merger) → pull this in.
- Otherwise, this can sit in Backlog. The annual count of these events is small (the reference export has 21 Distribution + 5 Interest + 11 Taxes + 2 Corp-action = 39 events over ~2 years, vs 206 trades).

## Acceptance criteria

**Pre-implementation (chat-session deliverables):**

- [ ] ADR drafted documenting domain model decision (Option A / B / C above) and tax-engine integration approach.
- [ ] CSV-3 ticket rewritten with full spec + acceptance criteria for each subtype.
- [ ] Vivek approves the ADR before implementation begins.

**Implementation (post-design):**

- [ ] To be defined after the design session.

## Files likely touched (rough sketch — will firm up post-design)

- `app/domain/models.py` — possible TransactionType extension or new event model
- `app/domain/tax/pipeline.py` — Vorabpauschale credit + already-withheld tax netting
- `app/adapters/scalable_csv/importer.py` — new event-type routing
- `docs/DECISIONS/ADR-00X-cash-events-and-corp-actions.md` — new ADR
- Tests for each subtype

## Out of scope

- Deposit / Withdrawal — these are bank-side cash flows, not portfolio events. Not planning to model them.
- Currency: all reference rows are EUR. If a future export shows non-EUR cash events, that becomes a separate concern.

## Notes

The reference CSV (2026-05-14 export) provides exact sample rows for each subtype. Use it for fixture design when this ticket is implemented:

```
# Distribution (cash dividend)
2026-05-12;02:00:00;Executed;"443359_…";"Air Products & Chem";Cash;Distribution;US0091581068;;;3,64;0,00;2,51;EUR

# Interest
2026-04-01;02:00:00;Executed;"522ed2f6-…";;Cash;Interest;;;;3,29;0,00;0,00;EUR

# Vorabpauschale (pre-paid ETF tax)
2026-01-24;01:00:00;Executed;"358459_…";"Vorabpauschale: Vanguard S&P 500 UCITS ETF (IE00BFMXXD54)";Cash;Taxes;;;;-3,84;0,00;;EUR

# Generic tax settlement
2026-03-10;01:00:00;Executed;"CDS_DTA_…";"";Cash;Taxes;;;;71,04;0,00;;EUR

# Corporate action (writeoff with negative shares)
2025-04-25;02:00:00;Executed;"WWUM 00477772743";"Apple Short 205,25 $ Turbo Open End HSBC";Security;Corporate action;DE000HT41XN9;-26;0,001;-0,026;;;EUR
```
