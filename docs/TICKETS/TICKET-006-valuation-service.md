# TICKET-006 — Valuation service (compute_live_positions, compute_portfolio_summary)

**Status:** READY
**Priority:** P0
**Estimated session length:** 1 – 1.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-03)
**Implemented by:** _pending_
**Depends on:** TICKET-001 (domain models), TICKET-002 (FIFO engine), TICKET-004-005 (price + FX adapter)

---

## Problem

We have all three foundational pieces:
- Domain models (`Transaction`, `Money`, `Position`, `RealisedGain`)
- FIFO engine (`compute_positions`, `compute_realised_gains`)
- Live data ports + yfinance adapter (`PriceProvider`, `FxProvider`)

What we're missing: the **orchestration layer** that combines them into something the UI can render. The UI doesn't want to call FIFO + 6 prices + 2 FX rates and assemble the result itself; the UI wants to call one function and get back a dict of `LivePosition` objects with everything pre-computed.

This ticket builds that orchestration. It is the **first service** in `app/services/`, and the patterns established here (function-not-class, dependency injection of ports, no internal state, per-item failure isolation) are templates every later service follows.

---

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-03:

1. **The service layer is stateless by contract.** No `@lru_cache`, no module-level dicts, no class-with-state. Services are pure functions that take ports as parameters and return immutable results. Caching lives only at the adapter layer (TICKET-004-005) and the Streamlit UI layer (TICKET-008). This keeps cache invalidation predictable: the user clicks Refresh, the UI calls `clear_caches()` once, both real cache layers are flushed, no middle layer to forget about.

2. **Two new domain types: `LivePosition` and `PortfolioSummary`.** `Position` (TICKET-001) represents the book-of-record state — what you own and what it cost. `LivePosition` extends that with the live-valuation overlay — current price, current value, unrealised gain. `PortfolioSummary` is the aggregated KPI-tile data. Both frozen, both in `app/domain/positions.py` since they're conceptual extensions of `Position`.

3. **Per-ticker failure isolation.** If yfinance returns an error for NVDA, the NVDA `LivePosition` has `live_*` fields set to `None` and a `staleness_reason` string. RHM.DE and the rest still compute normally. The portfolio doesn't fail because one ticker failed. The UI can then render NVDA as "—" while everything else displays correctly.

4. **FX failure is portfolio-wide.** If `get_current_rate(USD, EUR)` itself fails, *all* USD positions become stale (we can't translate them). EUR positions are unaffected. The summary's `staleness` field reflects this distinction: `"live"` (all good), `"partial"` (some tickers failed), `"stale"` (FX failed, USD positions unusable).

5. **Service layer files have no I/O imports.** No `streamlit`, no `requests`, no `yfinance`. Same purity rule as the domain layer, but slightly relaxed: services may import from `app.domain` AND `app.ports` (the latter is the difference). Adapters and UI are off-limits.

---

## Acceptance criteria

### New domain types in `app/domain/positions.py`

#### `LivePosition` — frozen Pydantic model

- [ ] `LivePosition` extends nothing structurally — it's a sibling of `Position`, not a subclass. Fields:
  - `position: Position` — the book-of-record snapshot from the FIFO engine
  - `live_price_native: Money | None` — current price per share in trade currency; `None` if price fetch failed
  - `live_value_eur: Money | None` — `position.open_shares * live_price_native * fx_to_eur`; `None` if any input is missing
  - `unrealised_gain_eur: Money | None` — `live_value_eur - position.cost_basis_eur`; `None` if `live_value_eur` is `None`
  - `unrealised_gain_pct: Decimal | None` — `(unrealised_gain_eur / position.cost_basis_eur) * 100` as a percentage; `None` if numerator missing or cost basis is zero
  - `current_fx_rate: Decimal | None` — the current rate used; `None` for EUR-native positions OR if FX failed
  - `staleness_reason: str | None` — human-readable explanation when any live field is `None`. Example: `"yfinance returned no current price for NVDA"` or `"FX rate USD/EUR unavailable"`
- [ ] Class validator: if `live_price_native` is `None`, all of `live_value_eur`, `unrealised_gain_eur`, `unrealised_gain_pct` must also be `None`. (Cannot have value without price.)
- [ ] Class validator: `staleness_reason` is non-`None` if and only if `live_price_native is None or live_value_eur is None`.
- [ ] Helper property `is_stale: bool` — returns `True` if any live field is `None`.
- [ ] Helper property `ticker: str` — convenience proxy to `self.position.ticker`.

#### `PortfolioSummary` — frozen Pydantic model

- [ ] Fields:
  - `total_value_eur: Money` — sum of all `live_value_eur` (skipping `None`s); always EUR
  - `total_cost_basis_eur: Money` — sum of `position.cost_basis_eur` across positions (this never has `None`s); always EUR
  - `total_unrealised_gain_eur: Money` — `total_value_eur - total_cost_basis_eur` over the *non-stale* positions only. **Important:** if some positions are stale, the summary's gain is computed over the live ones only, not the whole portfolio. The UI shows this as "+€X (across N of M positions)" so the user knows it's partial.
  - `total_unrealised_gain_pct: Decimal` — gain divided by cost basis of the same non-stale subset
  - `total_realised_gain_eur_ytd: Money` — sum of `position.realised_gain_eur_ytd` across all positions (no live data needed)
  - `position_count: int` — how many `LivePosition` objects total
  - `live_position_count: int` — how many had complete live data
  - `staleness: Literal["live", "partial", "stale"]` — `"live"` if `live_position_count == position_count`; `"stale"` if `live_position_count == 0` (FX likely down, can't price anything); `"partial"` otherwise
  - `as_of: datetime` — when the summary was computed; passed in by the caller (the service does not call `datetime.now()`)

### `app/services/__init__.py`

- [ ] Empty file or just a docstring explaining the layer's purpose. No code.

### `app/services/CLAUDE.md` — new per-module instruction file

- [ ] Brief file (~30 lines) covering:
  - The service layer is stateless. No caches, no module-level mutable state, no `@lru_cache`.
  - Services are functions, not classes, unless state is genuinely required (it isn't here).
  - Services accept ports as parameters (dependency injection). They never construct adapters.
  - Services may import from `app.domain` and `app.ports`. Never from `app.adapters` or `app.ui`.
  - Service errors are caught at the *boundary* of the service (per-ticker isolation), not propagated to the UI.
  - The two-cache architecture: adapter cache (60s TTL) below, Streamlit cache above. The service is the stateless middle.

### `app/services/valuation.py` — the orchestration

#### `compute_live_positions`

```python
def compute_live_positions(
    transactions: Sequence[Transaction],
    price_provider: PriceProvider,
    fx_provider: FxProvider,
) -> dict[str, LivePosition]:
    ...
```

- [ ] Steps:
  1. Call `compute_positions(transactions)` from the FIFO engine. This returns `dict[str, Position]`.
  2. Try to fetch `usd_to_eur = fx_provider.get_current_rate(USD, EUR)`. If this raises `FxRateUnavailableError`, set `usd_to_eur = None` and remember that all USD positions will be stale.
  3. For each ticker in the FIFO result:
     - Try `price_provider.get_current_price(ticker)`.
     - If price native currency is EUR → no FX needed; compute `live_value_eur` directly.
     - If price native currency is USD and `usd_to_eur is not None` → translate to EUR.
     - If price native currency is USD and `usd_to_eur is None` → mark as stale with reason `"FX rate USD/EUR unavailable"`.
     - On `PriceUnavailableError` from the provider, mark stale with the error's `.reason`.
  4. Build a `LivePosition` for each ticker, populated or stale.
  5. Return the dict.
- [ ] **Critical: per-ticker errors do not abort the loop.** Each ticker is in its own try/except. One failure does not affect another.
- [ ] **Logging:** when a ticker is marked stale, the service does NOT log to stdout/stderr (services are silent). The `staleness_reason` string is the entire feedback channel; the UI is responsible for displaying it. (We avoid logging because Streamlit's stdout is noisy and per-ticker print statements are useless in production.)

#### `compute_portfolio_summary`

```python
def compute_portfolio_summary(
    live_positions: dict[str, LivePosition],
    as_of: datetime,
) -> PortfolioSummary:
    ...
```

- [ ] Steps:
  1. Filter `live_positions.values()` into two groups: those with complete live data (`not is_stale`) and the rest.
  2. Compute `total_value_eur` and `total_unrealised_gain_eur` from the live group only.
  3. Compute `total_cost_basis_eur` from ALL positions (cost basis never has live failures).
  4. Compute `total_realised_gain_eur_ytd` from ALL positions.
  5. Compute `position_count` and `live_position_count`.
  6. Determine `staleness`:
     - `live_position_count == position_count` → `"live"`
     - `live_position_count == 0 and position_count > 0` → `"stale"`
     - else → `"partial"`
  7. Build and return the `PortfolioSummary`. Empty portfolio (`position_count == 0`) returns a summary with all-zero EUR Money values, `staleness="live"`.
- [ ] No port calls in this function — it's pure aggregation over the input.

#### `clear_caches`

```python
def clear_caches(
    price_provider: PriceProvider,
    fx_provider: FxProvider,
) -> None:
    ...
```

- [ ] Two-line implementation: call `price_provider.clear_cache()` and `fx_provider.clear_cache()`.
- [ ] This is the single entry point the UI uses for "Refresh." Why a service-layer wrapper rather than calling adapters directly from the UI? Because the UI does not import adapters (architectural rule — `import-linter` enforces this). The UI imports from `app.services` only.

### Tests

#### `tests/unit/services/__init__.py`

- [ ] Empty init.

#### `tests/unit/services/test_valuation.py`

All tests use `FakePriceProvider` and `FakeFxProvider` from `tests/fakes/` (created in TICKET-004-005). Zero network access.

##### Happy path
- [ ] **Single EUR position, fully live**: 1 buy of 4 RHM.DE at €1142, current price €1142, no FX needed. Result: one `LivePosition` with all live fields populated, `is_stale=False`. Summary: `staleness="live"`.
- [ ] **Single USD position, fully live**: 1 buy of 12 NVDA at $887.42, fx_rate_eur=0.92. Current price $750, current fx EUR/USD=1.10 (so 1 USD = 0.909 EUR). LivePosition has `live_value_eur` correctly computed. Verify the math precisely: shares × price × fx.
- [ ] **Mixed portfolio, all live**: 2 EUR positions + 2 USD positions. All resolve. Summary `staleness="live"`, `position_count=4`, `live_position_count=4`.
- [ ] **Empty portfolio**: `compute_live_positions([], ...)` returns `{}`. Summary has zeros and `staleness="live"`.

##### Per-ticker failure isolation
- [ ] **One ticker fails, others succeed**: 3 positions, FakePriceProvider configured to raise `TickerNotFoundError` for one ticker. Result: 3 `LivePosition`s; one has `is_stale=True` with the error reason; other two are live. Summary: `staleness="partial"`, `live_position_count=2`.
- [ ] **Per-ticker exception does not abort loop**: configure two failures and one success in alternating order. Verify both failures are surfaced and the success is unaffected.

##### FX failure
- [ ] **FX provider raises**: FakeFxProvider configured to raise `FxRateUnavailableError`. All USD positions become stale with reason `"FX rate USD/EUR unavailable"`. EUR positions remain live. Summary: `staleness="partial"` (assuming both currencies present); or `"stale"` if all positions are USD.
- [ ] **FX failure with all-EUR portfolio**: should still be `staleness="live"` because no position needed FX.

##### Math correctness
- [ ] **`unrealised_gain_eur = live_value_eur - cost_basis_eur`**: for a known input, assert exact match.
- [ ] **`unrealised_gain_pct` formula**: 10 NVDA bought at €100/share (cost €1000), current value €1100, gain pct = 10.00.
- [ ] **`unrealised_gain_pct` is `None` when cost basis is zero**: synthetic edge case.
- [ ] **Summary aggregates over live subset only**: 2 live positions worth €100 and €200, 1 stale; summary `total_value_eur` = €300 (not the stale one).
- [ ] **Cost basis aggregates over ALL positions**: same setup; `total_cost_basis_eur` includes the stale position's cost basis (the cost is known regardless of live data).

##### Statelessness (the negative test that catches accidental caching)
- [ ] **`test_service_has_no_state`**: call `compute_live_positions(...)` twice with identical inputs. Both calls must invoke the price provider the same number of times. Use a counting `FakePriceProvider` that increments on each call. After two service calls with 4 tickers each, the counter should be 8, not 4. (If somebody adds `@lru_cache` to the service, this test fails.)
- [ ] **`test_service_no_module_state`**: import `app.services.valuation` and verify there are no module-level dict, list, or class instances that hold state across calls. Implementation: introspect with `inspect.getmembers` and assert all module attributes are functions or imports.

##### `clear_caches`
- [ ] **`clear_caches` calls both providers**: pass mock providers that record the call. After `clear_caches()`, both `clear_cache` methods invoked exactly once.

### Lints / quality
- [ ] `pytest` — all tests pass
- [ ] `ruff check .` — passes
- [ ] `mypy app/` — passes; `app/services/` is checked under standard (not strict) mode but should be clean
- [ ] `lint-imports` — passes; specifically:
  - `app.services.valuation` imports from `app.domain` and `app.ports` only
  - `app.services.valuation` does NOT import `app.adapters.*` or `app.ui.*` or `streamlit` or `yfinance`

### State updates (per CLAUDE.md session-end ritual)
- [ ] `docs/SESSION_LOG.md` appended
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-006 → IN_REVIEW)
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-006 row → IN_REVIEW)
- [ ] Ticket file `Status: IN_REVIEW`
- [ ] PR opened via `gh pr create --fill --base main`

---

## Files created

```
app/services/CLAUDE.md
app/services/valuation.py
tests/unit/services/__init__.py
tests/unit/services/test_valuation.py
```

## Files modified

```
app/domain/positions.py        ← add LivePosition and PortfolioSummary
app/domain/__init__.py         ← export LivePosition, PortfolioSummary
app/services/__init__.py       ← (likely empty, just confirm it's a package)
docs/TICKETS/BACKLOG.md        ← TICKET-006 row → IN_REVIEW
```

---

## Out of scope

- Streamlit `@st.cache_data` integration — explicitly TICKET-008's job
- The `clear_caches` button itself — TICKET-008
- Any UI rendering — TICKET-007 + TICKET-008
- Performance time-series (charting NAV over time) — TICKET-013/014
- Tax calculations (Sparerpauschbetrag) — TICKET-010
- Decision gates / thesis state — TICKET-016+

---

## Notes (architectural and methodological — for future AI sessions)

### The two-cache architecture (why this service has none)

```
USER CLICKS "Refresh" or changes a transaction
         │
         ▼
Layer 3: Streamlit @st.cache_data         [TICKET-008]
   Caches compute_live_positions() by inputs.
   Invalidated by: Refresh button OR transaction edit.
         │ cache miss
         ▼
Layer 2: Valuation service                [THIS TICKET]
   Pure orchestration. NO STATE.
   Calls FIFO + ports. Returns immutable result.
         │
         ▼
Layer 1: Adapter cache                    [TICKET-004-005]
   60s TTL on current data, infinite on historical.
   Invalidated by: clear_cache().
```

The service has no cache *on purpose*. If it did, the Refresh button would have to invalidate three layers in correct order, and any ordering bug produces inconsistent state (Streamlit shows fresh service results computed from stale adapter data, etc.). With caching only at layers 1 and 3, invalidation is two independent operations: `service.clear_caches(adapters)` and `st.cache_data.clear()`. Both happen on Refresh. No ordering matters.

This is why the negative test `test_service_has_no_state` exists. If a future Claude Code session is "optimizing" and adds an `@lru_cache` here, that test fails immediately.

### Why functions, not classes

A `ValuationService` class with `__init__(self, price_provider, fx_provider)` would be perfectly reasonable. We're not doing it because:
1. There's no state to encapsulate (no caches, no config, no resources).
2. Functions with explicit parameters are easier to test (no fixture for a service object).
3. They're easier to compose in pipelines (`compute_portfolio_summary(compute_live_positions(...))` reads naturally).
4. Matches the pure-function discipline of the domain layer.

If a future service genuinely needs state (say, a connection pool or a request batcher), use a class then. Until then: functions.

### Why per-ticker error handling, not global

A USD price feed can fail for one ticker (delisted, typo, yfinance hiccup) while everything else is fine. Aborting the whole portfolio because NVDA failed would be a bad UX. The user wants to see "5 of 6 positions live, NVDA showing as stale" — which is exactly what this service produces.

The contract: `compute_live_positions` never raises. It returns a dict where each entry might be partly or fully populated. The UI is the layer that interprets `is_stale` and renders accordingly.

### Why `as_of` is a parameter, not `datetime.now()`

Same reason as the FIFO engine: testability. Tests need to assert specific times in the summary. The UI passes `datetime.now()` at the top of the call chain; everything below is deterministic given that input.

### How the UI will use this service (TICKET-008 preview, for context only)

```python
import streamlit as st
from app.services.valuation import compute_live_positions, compute_portfolio_summary, clear_caches

@st.cache_data
def cached_live_positions(transactions_signature):
    # Streamlit cache. Re-runs when transactions_signature changes.
    return compute_live_positions(transactions, price_provider, fx_provider)

if st.button("Refresh"):
    clear_caches(price_provider, fx_provider)
    st.cache_data.clear()
    st.rerun()
```

The `transactions_signature` trick is needed because Streamlit can't hash arbitrary objects; we'll pass a stable hash of transaction IDs. Details in TICKET-008.

### Methodology note (for future AI sessions reading this)

This ticket is shorter than TICKET-004-005 (337 lines) because the patterns it relies on are already established. Future tickets will be even shorter — the cache architecture is documented here, the dependency injection pattern is shown, the per-item failure isolation is templated. New service tickets just say "follow TICKET-006's pattern" and reference this file.

The first ticket of a kind is verbose; the tenth is short. This is the second service-layer ticket precedent (after the conceptual `clear_caches` helper) — every later service follows its lead.
