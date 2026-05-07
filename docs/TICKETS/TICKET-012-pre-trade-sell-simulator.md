# TICKET-012 — Pre-trade sell simulator (FIFO lot preview + tax impact + portfolio impact)

**Status:** MERGED
**Priority:** P1
**Estimated session length:** 2.5 – 3 hr
**Drafted by:** Vivek + Claude (chat 2026-05-04)
**Implemented by:** _pending_
**Depends on:** TICKETs 001 (domain), 002 (FIFO + RealisedGain), 003 (repo), 006 (valuation), 007 (UI shell), 008 (Live Overview), 008c (currency correctness), 009-revised (Manage Portfolio), **010 (tax engine)**, **011 (Tax Dashboard service layer)**.

> **After this ticket merges, the user can answer "what happens if I sell N shares of X right now?" without typing a real transaction.** The answer covers (a) which FIFO lots get consumed, (b) the realised gain in EUR, (c) the marginal tax bill, (d) the post-sell Sparerpauschbetrag state, and (e) the portfolio weight change. All before any data is written.

---

## Problem

The Tax Dashboard's harvest table (TICKET-011) shows static "if you sold the whole position" numbers. But real trades are partial: "I want to trim 3 shares of NVDA, not all 12." There is no way today to ask the dashboard "show me what 3 shares of NVDA does to my tax position before I execute."

The Manage Portfolio form (TICKET-009-revised) handles persistence — it accepts a sell and writes a `Transaction`. It runs FIFO validation (`SellExceedsOpenSharesError` is caught and surfaced). But it does NOT preview the consequences. The user sees only "transaction recorded" or "error: cannot sell more than open." Nothing about which lots were consumed, what gain was realised, or what tax that adds.

This ticket adds the **simulator**: an interactive panel that takes a hypothetical sell and previews everything before any state changes. Two ways to access it:

1. From a position's row on the Live Overview or Tax Dashboard: a "Simulate sell…" button opens the simulator pre-filled with that ticker.
2. As a top-level page (`app/ui/pages/simulator.py`) for unblocked exploration.

The simulator is **read-only**. It does not write transactions. Following any simulated trade, a "Record this trade" button hands off to Manage Portfolio with the form pre-filled — the user reviews and submits there. This separation is deliberate (see decision §4 below).

---

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-04.

### 1. The simulator is a read-only computation; the writer is Manage Portfolio.

The simulator exposes one service entry point: `simulate_sell(ticker, shares, sell_price_native, sell_fx_rate, profile, transactions, live_positions, current_summary) -> SellSimulation`. It runs FIFO mentally (without writing), then runs the tax engine mentally (without writing), then assembles a `SellSimulation` snapshot. **Nothing in the simulator path mutates state.**

If the user clicks "Record this trade" the page navigates to Manage Portfolio's Edit form with `st.session_state.simulator_handoff` populated; Manage Portfolio's submit pipeline takes over. This is the only writer.

Why split: the bug surface is much smaller. The simulator does not need atomic-write logic, it does not need cache invalidation, it does not need to clear `st.cache_data` correctly. It just computes and returns a frozen result. The writer logic already exists and is already tested.

### 2. The simulator runs FIFO via a *targeted* pure helper, not by re-running `compute_positions`.

`compute_positions(transactions + [hypothetical_sell])` would work but does triple the work needed: it processes every other ticker's transactions too. A new pure helper `simulate_lot_consumption(open_lots, shares_to_sell, sell_tx) -> tuple[list[RealisedGain], tuple[OpenLot, ...]]` does only the relevant slice. Pure, no I/O, single-ticker. Lives in `app/domain/fifo.py` next to `_consume_from_lots` (TICKET-002 made that helper internal; this ticket promotes the same logic to a public helper).

The promoted helper is exactly the consume-or-split-front-lot logic from TICKET-002, refactored to take `open_lots: tuple[OpenLot, ...]` and `shares_to_sell: Decimal` and return the realised gains and the resulting `open_lots` after consumption. It does NOT take a transaction list, does NOT do calendar-year filtering, does NOT compute YTD aggregates. It is one tightly-scoped operation. Same algorithm, smaller surface.

### 3. The tax-impact preview reuses TICKET-011's `compute_per_position_harvest_impact`-style math, but for partial sells.

`compute_per_position_harvest_impact` (TICKET-011) computes "tax impact if you sell *the whole position*." The simulator wants "tax impact if you sell *N specific shares*." The mechanism is the same — synthesise hypothetical `RealisedGain`s, run the tax engine, take the diff — but the inputs are different.

Rather than parametrise `compute_per_position_harvest_impact`, this ticket adds a sibling: `compute_marginal_tax_for_realised_gains(current_summary, hypothetical_gains, profile) -> MarginalTaxImpact`. It takes already-computed `RealisedGain`s (whatever produced them), runs the engine with them appended, and returns the marginal numbers. The simulator passes the FIFO output of the hypothetical sell. The harvest table can later be refactored to use this same helper (deferred — not in this ticket's scope).

### 4. The simulator validates *before* computing.

If `shares_to_sell > position.open_shares`, the simulator returns a `SellSimulation` with `is_valid=False` and a `validation_error: SellExceedsOpenSharesError`. The page renders the error inline and skips the impact preview. **No half-rendered preview** — same loud-fail discipline as TICKET-008c.

If the position's live price is stale (FX down or per-ticker failure), the simulator can still run if the user provides a manual "assumed sell price" (the simulator UI surfaces this fallback explicitly with a banner). It cannot silently substitute the cost basis, the last-known price, or any other "best guess" — the user picks a number consciously or the simulator refuses.

### 5. The simulator's UI lives at `app/ui/pages/simulator.py` AND `app/ui/components/sell_simulator.py`.

The component is the embeddable panel; the page is a simple wrapper around the component with a ticker selector at the top. The component is what gets opened from a "Simulate sell…" button on Live Overview or Tax Dashboard rows. Same panel, two entry points.

### 6. The simulator does not show speculative future numbers.

Some pre-trade tools show "after this sell, in 1 year your portfolio will be worth €X based on Y% expected return." We do NOT. No expected-return modelling. The simulator is *strictly* about today's deterministic facts: which lots get consumed, what gain that produces, what tax that triggers, what allowance state results. Anything probabilistic belongs to a different feature (TICKET-016+).

### 7. The simulator surfaces the FIFO lot consumption explicitly.

The user wants to know which buy lots are being sold against. If they bought 1 share at €100 in 2024 and 1 share at €200 in 2026, and they sell 1 share today at €250, FIFO disposes the €100 lot — €150 gain, not €50 gain. This is non-obvious. The simulator shows a small table:

| Lot | Buy date | Shares | Cost/share (EUR) | Sell price (EUR) | Realised gain (EUR) |
|---|---|---|---|---|---|
| #1 | 2024-08-01 | 1.00 | 97.50 | 250.00 | +152.50 |

This is the central UX value — the user understands the FIFO consequence at a glance.

---

## Acceptance criteria

### `app/domain/fifo.py` — promote helper to public

- [ ] Promote the existing internal `_consume_from_lots` (TICKET-002) to a public `simulate_lot_consumption(open_lots: tuple[OpenLot, ...], shares_to_sell: Decimal, sell_tx: Transaction) -> tuple[list[RealisedGain], tuple[OpenLot, ...]]`. **Pure**: takes immutable inputs, returns immutable outputs. No side effects. Same algorithm; same `SellExceedsOpenSharesError` on over-sell.
- [ ] The original internal callsite inside `compute_realised_gains` is refactored to call the public function. No behavioural change to FIFO; the change is purely a visibility promotion.
- [ ] Add unit tests `tests/unit/domain/test_simulate_lot_consumption.py` for the promoted function:
  - Single lot, exact shares: one RealisedGain, empty remaining.
  - Single lot, partial shares: one RealisedGain, lot reduced.
  - Multiple lots, crosses boundary: two RealisedGains, partially-consumed front lot remaining.
  - Over-sell: raises `SellExceedsOpenSharesError`.
  - Empty lots: raises immediately.
  - Order preservation: lots return in input order minus consumed prefixes.

### `app/services/tax_planning.py` — add a sibling function

- [ ] `compute_marginal_tax_for_realised_gains(current_summary: TaxYearSummary, hypothetical_gains: Sequence[RealisedGain], profile: TaxProfile) -> MarginalTaxImpact`.
  - Run `compute_tax_year_summary` with `current_summary`'s implicit transactions plus the hypothetical gains. The simplest implementation reconstitutes by passing `current_summary.realised_gain_impacts` plus the new gains; or, more simply, takes both `current_transactions` and the synthesised `Transaction` of the proposed sell as inputs.
  - **Decision:** the function takes a `current_transactions: Sequence[Transaction]` parameter and a `proposed_sell: Transaction` parameter. The current summary is recomputed inside. This is one additional call to the tax engine, but the engine is O(N) over realised gains, so the cost is negligible compared to the clarity of the API.
  - Returns `MarginalTaxImpact` (Pydantic frozen):
    - `before_summary: TaxYearSummary`
    - `after_summary: TaxYearSummary`
    - `marginal_taxable_gain_eur: Money` (after − before, in `total_taxable_after_loss_offset_eur`)
    - `marginal_allowance_consumed_eur: Money` (after − before, in `sparerpauschbetrag_consumed_eur`)
    - `marginal_aktien_carryforward_change_eur: Money` (after − before, in `aktien_pot.remaining_carryforward_eur`)
    - `marginal_general_carryforward_change_eur: Money` (same for general pot)
    - `marginal_abgeltungsteuer_eur: Money`
    - `marginal_solidaritaetszuschlag_eur: Money`
    - `marginal_total_tax_owed_eur: Money`

### `app/services/sell_simulator.py` — new service

- [ ] `SellSimulation` — frozen Pydantic model. The full simulation result. Fields:
  - `request: SellSimulationRequest` (echoed input for round-tripping into the writer)
  - `is_valid: bool`
  - `validation_error: str | None` (human-readable; `None` if valid)
  - `lot_consumption: tuple[LotConsumption, ...]` (per-lot breakdown; empty if invalid)
  - `realised_gains: tuple[RealisedGain, ...]` (one per consumed lot fragment)
  - `total_realised_gain_eur: Money`
  - `marginal_tax: MarginalTaxImpact | None` (`None` if invalid)
  - `position_after: PositionAfterSnapshot | None` (`None` if invalid)
- [ ] `SellSimulationRequest` — frozen Pydantic model:
  - `ticker: str`
  - `shares: Decimal`
  - `sell_price_native: Money`
  - `sell_fx_rate_eur: Decimal`
  - `sell_date: date`
- [ ] `LotConsumption` — frozen Pydantic model. One row of the lot-consumption table:
  - `lot_index: int` (1-based for display)
  - `buy_transaction_id: str`
  - `buy_date: date`
  - `shares_consumed: Decimal`
  - `cost_per_share_native: Money`
  - `cost_per_share_eur: Money` (cost_per_share_native * fx_rate_eur)
  - `sell_price_eur: Money` (sell_price_native_eur)
  - `realised_gain_eur: Money` (the per-lot gain)
- [ ] `PositionAfterSnapshot` — frozen Pydantic model. The post-sell view:
  - `open_shares_after: Decimal`
  - `cost_basis_eur_after: Money`
  - `unrealised_gain_eur_after: Money | None` (None if live price unavailable)
  - `weight_pct_before: Decimal | None`
  - `weight_pct_after: Decimal | None`
  - `weight_change_pct: Decimal | None` (after − before)
- [ ] `simulate_sell(request: SellSimulationRequest, transactions: Sequence[Transaction], profile: TaxProfile, live_positions: dict[str, LivePosition]) -> SellSimulation`:
  - **Step 1**: derive `open_lots` for the ticker from `compute_positions(transactions)`. If the ticker has no open position, return `SellSimulation(is_valid=False, validation_error="No open position for {ticker}.", ...)`.
  - **Step 2**: Build a hypothetical `Transaction(type=SELL, ticker=request.ticker, shares=request.shares, price_native=request.sell_price_native, fx_rate_eur=request.sell_fx_rate_eur, trade_date=request.sell_date, …)`. The TICKET-008c validator runs and may raise on ticker/currency mismatch — surface as validation error.
  - **Step 3**: try `simulate_lot_consumption(position.open_lots, request.shares, hypothetical_sell)`. If `SellExceedsOpenSharesError`, return `is_valid=False` with the error's message.
  - **Step 4**: compute `marginal_tax = compute_marginal_tax_for_realised_gains(current_transactions=transactions, proposed_sell=hypothetical_sell, profile=profile)`. The before-and-after summaries are returned.
  - **Step 5**: compute `position_after`:
    - `open_shares_after = position.open_shares - request.shares`
    - `cost_basis_eur_after = sum of remaining open lots' cost_basis_eur`
    - `unrealised_gain_eur_after`: if `live_positions[ticker].live_price_native is not None`, recompute. Else `None`.
    - Weight: `live_position.live_value_eur / portfolio_total_value_eur`. After: `(live_value_eur - shares × sell_price_eur) / (portfolio_total_value_eur - shares × sell_price_eur)`. Both `None` if any input stale.
  - **Step 6**: assemble and return `SellSimulation(is_valid=True, ...)`.
- [ ] **The function is pure**: same input → same output.
- [ ] **Per-failure isolation**: any one of the steps that can produce a partial result still produces a `SellSimulation` with as much info as possible. E.g., if the marginal tax computation fails (it should not, but if it does), `marginal_tax = None` and the page renders only the lot consumption.
  - *On reflection: this is over-engineering for a path that should not fail. Simpler: any unexpected failure in step 4 or 5 raises and the page catches at top level.* The simulator service is allowed to raise on truly unexpected errors. Validation errors (steps 1, 2, 3) become `is_valid=False`; everything else propagates.

### `app/ui/components/sell_simulator.py` — new component

This is the embeddable panel. It is rendered inside the simulator page and inside any future row-level "Simulate sell…" affordance.

- [ ] `render_sell_simulator(default_ticker: str | None = None) -> None`:
  - Renders a `st.form` with: ticker (selectbox of available open positions), shares (number_input), sell_date (date_input, default today), sell price source toggle (Live | Manual).
    - **Live**: pre-fills `sell_price_native` from `live_position.live_price_native`. If stale, this option is disabled with a tooltip "Live price unavailable; switch to Manual to override."
    - **Manual**: shows native-price + FX-rate fields. Same fields as the TICKET-009-revised fallback mode. Default the FX rate to `live_position.current_fx_rate` if available, else require user input.
  - On Submit: call `simulate_sell(...)`. Display the result.
- [ ] **Result rendering** (when `is_valid=True`):
  - **Header**: `"Simulating: SELL {shares} {ticker} on {date} at {price_native}"` with the implied EUR proceeds.
  - **Lot Consumption table**: columns Lot, Buy Date, Shares, Cost/Share (EUR), Sell Price (EUR), Realised Gain (EUR). Sorted by lot_index. Each row's gain coloured green/red.
  - **Realised Gain summary line**: `"Total realised gain: {total_realised_gain_eur}"` with sign coloring.
  - **Tax Impact panel** (3 columns):
    - Marginal Taxable Gain
    - Marginal Allowance Consumed (with running headroom display: `"€{remaining_after} of €{total} left"`)
    - Marginal Tax Owed (Abgeltungsteuer + Soli, broken out)
  - **Position After panel** (3 columns):
    - Open Shares After (with delta indicator)
    - Cost Basis After (with delta)
    - Weight After (with delta as percentage point change)
  - **"Record this trade" button**: writes `st.session_state.simulator_handoff = SellSimulationRequest(...)`, navigates to Manage Portfolio. Manage Portfolio's Add form pre-fills from session_state. (TICKET-009-revised's form is the writer.)
- [ ] **Result rendering** (when `is_valid=False`):
  - Single yellow banner with the validation error message.
  - No tax/lot panels rendered.
- [ ] **Stale handling**:
  - If `live_position.is_stale`, the ticker is greyed in the selectbox and the live-price toggle starts in Manual mode. Banner above the form: `"Live price for {ticker} is unavailable ({reason}). Enter the price you would expect to execute at."`
  - If FX is stale and the position is non-EUR-native: same handling.

### `app/ui/pages/simulator.py` — new page

- [ ] Wraps `render_sell_simulator()` with a top header `"Pre-trade Sell Simulator"` and a brief description.
- [ ] If `st.session_state.simulator_default_ticker` is set (set by a row-level "Simulate sell…" button on another page), pass it to `render_sell_simulator(default_ticker=...)` and clear after one render.
- [ ] Adds the page to the sidebar navigation (TICKET-007's nav config).

### `app/ui/pages/overview.py` and `app/ui/pages/tax.py` — add row-level entry points

- [ ] Live Overview: each row in the positions table gets a small "Simulate sell" icon button. Click → set `st.session_state.simulator_default_ticker` and navigate to Simulator page.
- [ ] Tax Dashboard: each row in the Harvest Opportunity table gets the same affordance. Same handler.

### `app/ui/pages/manage.py` — accept handoff from simulator

- [ ] On render, if `st.session_state.simulator_handoff: SellSimulationRequest` is set:
  - Pre-fill the Add Transaction form with `type=SELL`, `ticker=<from request>`, `shares=<from request>`, `trade_date=<from request>`. The EUR-total field is pre-filled from `request.shares × request.sell_price_native × request.sell_fx_rate_eur`.
  - Clear `st.session_state.simulator_handoff` after one render (otherwise it sticks).
  - Banner at the top: `"Pre-filled from simulator. Review the values and click Submit to record."` so the user knows where the data came from.

### Tests

#### `tests/unit/domain/test_simulate_lot_consumption.py`

(Six cases, listed above.)

#### `tests/unit/services/test_sell_simulator.py`

- [ ] **Happy path: partial sell of NVDA**:
  - Portfolio has 1 NVDA buy lot of 12 shares at €100 cost basis.
  - Request: sell 5 shares at €120 EUR-equivalent.
  - Expected `SellSimulation`:
    - `is_valid=True`
    - `lot_consumption` length 1, `shares_consumed=5`
    - `total_realised_gain_eur = €100`
    - `marginal_tax.marginal_total_tax_owed_eur` matches engine output
    - `position_after.open_shares_after = 7`
- [ ] **Sell crossing two lots**:
  - Portfolio: NVDA buy 1 lot of 5 shares @ €100, NVDA buy 2 lot of 5 shares @ €110.
  - Request: sell 7 shares at €130.
  - Expected `lot_consumption`:
    - Row 1: lot 1, 5 shares, gain (130-100)*5 = €150
    - Row 2: lot 2, 2 shares, gain (130-110)*2 = €40
  - `total_realised_gain_eur = €190`.
- [ ] **Over-sell error**:
  - Portfolio has 5 shares; request 10.
  - `is_valid=False`, validation_error contains "5" and "10".
- [ ] **No-open-position error**:
  - Portfolio empty; request to sell NVDA.
  - `is_valid=False`, validation_error: "No open position for NVDA."
- [ ] **Pure / deterministic**:
  - Call `simulate_sell` twice with identical inputs; both `SellSimulation`s are equal.
- [ ] **Marginal allowance state when sale exhausts allowance**:
  - Pre-existing realised gains have consumed €600 of €1,000 allowance.
  - Request a sell that produces €600 of gain.
  - Expected: `marginal_allowance_consumed_eur = €400` (covered by remaining allowance), `marginal_taxable_gain_eur = €200`, marginal tax = €50 + €2.75 Soli = €52.75.
- [ ] **Aktien vs general pot interaction**:
  - Pre-existing 2026 realised: €500 ETF loss (post-Teilfreistellung €350 in general pot).
  - Request: sell NVDA position with €500 gain (AKTIE).
  - Expected: aktien gain €500 added to aktien-pot. General pot's €350 loss remains (firewall). Allowance applies to the €500 aktien gain → €0 taxable for the sell. Marginal tax = €0.
  - This is the test that catches a future bug where the simulator might incorrectly net the aktien gain against the general-pot loss.

#### `tests/unit/ui/test_sell_simulator_component.py`

- [ ] **Form pre-fill from session_state**: with `simulator_default_ticker="NVDA"`, the ticker selectbox starts at NVDA.
- [ ] **Stale-price banner appears**: with a stale `live_position`, banner text contains "Live price for NVDA is unavailable".
- [ ] **Record-this-trade handoff sets the right session_state key**: clicking the button populates `st.session_state.simulator_handoff` with the `SellSimulationRequest` of the simulated trade.

#### `tests/integration/test_simulator_e2e.py`

- [ ] End-to-end through the page: render the simulator, submit a valid sell, verify the rendered result has the expected sections.
- [ ] End-to-end with an invalid sell: render, submit over-sell, verify error banner shows and impact panels do NOT render.
- [ ] End-to-end handoff: simulate a sell, click Record-this-trade, navigate to Manage Portfolio, verify the form is pre-filled and the banner appears.

### Lints / quality

- [ ] `pytest` — all tests pass.
- [ ] `ruff check .` — passes.
- [ ] `mypy app/` — passes; strict mode on `app/domain/`.
- [ ] `lint-imports` — passes; `app.services.sell_simulator` imports `app.domain.*` and `app.ports.*` only. `app.ui.components.sell_simulator` imports from `app.services.*` and `app.ui.*`. Not from adapters. Not from `streamlit` bypassing render_html for HTML emission.
- [ ] Manual: `streamlit run app/ui/main.py`, navigate to Pre-trade Sell Simulator, run a few simulations including edge cases. Screenshots in PR description.

### State updates (per CLAUDE.md session-end ritual)

- [ ] `docs/SESSION_LOG.md` appended.
- [ ] `docs/PROJECT_STATE.md` updated.
- [ ] `docs/TICKETS/BACKLOG.md` updated.
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.

---

## Files created

```
app/services/sell_simulator.py
app/ui/components/sell_simulator.py
app/ui/pages/simulator.py
tests/unit/domain/test_simulate_lot_consumption.py
tests/unit/services/test_sell_simulator.py
tests/unit/ui/test_sell_simulator_component.py
tests/integration/test_simulator_e2e.py
```

## Files modified

```
app/domain/fifo.py                                ← promote _consume_from_lots to public simulate_lot_consumption
app/domain/__init__.py                            ← export the public helper
app/services/tax_planning.py                       ← add compute_marginal_tax_for_realised_gains
app/ui/pages/overview.py                           ← row-level "Simulate sell" affordance
app/ui/pages/tax.py                                ← row-level "Simulate sell" affordance
app/ui/pages/manage.py                             ← accept simulator handoff session_state
app/ui/components/sidebar.py                       ← add Simulator entry to nav
app/ui/styles/dark.css                             ← .lot-consumption-table, .simulator-impact classes
docs/TICKETS/BACKLOG.md                            ← TICKET-012 row → IN_REVIEW
README.md                                          ← brief mention of the simulator
```

## Files NOT to modify

- `app/domain/tax/*` — engine is fixed; this ticket consumes it.
- `app/domain/realised_gain.py`, `app/domain/models.py`, `app/domain/money.py` — no domain-model changes.
- `app/services/valuation.py` — left alone.
- `app/adapters/*` — no adapter changes.
- `app/ports/*` — no port changes.

If during implementation a different file *seems* to need changes, **stop and flag it in the PR description.** Do not silently expand scope.

---

## Out of scope

- **Buy simulation.** Same architectural pattern would work for buys ("what if I added 5 NVDA at $200?") but the user's actual decision support is more about sells (tax optimisation, portfolio rebalancing). Buy simulation can be a future ticket if it becomes needed; the architectural surface this ticket establishes (read-only service + component + page + handoff) is the template.
- **Multi-leg simulation.** Simulating "sell 3 NVDA AND sell 2 ETN today" in one go. Not in this ticket — the user runs the simulator twice. If multi-leg ever becomes a frequent flow, future ticket can add a queue.
- **Saving simulator scenarios.** No "save this scenario" or "compare scenarios A vs B" flow. The user runs and reviews; no persistence.
- **Predicted-price simulation.** "What if I assume NVDA grows 20% by year-end?" That is forecasting; out of scope. The simulator is for *now*.
- **Tax-loss-harvesting recommendations.** Static suggestions belong on the Tax Dashboard (TICKET-011's Loss Harvesting table). The simulator answers questions; it does not propose them.
- **Simulating against historical price**. "What would tax have been if I had sold last quarter at $X?" Out of scope.
- **Mobile-optimised layout for the simulator.** The component is desktop-first like the rest of the dashboard. Future ticket can address mobile if it matters.
- **Refactoring TICKET-011's harvest table to use `compute_marginal_tax_for_realised_gains`.** The new helper makes it possible to refactor the harvest table to share logic; left as a follow-up cleanup ticket.

---

## Test cases (selected, illustrative)

The most important test is the **"big lot/small lot interaction"** one because it catches the FIFO-misordering bug class:

**Scenario**: User holds 5 NVDA (bought 2025-05-12 at €100/share), 3 NVDA (bought 2026-04-15 at €150/share). Current price €130. User wants to sell 6 shares.

**Naive expectation** (what the user might think): "I am selling the higher-cost-basis lot to minimise gain." Reality: FIFO disposes the 2025 lot first, all 5 of those, then 1 share from the 2026 lot.

**Expected `SellSimulation`**:
- `lot_consumption[0]`: 5 shares from 2025 lot, gain (130-100)*5 = €150
- `lot_consumption[1]`: 1 share from 2026 lot, gain (130-150)*1 = -€20
- `total_realised_gain_eur = €130`
- `marginal_tax`: depends on existing summary; for an unused-allowance state, fully sheltered = €0.

The test asserts both rows of the table and the total. A future "fix" that lets the user pick lot order would break this test, which is the right outcome — lot order is not user-selectable in German FIFO.

---

## Notes (architectural and methodological — for future AI sessions)

### Why the simulator and writer are separate paths

A unified "simulator + writer" panel would be tempting. Showing a preview that auto-becomes-real on submit is good UX. But:

- The simulator gets called many times per session; the writer gets called rarely. Their performance budgets differ.
- The writer has cache-invalidation responsibilities (clear `st.cache_data`, optionally clear adapter caches). Mixing those into a hot path is asking for cache bugs.
- The writer has a side effect (file write). Anything with a side effect must be deliberately invoked, not accidentally tripped from a re-render.

The handoff via session_state is the explicit "now I want to commit" moment. The user clicks it; nothing happens until they click. That separation is worth the small extra step.

### Why the lot consumption table is the central UX

In every conversation about "should I sell some of X" with someone who is not a tax professional, the "which lot gets sold" question is the one they get wrong most often. They think in average-cost ("I bought NVDA at an average of €130, current is €145, so I have a gain of €15/share"). FIFO says no — the *oldest* lot is sold first, and that lot's cost is whatever it actually was.

Surfacing the lot-by-lot breakdown front-and-centre forces the user to confront the actual gain that will be realised. This is the dashboard's competitive advantage over the broker UI, which typically only shows position-level average cost.

### Why the marginal tax calculation runs the full engine, not a shortcut

A naive shortcut: "marginal tax = realised_gain × 0.26375." Wrong by a wide margin if the user has unused allowance, unconsumed losses, mixed pots, or Teilfreistellung-eligible positions. Running the full engine for the marginal calculation is O(N) over realised gains; the typical portfolio has tens of realised gains per year. The cost is negligible.

Pre-emptively defending against a future "performance optimisation" that replaces the engine call with the shortcut: the test `test_marginal_allowance_state` (above) would fail. The test exists specifically to catch this regression.

### Why we promote `simulate_lot_consumption` instead of running `compute_positions(transactions + [hypothetical])`

Both work. The shorter version is `compute_positions(transactions + [hypothetical])` and read the relevant ticker out. We do not, for two reasons:

1. The realised-gains output of `compute_positions` aggregates YTD; we want only the gains *from this single sell*. Filtering them out by transaction-id is fragile (what if a future enhancement adds metadata?).
2. The promoted helper makes the simulator's intent explicit in code: "I want the consequence of disposing N shares against these specific lots." That reads better than a list-concatenation trick.

The promoted helper is also the right primitive for a future TICKET-013 (lot ledger page) which will want to show "if I sold 3 shares right now, which lots would I be touching?" without recomputing the full FIFO across the portfolio.

### Why no expected-return modelling

The dashboard does not predict the future. It computes facts about now. Adding "if NVDA grows X% by year-end, your tax bill is Y" tempts the user to anchor on the projection. Anchoring on a projection a user types into a form is worse than no projection — it manufactures false confidence. If the user wants a forecast, they can do it on paper.

### Why the simulator does not warn about "you are about to sell at a loss"

It just shows the realised gain (which can be negative). There is no editorialisation. Some pre-trade tools say "⚠ This sale will lock in a loss"; we do not, because:

- A loss-locking sell is sometimes exactly what the user wants (loss-harvesting).
- The user can read the gain number themselves and decide.
- Editorial nudges accumulate. Each nudge is small; the sum is paternalistic. METHODOLOGY.md preserves the "user is in control" stance.

### Why this ticket needs `compute_marginal_tax_for_realised_gains` as a new helper, even though TICKET-011 has `compute_per_position_harvest_impact`

The two are similar but not identical. The harvest function takes `LivePosition`s (it owns the synthesis of "sell-it-all-today" gains internally). The simulator already has its own gains list (from FIFO simulation) and just needs the marginal-tax math. Sharing the synthesis logic would couple them. Better: each function owns its own synthesis, and they share the underlying engine call — which is `compute_tax_year_summary` itself. The new helper is a thin wrapper around that. As noted in the out-of-scope section, the harvest function can later be refactored to use the new helper to share lower-level logic, but that is a separate cleanup.
