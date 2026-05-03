# TICKET-002 — FIFO engine (compute_positions, compute_realised_gains, RealisedGain)

**Status:** MERGED
**Priority:** P0
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-03)
**Implemented by:** Claude Code (session 2026-05-03)
**Depends on:** TICKET-001 (must be merged into main before this ticket starts)

## Problem

We have domain types (`Transaction`, `Position`, `OpenLot`, `Money`) from TICKET-001. We now need the **FIFO engine** that turns a list of transactions into the current view of the portfolio: open positions + realised gains.

This is the core algorithm of the entire app. Get it right and tax, valuation, lot ledger, pre-trade simulation all become straightforward downstream queries. Get it wrong and every number in the UI is wrong.

The engine is a **pure function**: input is a list of `Transaction`s, output is positions and realised gains. No I/O, no global state, no `datetime.now()`. Fully unit-testable from one test file.

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-03:

1. **Tie-break for same-day same-ticker buys** = caller-supplied transaction order, broken by `Transaction.id` (UUID) for fully deterministic output. The user is the source of truth for "which buy came first" intra-day.
2. **Invalid sells (sell > open shares)** = raise `SellExceedsOpenSharesError` with a clear, actionable message. The engine assumes valid input. UI / pre-trade simulator (later tickets) must prevent invalid sells from being persisted.
3. **`RealisedGain` is a domain model**, defined in this ticket. It is the canonical record of "this many shares of this buy lot were consumed by this sell transaction with this gain in EUR."
4. **Mutable internal state, pure external interface.** Inside the function, use a per-ticker queue (deque) and pop/split lots as we walk the transaction list. Externally, the function takes an immutable input and returns immutable output (frozen Pydantic models).
5. **Splits, dividends, fees-only events are out of scope.** Only BUY and SELL transactions exist in this ticket. Future tickets add new `TransactionType` members; the FIFO engine will handle them via dispatch and not require a rewrite.
6. **`as_of` filtering is callers' responsibility, not the engine's.** If the caller wants positions as of 2025-12-31, the caller filters the transaction list. The engine processes whatever it's given.

## Acceptance criteria

### `app/domain/realised_gain.py`

- [ ] `RealisedGain` — Pydantic v2 `BaseModel`, `frozen=True`.
  - `sell_transaction_id: str`
  - `buy_transaction_id: str`
  - `ticker: str` (validated uppercase)
  - `shares: Decimal` (must be `> 0`; the number of shares from this buy lot consumed by this sell)
  - `sell_date: date`
  - `buy_date: date`
  - `proceeds_eur: Money` (must be EUR; = `shares * sell_price_native * sell_fx_rate_eur`)
  - `cost_basis_eur: Money` (must be EUR; = `shares * buy_price_native * buy_fx_rate_eur`)
  - `realised_gain_eur: Money` (must be EUR; = `proceeds_eur − cost_basis_eur`)
  - `holding_period_days: int` (= `(sell_date − buy_date).days`; must be `>= 0`)
- [ ] Class validator: `proceeds_eur`, `cost_basis_eur`, `realised_gain_eur` all currency = EUR; raise on mismatch.
- [ ] Class validator: `realised_gain_eur == proceeds_eur − cost_basis_eur` (within 0.01 EUR tolerance for Decimal rounding).
- [ ] Class validator: `holding_period_days >= 0` (sell cannot be before buy).
- [ ] Helper property `is_loss: bool` (returns `realised_gain_eur.amount < 0`).

### `app/domain/fifo.py`

- [ ] `SellExceedsOpenSharesError(Exception)` defined here. Message format:
  `"Sell of {shares} {ticker} on {date} exceeds open position of {open_shares} shares (transaction {sell_id})"`
- [ ] `compute_positions(transactions: Sequence[Transaction]) -> dict[str, Position]`:
  - Returns a dict keyed by ticker. Tickers with zero open shares (fully sold out) are **omitted from the output dict** — they have no Position to report.
  - Each `Position` has correctly-summed `open_shares`, the full ordered tuple of remaining `OpenLot`s (oldest first), `cost_basis_eur` summed across lots, and `realised_gain_eur_ytd` = sum of realised gains for that ticker in the current calendar year.
  - "Current calendar year" = year of the most recent transaction in the input. **Not** `datetime.now().year` — the engine has no clock. (The UI layer can pass an `as_of` filter if it wants a different year; the engine just reports YTD relative to the data given.)
- [ ] `compute_realised_gains(transactions: Sequence[Transaction]) -> list[RealisedGain]`:
  - Returns all realised gains across all sells, in chronological order (sorted by `sell_date`, then by `sell_transaction_id` for determinism).
  - One sell may produce multiple `RealisedGain` records if it consumes from multiple buy lots (typical for partial sells across lots).
- [ ] Internal helper `_sort_transactions(transactions) -> list[Transaction]`:
  - Sort key: `(trade_date, type_priority, id)` where `type_priority` is `0` for BUY and `1` for SELL — this ensures that on the same day, all buys are processed before any sells. (Otherwise a same-day buy-then-sell would fail because the buy hasn't entered the queue when the sell tries to consume.)
  - Within the same day and type, order by `id` (UUID). This is deterministic and matches the "caller-supplied order" decision since UUIDs are assigned at construction time.
- [ ] Internal helper `_consume_from_lots(lot_queue: deque[OpenLot], shares_to_consume: Decimal, sell_tx: Transaction) -> list[RealisedGain]`:
  - Pops from the front of the queue.
  - If the front lot has more shares than needed, **splits it**: emit one `RealisedGain` for the consumed portion, push back a reduced `OpenLot` to the front of the queue.
  - If the front lot has equal or fewer shares, consume it fully, emit one `RealisedGain`, continue popping.
  - If the queue empties before `shares_to_consume` is satisfied, raise `SellExceedsOpenSharesError`.

### Tests

All tests in `tests/unit/domain/test_fifo.py` (single file is fine — many test functions inside).

#### Basic correctness
- [ ] **Empty input**: `compute_positions([]) == {}`, `compute_realised_gains([]) == []`.
- [ ] **Single buy**: one EUR buy → one Position with one OpenLot, no realised gains.
- [ ] **Single buy, full sell**: buy 10 NVDA at $100, sell 10 NVDA at $120 (same FX rate 1.0) → empty positions dict, one RealisedGain with `realised_gain_eur = $200`.
- [ ] **Single buy, partial sell**: buy 10 NVDA, sell 4 → Position with `open_shares=6`, one RealisedGain for 4 shares.
- [ ] **Multiple buys, partial sell crossing lots**: buy 10 NVDA at $100, buy 5 NVDA at $120, sell 12 → two RealisedGain records (10 shares from lot 1, 2 shares from lot 2), Position with `open_shares=3` and one OpenLot of 3 shares from the second buy.

#### Multi-ticker
- [ ] **Two tickers, no interference**: NVDA and RHM.DE transactions don't affect each other's FIFO queues. Test that buying RHM.DE doesn't change NVDA's position.

#### FX correctness
- [ ] **USD buy, EUR sell currency-of-origin gain ≠ EUR gain**: buy 10 NVDA at $100 with fx_rate 0.90 (cost €900), sell 10 NVDA at $100 with fx_rate 1.10 (proceeds €1100). Realised gain in EUR = €200, even though USD gain is $0.
- [ ] **EUR buy and sell**: buy 10 RHM.DE at €100 (fx_rate 1.0), sell 10 at €120 (fx_rate 1.0). Realised gain = €200.

#### Tie-breaking
- [ ] **Same-day buys, tie-break by id**: two BUY transactions on the same date, same ticker, with different IDs and different prices. Force IDs to known values (override `default_factory`). A subsequent sell consumes from the lower-id buy first. Verify by checking `RealisedGain.buy_transaction_id`.
- [ ] **Same-day buy then sell**: buy 10 NVDA, sell 10 NVDA on the same date. Both succeed. (Tests that BUY is processed before SELL on same date.)

#### Error cases
- [ ] **Sell with no buys**: SELL of NVDA with no prior BUY → `SellExceedsOpenSharesError`.
- [ ] **Sell exceeding open**: buy 5, sell 10 → `SellExceedsOpenSharesError`. Error message contains the ticker, the attempted shares, and the actual open shares.
- [ ] **Sell after full sell-out**: buy 10, sell 10, sell 1 → `SellExceedsOpenSharesError` on the second sell.

#### Realised gains output
- [ ] **Chronological ordering**: insert sells out of order, verify output of `compute_realised_gains` is sorted by `sell_date`.
- [ ] **One sell across two lots produces two RealisedGains**: verify the count and that `shares` sums to the original sell quantity.

#### Position.realised_gain_eur_ytd
- [ ] **YTD computation**: input has sells in year N-1 and year N (where N = year of most recent transaction). Position.realised_gain_eur_ytd reflects only year-N sells.

#### Determinism
- [ ] **Same input → same output**: run `compute_positions` twice on the same shuffled input list (after shuffling); both runs produce identical output. Use `hash` or direct equality on the result dict.

#### Property-based test (use `hypothesis`)
- [ ] For any sequence of valid BUYs followed by valid SELLs (each sell ≤ open shares at that point), the sum of `RealisedGain.shares` for a ticker equals the sum of SELL transaction shares for that ticker. Constrain the strategy:
  - 1–5 tickers
  - 1–20 transactions
  - Shares between Decimal("0.0001") and Decimal("1000")
  - Prices between Decimal("0.01") and Decimal("10000")
  - FX rates between Decimal("0.5") and Decimal("2.0")
  - Generator must produce a valid sequence (sells never exceed running open shares per ticker)

### Lints / quality
- [ ] `pytest` — all tests pass (existing + new)
- [ ] `ruff check .` — passes
- [ ] `mypy app/` — passes; **strict mode on `app/domain/`**
- [ ] `lint-imports` — passes; FIFO engine has no I/O, no `requests`, no `datetime.now`

### State updates (per CLAUDE.md session-end ritual)
- [ ] `docs/SESSION_LOG.md` appended
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-002 → IN_REVIEW; "Done" gains TICKET-001)
- [ ] `BACKLOG.md` updated (TICKET-002 → IN_REVIEW)
- [ ] Ticket file `Status: IN_REVIEW`
- [ ] PR opened via `gh pr create --fill --base main`

## Files created

```
app/domain/realised_gain.py
app/domain/fifo.py
tests/unit/domain/test_fifo.py
```

## Files possibly updated

```
app/domain/__init__.py     ← export RealisedGain, compute_positions, compute_realised_gains
app/domain/CLAUDE.md       ← add notes on the FIFO algorithm and its invariants
```

## Out of scope

- Stock splits (would require a `SPLIT` transaction type)
- Dividend tracking (would require a `DIVIDEND` transaction type)
- Fees-only adjustments
- Persistence — TICKET-003
- The `as_of` parameter on `compute_positions` — caller pre-filters
- Tax calculations (Abgeltungsteuer, Sparerpauschbetrag) — TICKET-010
- The pre-trade sell simulator that uses this engine — TICKET-012

## Notes

### On the "BUY before SELL on same date" sort rule

This is not arbitrary. Real brokers process trades intraday, and a same-day buy-then-sell is a perfectly valid pattern (day trading, mistake correction, etc.). If we sort purely by date and id, a same-day SELL with a smaller ID than its corresponding BUY would fail because the buy hadn't been processed yet. By sorting BUY < SELL within the same date, we match the only economically meaningful ordering.

If a user really wants to sell something they don't own yet (short-selling), that's a different transaction type entirely and out of scope.

### On the queue / deque choice

Use `collections.deque[OpenLot]` for each ticker. Reasons:
- O(1) append (for new buys) and O(1) popleft (for FIFO sells)
- Easier to read than a plain list with index manipulation
- We need front-of-queue mutation when a sell partially consumes the front lot — easy with deque

### On lot splitting

When a sell consumes 4 of the 10 shares in the front buy lot:

```python
# Before: front lot has 10 shares
# After: front lot has 6 shares (popleft + replace), one RealisedGain emitted for 4 shares
front_lot = lot_queue.popleft()
gain = _make_realised_gain(front_lot, sell_tx, shares=Decimal("4"))
remaining_lot = front_lot.model_copy(update={
    "remaining_shares": front_lot.remaining_shares - Decimal("4"),
})
lot_queue.appendleft(remaining_lot)
```

This is the only place where `model_copy` is acceptable in domain code — we are explicitly producing a new immutable instance.

### On the `OpenLot` constructed from a BUY transaction

When processing a BUY, push a fresh `OpenLot`:

```python
OpenLot(
    source_transaction_id=buy_tx.id,
    ticker=buy_tx.ticker,
    trade_date=buy_tx.trade_date,
    remaining_shares=buy_tx.shares,
    cost_per_share_native=buy_tx.price_native,  # NOT including fees — fees stay on the Transaction
    fx_rate_eur=buy_tx.fx_rate_eur,
)
```

**Fees are not allocated into per-lot cost basis** in this ticket. Reason: fee allocation across partial sells gets ugly fast (do you allocate proportionally? per-share? at sell time?). German tax authority treats `Anschaffungsnebenkosten` (acquisition costs) as adding to the cost basis of the lot, but for now fees are tracked on the `Transaction` and not pushed down to lots. This is documented as a known simplification — a future ticket will revisit if it matters.

### On performance

For ≤1000 transactions across ≤50 tickers, this is trivial. We are talking microseconds. No caching, no incremental updates, no memoization needed in this ticket. If profiling later shows it's a bottleneck (it won't), TICKET-013 (daily NAV cache) addresses it at a higher level.

### On testing strategy

- Most tests construct Transactions directly with explicit IDs (override the UUID factory) for predictability.
- Use a small set of helper builders in the test file: `_buy(ticker, date, shares, price_eur, ...)` and `_sell(...)` that return `Transaction` instances with sensible defaults.
- Property-based test should use `hypothesis.strategies.composite` to build a *valid* transaction sequence (sells never exceed running open shares); a naive strategy will produce 99% invalid inputs and waste time on `SellExceedsOpenSharesError`.
