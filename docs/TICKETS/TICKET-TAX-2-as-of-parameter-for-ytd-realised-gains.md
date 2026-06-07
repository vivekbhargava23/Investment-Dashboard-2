# TICKET-TAX-2 — `compute_positions` takes `as_of: date` for honest YTD realised gains

**Priority:** HIGH
**Status:** IN_PROGRESS
**Estimated session length:** 1 hr
**Recommended model:** Sonnet — domain signature change with ~6 call-site migrations and test updates. Single-area change, low blast radius, but touches money-relevant code so all callers must be updated comprehensively.
**Drafted by:** Vivek + Claude Chat (2026-06-07)
**Implemented by:** TBD
**Milestone:** Investment Panel

> **Theme:** `Position.realised_gain_eur_ytd` is currently computed against "the most recent year that happens to appear in the transaction list," not against the current calendar year. When the user opens the dashboard in a new year before placing any trades, YTD silently reports last year's figures under a current-year label. This is a correctness bug in tax-relevant numbers. Fix by making the engine take `as_of: date` explicitly, per `app/domain/CLAUDE.md`'s "No `datetime.now()` — pass `as_of: date`" rule.

---

## Problem

`app/domain/fifo.py:28-30`:

```python
latest_year = 0
if sorted_txs:
    latest_year = max(tx.trade_date.year for tx in sorted_txs)
```

…and line 68 filters realised gains by `gain.sell_date.year == latest_year`. The function uses the latest year present in the transaction history as a proxy for "this year." That proxy breaks every January 1st, and breaks earlier than that any time the user has gone weeks without trading at a year boundary.

**Concrete failure mode.** User loads the dashboard on 2026-06-07 (today). Last sell was 2025-11-14. `Position.realised_gain_eur_ytd` reports the 2025-11-14 gain as "YTD." Downstream:

- Live Overview's **Sparerpauschbetrag** and **Tax Headroom** tiles show last-year-against-this-year's-€1,000-allowance — i.e. wrong.
- Tax page's YTD summary shows the same wrong figure.
- A user making a year-end tax-harvesting decision (sell to fill the allowance, or hold to preserve it) makes that decision against a wrong number.

The bug is silent — no exception, no warning, just a confidently-wrong figure.

This violates `app/domain/CLAUDE.md`:

> No `datetime.now()` — pass `as_of: date` explicitly

…in spirit. The function avoids `datetime.now()`, but only by inventing a worse proxy. The right fix is to take `as_of` from the caller.

---

## Solution

Change the `compute_positions` signature to require an explicit `as_of: date`. Filter YTD realised gains by `as_of.year`. Update all six production call sites and all affected tests to pass `as_of` through.

### Files likely touched

- `app/domain/fifo.py` — signature, YTD filter.
- `app/services/valuation.py` — caller (already takes `as_of: date`, just thread it).
- `app/services/nav.py` — caller (NAV history pipeline already operates on a date axis; pick the appropriate date per iteration).
- `app/services/analytics_technicals.py` — caller.
- `app/services/sell_simulator.py` — caller (uses today/as_of of the simulated sell).
- `app/ui/pages/catalysts.py` — caller.
- `app/ui/pages/manage.py` — caller (simulating a candidate sell — `as_of` is the candidate trade date).
- `app/ui/pages/analytics.py` — caller.
- `app/domain/__init__.py` — re-export unchanged; signature change does not affect the public name.
- `tests/unit/domain/test_fifo.py` — all `compute_positions(...)` calls need an `as_of` argument; add the regression test below.
- `tests/unit/ui/test_manage_form_pipeline.py` — same migration.
- Any other callers a final `grep -rn "compute_positions(" --include="*.py"` finds.

### Signature

```python
def compute_positions(
    transactions: Sequence[Transaction],
    as_of: date,
) -> dict[str, Position]:
    ...
```

Internals: drop the `latest_year` block. Replace line 68's filter with `if gain.sell_date.year == as_of.year`. No other logic changes.

### Caller-side rule

UI/service callers fetch `as_of` from the same source they already use for "today" / valuation date. The single permitted introduction of `date.today()` is at the boundary — typically already done by the calling page or by a `default_as_of` helper. Do **not** add `date.today()` inside the domain layer. If a caller doesn't have a clear `as_of` available, it almost certainly is using a fixed valuation date already (e.g. NAV history iterating dates); use that.

### What does NOT change

- `compute_realised_gains` — pure FIFO replay, no YTD concept. Untouched.
- `simulate_lot_consumption` — pure helper. Untouched.
- `_consume_from_lots` — internal. Untouched.
- The `RealisedGain` model. Untouched.
- The `Position` model: `realised_gain_eur_ytd` field stays; only the *computation* of its value changes.
- The Sparerpauschbetrag / tax-engine logic. We are giving it correct input; we are not changing how it uses that input.

---

## Acceptance criteria

- [ ] `compute_positions` signature is `(transactions: Sequence[Transaction], as_of: date) -> dict[str, Position]`.
- [ ] The `latest_year = max(...)` block in `fifo.py` is removed; the YTD filter uses `as_of.year`.
- [ ] Every production call site in the file list above passes a real `as_of`. No call site uses `date.today()` inline as the literal `as_of` argument (callers either receive `as_of` from their own caller, or take a parameter, or use a date the page already holds). The domain function's docstring states this expectation.
- [ ] All existing tests updated to pass `as_of`. Pick the date that makes each test's intent explicit — for legacy tests the simplest correct choice is `as_of = max(tx.trade_date for tx in transactions)` (preserves today's behaviour where applicable) or a fixed `date(2025, 1, 1)` for tests that don't care.
- [ ] New regression test added (see Test cases below) that fails on `main` and passes after the fix.
- [ ] `pytest`, `ruff check .`, `mypy app/`, `lint-imports` all clean.

---

## Test cases

Add to `tests/unit/domain/test_fifo.py`:

1. **`test_ytd_filter_uses_as_of_year_not_latest_trade_year`** — the regression test.
   - Build two transactions for the same ticker: BUY 10 @ €100 on `date(2025, 3, 1)`, SELL 5 @ €120 on `date(2025, 11, 1)`. Realised gain = €100.
   - Call `compute_positions(txs, as_of=date(2026, 6, 7))`.
   - Assert: `positions[ticker].realised_gain_eur_ytd == Money.zero(Currency.EUR)`. (2025's gain is NOT YTD when `as_of` is in 2026.)
   - On `main` (pre-fix), the same input returns €100 — test would fail.
2. **`test_ytd_includes_only_current_year_realised_gains`** — happy-path complement.
   - BUY 20 on `date(2024, 3, 1)`, SELL 5 on `date(2025, 4, 1)` (gain €50), SELL 5 on `date(2026, 4, 1)` (gain €100).
   - Call with `as_of=date(2026, 6, 7)`.
   - Assert: `realised_gain_eur_ytd == €100`. (2025's €50 is excluded.)
3. **`test_empty_transactions_with_as_of_returns_empty_dict`** — edge case.
   - `compute_positions([], as_of=date(2026, 6, 7))` returns `{}`. (No crash on the removed `latest_year = 0` path.)
4. **`test_position_with_no_sells_has_zero_ytd_in_current_year`** — edge case.
   - BUY 10 in 2025, no sells. `as_of=date(2026, 6, 7)`. `realised_gain_eur_ytd == €0`.

Each test that touches a call site outside `test_fifo.py` (e.g. `test_manage_form_pipeline.py`) gets `as_of` threaded through with no other intent change.

---

## Out of scope

- **Property-based FIFO tests with Hypothesis.** Tracked separately as the planned TICKET-TAX-3. This ticket does not add property tests.
- **The `Money` rounding accumulation issue** (`normalize_amount` quantizes at 4dp on every operation; multi-lot multiplication compounds rounding). Real concern but a different change; out of scope here.
- **Per-lot YTD attribution.** Currently `realised_gain_eur_ytd` is a portfolio-level field on `Position`. Not changing the data model in this ticket.
- **UI banners for "year just rolled over."** If a user crosses the year boundary mid-session, Streamlit's caching may serve stale data — not this ticket's job.
- **Refactoring the duplicated BUY-lot-creation block** between `compute_positions` and `compute_realised_gains`. Tempting while editing the file; resist. New ticket if desired.
- **Auditing or migrating the Sparerpauschbetrag / Verlustverrechnungstopf calculation** in `app/domain/tax/`. Those services consume `Position.realised_gain_eur_ytd`; once the input is correct, their output is correct without further changes.

---

## Notes / assumptions

- **Assumes** the call sites listed under "Files likely touched" are exhaustive. Final grep before editing: `grep -rn "compute_positions(" --include="*.py" .`. If a caller exists that isn't listed, update it and note in the PR body. Do NOT silently default `as_of` to keep an unlisted caller compiling — pass an explicit value.
- **Assumes** `app/services/valuation.py` already has an `as_of: date` in scope at the call site (it computes valuations against an `as_of`). Verify before editing; if not, take it as a parameter on the surrounding function rather than reading the clock.
- **Assumes** `app/services/nav.py` iterates over a sequence of historical dates when reconstructing NAV history; the per-iteration date is the correct `as_of` for that call. Verify the iteration variable's name and pass it through.
- **Assumes** UI page callers (`catalysts.py`, `manage.py`, `analytics.py`) either already have a "today" / valuation date in their render path, or can accept one from the page-level `as_of` helper if there is one. If not, the page function takes `as_of: date = date.today()` at its boundary and threads it down — `date.today()` is permitted at the UI boundary, not in domain or services.
- **Assumes** no consumer of `Position` relies on the old (buggy) behaviour. If any service quietly relied on YTD-as-latest-data-year for backtest reasons, that's a real bug discovery — stop and report per the AGENTS.md Stop Conditions list. Do not preserve buggy behaviour.
- The `**Status:**` line is decorative per METHODOLOGY.md. Omitted intentionally; board column is authoritative.
- Module-level constraint reminder: `app/domain/CLAUDE.md` forbids `datetime.now()` and file I/O in domain code. The fix respects this — `as_of` is injected, not read.
