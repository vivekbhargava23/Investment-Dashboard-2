# TICKET-CSV-1 — Fix amount sign check + skip outgoing Security transfers

**Status:** QUEUED
**Priority:** CRITICAL
**Estimated session length:** 30 min
**Drafted by:** Vivek + Claude (chat session 2026-05-15)
**Implemented by:** TBD
**Milestone:** Foundation

## Problem

TICKET-CSV-1 shipped the Scalable CSV importer. Running it against the real 2026-05-14 export fails on the first outgoing Security-transfer row:

```
Import error: Row 102: amount sanity check failed — abs(amount)=20.247000,
shares×price=-20.247000, diff=40.494000 ≥ 0.01. This may indicate a CSV format change.
```

The row is:
```
2025-12-05;01:00:00;Executed;"WWUM 00596687933";"21shares Polygon ETP";Security;Security transfer;CH1129538448;-17;1,191;-20,247;;;EUR
```

Two distinct spec bugs in TICKET-CSV-1 caused this:

### Bug 1 — Amount sign check is wrong

The original ticket described the check as: `|shares × price + fee_signed - csv_amount| < 0.01`, with a note that "For Buy: amount is negative, so check is `|shares × price + fee - (-amount)| < 0.01`."

This is incomplete. The Scalable sign convention is:

| Row type | `shares` sign | `price` sign | `amount` sign | `shares × price` sign |
|---|---|---|---|---|
| Buy | + | + | − (cash out) | + |
| Savings plan | + | + | − (cash out) | + |
| Sell | + | + | + (cash in) | + |
| Security transfer (incoming) | + | + | + (informational) | + |
| Security transfer (outgoing) | − | + | − (informational) | − |

For outgoing transfers, both `shares × price` and `amount` are negative — they match in absolute value, but the implementation's sign handling fails on them (diff = 40.494 = 2 × |20.247|, the classic sign-flip symptom).

**Correct check (sign-agnostic):** compute `expected = abs(shares × price) + fee_eur` and `actual = abs(amount)`, then assert `abs(expected - actual) < 0.01`. The fee is always non-negative in the CSV (it's the broker's charge, never paid to the user). The directional sign is verified separately by row-type rules (see Bug 2).

### Bug 2 — Outgoing Security transfers should not be imported

The reference CSV has 26 Security transfer rows, paired by ISIN:
- **13 outgoing** rows dated 2025-12-05, shares negative, amount negative (assets leaving the *old* broker).
- **13 incoming** rows dated 2025-12-06, shares positive, amount positive (assets arriving at Scalable, with cost basis preserved).

Only the incoming side represents a real cost-basis lot. The outgoing side is bookkeeping for the *previous* broker. Importing them would:

1. Violate `Transaction.shares_must_be_positive` (would crash at Pydantic validation).
2. If we worked around that — create phantom negative lots that break FIFO.
3. Double-count the migration (each holding appears twice).

The original TICKET-CSV-1 spec said only: "Security transfer → BUY" without addressing the outgoing side. The implementation correctly forwarded the row to amount-check (where it failed), but the right behaviour is to skip outgoing transfers entirely at the row-filter stage.

## Scope

Two narrow fixes to `app/adapters/scalable_csv/importer.py` and corresponding tests. No domain model changes. No changes to TICKET-CSV-2 or CSV-3 plans.

## Fix 1 — Amount sanity check (sign-agnostic)

Replace the current check with:

```python
expected = abs(shares * price) + fee_eur  # fee_eur is Decimal("0") when fee blank
actual = abs(amount)
if abs(expected - actual) >= Decimal("0.01"):
    raise ImportError(
        f"Row {row_num}: amount sanity check failed — "
        f"abs(amount)={actual}, abs(shares×price)+fee={expected}, "
        f"diff={abs(expected - actual)} ≥ 0.01. "
        f"This may indicate a CSV format change."
    )
```

Then, independently, verify directional sign consistency by row type:

```python
SIGN_RULES = {
    # type: (expected shares sign, expected amount sign)
    "Buy": ("positive", "negative"),
    "Savings plan": ("positive", "negative"),
    "Sell": ("positive", "positive"),
    "Security transfer": "either",  # both incoming and outgoing exist
}
```

The sign check is **separate** from the amount check. If a Buy row has positive amount, that's a CSV-format-change error worth flagging. The sign check runs only on rows we've decided to keep (i.e. after the outgoing-transfer filter from Fix 2).

## Fix 2 — Skip outgoing Security transfers

In the row-filter stage of the importer (the same place the existing status-filter and type-filter live), add one rule:

```python
if row.type == "Security transfer" and row.shares < 0:
    # outgoing side of broker migration — bookkeeping for old broker, not a real lot
    counters["outgoing_transfers_skipped"] += 1
    continue
```

The filter runs **before** the amount sanity check, so outgoing rows never reach the math.

Update the import summary to include this counter:

```
In scope:          189
  Status-filtered: 18
  Outgoing Security transfers skipped: 13
  Out of scope:    95
  Already in portfolio: ...
  New transactions:     ...
  Unmapped ISINs:       ...
```

## Acceptance criteria

- [ ] Running `python tools/import_scalable_csv.py --input data/scalable_raw.csv` against the real 2026-05-14 export exits 0.
- [ ] Exactly 13 Security transfer rows are imported as Transactions (the incoming side, dated 2025-12-06), not 26.
- [ ] Summary output includes a new line "Outgoing Security transfers skipped: 13" with the correct count.
- [ ] All previously-passing TICKET-CSV-1 tests still pass unchanged.
- [ ] New test: outgoing-transfer fixture (one negative-shares row) → not imported, counted under `outgoing_transfers_skipped`.
- [ ] New test: incoming-transfer fixture (positive shares, positive amount) → imported as a BUY Transaction with correct fields.
- [ ] New test: paired transfer fixture (one outgoing + one incoming for the same ISIN, one day apart) → exactly one Transaction created (the incoming one), with the outgoing counted as skipped.
- [ ] New test: Buy row with positive amount (forced-edit fixture) → import aborts with a clear directional-sign error.
- [ ] New test: sign-agnostic amount check passes on incoming transfers (positive shares × positive price ≈ positive amount).
- [ ] Lints pass: `ruff check . && mypy app/ && lint-imports`.

## Files likely touched

- `app/adapters/scalable_csv/importer.py` — both fixes
- `tests/unit/test_scalable_csv_importer.py` — new test cases (4 listed above)
- `tests/fixtures/scalable_csv/` — new fixture CSVs:
  - `outgoing_transfer_only.csv` — 1 negative-shares transfer row
  - `incoming_transfer_only.csv` — 1 positive-shares transfer row
  - `paired_transfers.csv` — 2 rows (outgoing + incoming for same ISIN)
  - `buy_wrong_sign.csv` — 1 Buy row with positive amount (should reject)

## Out of scope

- Refactoring the amount-check call site. Minimal in-place fix.
- Treating outgoing transfers as a Distribution-style cash event. They are bookkeeping for the previous broker; we don't model them at all. (If a future migration is FROM Scalable TO another broker, that's a different problem — file a new ticket then.)
- Changes to the `SIGN_RULES` table beyond what's specified above. If a future export shows new row types with different sign conventions, that's a separate ticket.
- Reconciling the small price differences between paired transfers (CH1129538448: outgoing at 1.191, incoming at 1.144 = 19.4463/17). The incoming side is what counts for cost basis; the outgoing side is ignored. No reconciliation needed.

## Test cases (detailed)

### Test 1 — Outgoing transfer skipped

Fixture: 1 row, `type=Security transfer, shares=-17, price=1.191, amount=-20.247`. Run importer with the ISIN pre-mapped to a ticker.

Expected: 0 transactions written to portfolio.json. Summary has `outgoing_transfers_skipped: 1`. No errors raised.

### Test 2 — Incoming transfer imported

Fixture: 1 row, `type=Security transfer, shares=17, price=1.144, amount=19.4463`. Run importer.

Expected: 1 Transaction written with `type=BUY, shares=17, price_native=Money(1.144, EUR), fees_native=None`. Summary has `new: 1, outgoing_transfers_skipped: 0`.

### Test 3 — Paired transfers

Fixture: 2 rows for the same ISIN — one outgoing (2025-12-05, shares=-17, amount=-20.247), one incoming (2025-12-06, shares=17, amount=19.4463). Run importer.

Expected: 1 Transaction (the incoming one), 1 outgoing skipped. The resulting Transaction's `trade_date` is 2025-12-06 (not 2025-12-05).

### Test 4 — Buy with wrong sign rejects

Fixture: 1 Buy row with `shares=4, price=76.51, amount=+306.04` (positive instead of the expected negative).

Expected: import aborts with a directional-sign error referencing the row number and the rule violated (Buy expects negative amount).

### Test 5 — Amount check sign-agnostic on incoming transfers

Fixture: same as Test 2. Verify the amount check passes (it would have failed in the pre-hotfix code if the importer had reached it after a Bug-2 workaround).

## Notes

### Why this is a hotfix, not part of CSV-2

CSV-2 is UI work (Streamlit mappings page). This bug blocks Vivek from running the importer end-to-end on his real data. CSV-2 cannot be tested usefully until the importer succeeds. Hotfix unblocks both Vivek and CSV-2 in 30 min.

### Why the amount check is sign-agnostic now

The old check tried to encode direction (cash in vs cash out) into the same expression. Direction is a separate concern — it's about which way money moved, not whether the math adds up. Separating "does the arithmetic balance?" from "is the sign correct for this row type?" gives clearer error messages and is easier to extend if Scalable adds new row types later (e.g. partial sells, options assignments).

### Bench-test against the real CSV

Walked Fix 2 against all 26 Security transfer rows in the reference export. All 13 outgoing rows (2025-12-05) have `shares < 0` and `amount < 0`. All 13 incoming rows (2025-12-06) have `shares > 0` and `amount > 0`. The negative-shares filter cleanly separates them. No edge case found in the real data.

### Bench-test for Buy/Sell sign rules

- Buy row sample: `shares=4, price=76.51, amount=-306.04`. Positive shares, negative amount. ✓ matches rule.
- Sell row sample: `shares=15, price=117.355, amount=1.760,325`. Positive shares, positive amount. ✓ matches rule.
- No Buy or Sell row in the reference export has unexpected signs.

### Anti-approximation

The "either" sign rule for Security transfer is not a placeholder — it's the correct rule because both incoming and outgoing exist in the data, and the filter in Fix 2 already removes the outgoing ones before the sign check runs. So in practice, by the time the sign check runs, Security transfers are guaranteed to be incoming (positive shares, positive amount), and "either" is a defensive allowance for future variants.
