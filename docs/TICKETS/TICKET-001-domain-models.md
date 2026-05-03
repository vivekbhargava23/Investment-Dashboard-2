# TICKET-001 — Domain models (Money, Transaction, Position, OpenLot)

**Status:** IN_REVIEW
**Priority:** P0
**Estimated session length:** 1 – 1.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-03)
**Implemented by:** _pending_

## Problem

We have an empty `app/domain/` package. We need the **pure-Python data structures** that represent the portfolio. No I/O, no FIFO engine, no FX adapter — just the types and their invariants, fully tested.

This ticket defines the vocabulary every later ticket uses. Get this right and FIFO, storage, and tax become straightforward. Get it wrong and we pay forever.

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-03 and are reflected in the code:

1. **Transaction is the atomic record** (Pattern A). `Position` and `OpenLot` are derived types, computed by the FIFO engine in TICKET-002. We never store Lots; we store Transactions and compute the Lot view.
2. **Money is a value object** with `amount: Decimal` and `currency: Currency`. Same-currency arithmetic; mixed-currency raises.
3. **All domain models are frozen** (Pydantic v2 `model_config = ConfigDict(frozen=True)`). To "edit" a transaction you replace it with a new one.
4. **`fx_rate_eur` is a required field on Transaction**, supplied by the caller at creation time. The domain model never looks up FX; that's the boundary's responsibility (UI layer or CSV importer calls FX service, then constructs the Transaction).
5. **Trade date only** — no settlement date for now.
6. **`shares` is always positive on a Transaction**; the sign comes from `type` (BUY adds, SELL removes).

These are documented in `app/domain/CLAUDE.md` (which Claude Code created in TICKET-000) and should be reinforced there if not already.

## Acceptance criteria

### `app/domain/money.py`

- [ ] `Currency(str, Enum)` with two members: `EUR = "EUR"`, `USD = "USD"`.
- [ ] `Money` class — Pydantic v2 `BaseModel` with `model_config = ConfigDict(frozen=True)`.
  - Fields: `amount: Decimal`, `currency: Currency`
  - Validator: `amount` is normalised to a fixed precision (use `Decimal` quantization to 4 decimal places — enough for share-quantity math, FX rates, and price-per-share).
- [ ] Arithmetic methods on `Money`:
  - `__add__`, `__sub__` — same-currency only; raise `CurrencyMismatchError` if currencies differ.
  - `__mul__` — `Money * Decimal` returns `Money`. `Money * Money` is undefined and raises `TypeError`.
  - `__truediv__` — `Money / Money` requires same currency, returns a `Decimal` (a unitless ratio). `Money / Decimal` returns `Money`.
  - `__neg__` — returns `Money(-amount, currency)`.
  - `__lt__`, `__le__`, `__gt__`, `__ge__`, `__eq__` — same-currency comparison; raise on mismatch except `__eq__` which returns `False`.
- [ ] `Money.zero(currency)` classmethod for convenience.
- [ ] `__str__` returns formatted output like `"€100.50"` or `"$2,540.00"` (use locale-independent `f"{symbol}{amount:,.2f}"` with `EUR` → `€`, `USD` → `$`).
- [ ] `CurrencyMismatchError` exception class defined in this module.

### `app/domain/models.py`

- [ ] `TransactionType(str, Enum)` with `BUY = "buy"`, `SELL = "sell"`.
- [ ] `Transaction` — Pydantic v2 `BaseModel`, `frozen=True`.
  - `id: str` (UUID4 string, auto-generated via `default_factory=lambda: str(uuid4())`)
  - `type: TransactionType`
  - `ticker: str` (must be uppercase, validated; e.g. `"NVDA"`, `"RHM.DE"`)
  - `trade_date: date` (Python's `datetime.date`)
  - `shares: Decimal` (must be `> 0`; ValidationError otherwise)
  - `price_native: Money` (price per share in trade currency)
  - `fees_native: Money | None = None` (optional; if present, must be same currency as `price_native`)
  - `fx_rate_eur: Decimal` (must be `> 0`; the ECB EUR/native rate at `trade_date`. For EUR-native trades this is `Decimal("1")`.)
  - `notes: str | None = None`
- [ ] Class validator on `Transaction`:
  - If `price_native.currency == EUR`, `fx_rate_eur` must equal `Decimal("1")`.
  - If `fees_native` is present, its currency must match `price_native.currency`.
- [ ] Helper property `Transaction.cost_native` → `Money` (= `price_native * shares + (fees_native or 0)`).
- [ ] Helper property `Transaction.cost_eur` → `Money` (= `cost_native.amount * fx_rate_eur` as EUR Money).

### `app/domain/positions.py`

- [ ] `OpenLot` — Pydantic v2 `BaseModel`, `frozen=True`.
  - `source_transaction_id: str`
  - `ticker: str`
  - `trade_date: date`
  - `remaining_shares: Decimal` (must be `>= 0`)
  - `cost_per_share_native: Money`
  - `fx_rate_eur: Decimal`
  - Helper property `cost_basis_eur: Money` → `Money(remaining_shares * cost_per_share_native.amount * fx_rate_eur, EUR)`
- [ ] `Position` — Pydantic v2 `BaseModel`, `frozen=True`.
  - `ticker: str`
  - `open_shares: Decimal` (sum of `remaining_shares` across `open_lots`)
  - `open_lots: tuple[OpenLot, ...]` (tuple, not list — must be hashable/immutable)
  - `realised_gain_eur_ytd: Money` (in EUR)
  - `cost_basis_eur: Money` (in EUR; sum across `open_lots`)
  - Class validator: `open_shares` equals sum of `remaining_shares` across `open_lots` (rounded to 4 dp). Raise on mismatch.
  - Class validator: every `OpenLot.ticker` matches `Position.ticker`.

### Tests

All tests in `tests/unit/domain/`. Create `tests/unit/domain/__init__.py`.

- [ ] `tests/unit/domain/test_money.py`:
  - Same-currency `+`, `-`, comparisons work
  - Mixed-currency `+`, `-` raise `CurrencyMismatchError`
  - `Money * Decimal` returns Money with correct amount
  - `Money * Money` raises `TypeError`
  - `Money / Money` (same currency) returns `Decimal`
  - `Money / Decimal` returns `Money`
  - `Money.zero(EUR) + Money(10, EUR) == Money(10, EUR)`
  - Frozen: `m.amount = 5` raises
  - `__str__` formats correctly: `Money(Decimal("1234.5"), EUR)` → `"€1,234.50"`
  - **Property test** (use `hypothesis`): for any two same-currency Money values `a, b`, `a + b - b == a` (within precision)
- [ ] `tests/unit/domain/test_transaction.py`:
  - Valid BUY transaction in EUR — fx_rate must be 1
  - Valid BUY transaction in USD with fx_rate ≠ 1
  - EUR transaction with fx_rate ≠ 1 raises ValidationError
  - Negative shares raises ValidationError
  - Zero shares raises ValidationError
  - `fees_native` in different currency than `price_native` raises ValidationError
  - `cost_native` math: `Transaction(shares=10, price_native=Money(50, USD), fees=Money(2, USD)).cost_native == Money(502, USD)`
  - `cost_eur` math: with fx_rate 0.9, cost_eur = cost_native.amount × 0.9
  - Frozen: cannot mutate fields after creation
  - `id` auto-generated and unique across instances
- [ ] `tests/unit/domain/test_positions.py`:
  - Valid `OpenLot` and `Position` creation
  - `Position` with `open_shares` mismatching sum of lots raises ValidationError
  - `Position` with mixed tickers across lots raises ValidationError
  - `OpenLot.cost_basis_eur` math
  - Frozen: cannot mutate

### Lints / quality
- [ ] `pytest` — all tests pass
- [ ] `ruff check .` — passes
- [ ] `mypy app/` — passes; **strict mode on `app/domain/`**
- [ ] `lint-imports` — passes; domain layer has no I/O imports

### State updates (per CLAUDE.md session-end ritual)
- [ ] `docs/SESSION_LOG.md` appended
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-001 → IN_REVIEW; "Done" gains TICKET-000)
- [ ] Ticket file `Status: IN_REVIEW`
- [ ] PR opened via `gh pr create --fill --base main`

## Files created

```
app/domain/money.py
app/domain/models.py
app/domain/positions.py
tests/unit/domain/__init__.py
tests/unit/domain/test_money.py
tests/unit/domain/test_transaction.py
tests/unit/domain/test_positions.py
```

## Files possibly updated

```
app/domain/CLAUDE.md     ← reinforce the architectural decisions if not already there
app/domain/__init__.py   ← export public API (Money, Currency, Transaction, etc.)
```

## Out of scope

- FIFO engine — TICKET-002
- Persistence — TICKET-003
- FX lookups — TICKET-004
- Price feeds — TICKET-005
- Anything in `app/services/`, `app/adapters/`, `app/ui/`
- Dividend, split, fee-only, or non-EUR/non-USD transactions
- Settle date

## Notes

### On `Decimal` precision

Use 4 decimal places everywhere. This is enough for:
- Share quantities (typically ≤4 dp from any broker)
- Prices (typically 2 dp, sometimes 4)
- FX rates (typically 4 dp from ECB)
- EUR conversions

Quantize on assignment: `amount.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)`.

### On frozen Pydantic models

```python
from pydantic import BaseModel, ConfigDict

class Money(BaseModel):
    model_config = ConfigDict(frozen=True)
    amount: Decimal
    currency: Currency
```

Note: arithmetic operators (`__add__` etc.) are defined as **methods that return new instances**, not mutations. Pattern:

```python
def __add__(self, other: "Money") -> "Money":
    if self.currency != other.currency:
        raise CurrencyMismatchError(...)
    return Money(amount=self.amount + other.amount, currency=self.currency)
```

### On the EUR fx_rate=1 invariant

This is a critical invariant. If a transaction's price is in EUR, its fx_rate_eur must be exactly `Decimal("1")` — never `Decimal("1.0001")` or anything else. The validator catches this at construction time, before bad data lands in storage.

For USD trades, fx_rate_eur is the EUR/USD rate **as seen by an EUR holder buying USD assets** — i.e. how many EUR one USD is worth. So a $100 stock with fx_rate_eur of `0.92` costs €92 per share.

### On UUIDs as transaction IDs

We use UUID4 strings (not auto-incrementing integers) so transaction IDs are stable across:
- Edits and re-orderings (no renumbering)
- Multiple sources of truth if we ever sync with broker exports
- Future migration from JSON to SQLite (UUIDs are portable; integers force renumbering)

### On `tuple[OpenLot, ...]` vs `list[OpenLot]`

Frozen Pydantic models can technically hold mutable list fields, but the contents would be mutable even though the model is "frozen." Using `tuple` ensures the entire object graph is immutable. This matters for hashing and for the property "Position is a snapshot, not a live view."

### Module structure

Three separate files (`money.py`, `models.py`, `positions.py`) instead of one big `models.py`. Reason: `Money` is the most reused primitive; importing it should be a one-liner that doesn't pull in transaction logic. `Position`/`OpenLot` are derived types and conceptually distinct from `Transaction`.

`app/domain/__init__.py` should re-export the common types so callers can write:
```python
from app.domain import Money, Currency, Transaction, Position, OpenLot
```
without caring about the file split.
