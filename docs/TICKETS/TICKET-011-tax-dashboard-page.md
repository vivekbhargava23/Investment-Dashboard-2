# TICKET-011 — Tax Dashboard page (Sparerpauschbetrag tracker, harvest opportunity, tax exposure)

**Status:** IN_PROGRESS
**Priority:** P1
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-04)
**Implemented by:** _pending_
**Depends on:** TICKETs 001 (domain), 002 (FIFO), 003 (repo), 006 (valuation), 007 (UI shell), 008 (Live Overview seeding + render_html), 008c (currency correctness), **010 (tax engine)**.

> **After this ticket merges, the user has a dedicated page that answers: "what is my 2026 tax bill, where is my Sparerpauschbetrag headroom, and which positions could I sell tax-free today?"** The placeholder Sparerpauschbetrag/Tax-Headroom tiles on Live Overview also stop being hardcoded and start reading the real engine output.

---

## Problem

TICKET-010 built the tax engine. It is a pure function that returns a `TaxYearSummary` — but no UI consumes it yet. TICKET-008's Live Overview hardcodes both tax tiles (`€0,00 used of €1.000,00` and `€1.000,00`) with comments saying *"Wired in TICKET-010"*. That comment was written before we realised TICKET-010 should be an engine and TICKET-011 should be the page; this ticket is the page.

Two things to do:

1. **Wire the existing Sparerpauschbetrag and Tax-Headroom tiles on Live Overview** to read from the real engine output instead of constants.
2. **Build a new Tax Dashboard page** at `app/ui/pages/tax.py` that renders the four sections from the JS mockup (`Investment_Dashboard.html`):
   - YTD summary tiles (Sparerpauschbetrag, Realised Gains YTD, Loss Pot, Tax Headroom)
   - Sparerpauschbetrag consumption progress bar
   - Total Tax Exposure (what would the bill be if everything were closed today, after Teilfreistellung and offsets)
   - Harvest Opportunity table (positions with unrealised gains, sorted by gain size, with their per-position "tax if realised" computed using current allowance state)

The harvest table is the high-leverage feature: a one-page answer to "what can I sell today and pay €0 tax?"

---

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-04. Several tighten the pattern set by TICKET-008.

### 1. Tax engine calls go through `app/services/tax_planning.py`, not the page directly.

TICKET-010 deliberately did not create a service. This ticket does: `app/services/tax_planning.py`. Reasons:

- The page needs more than just `compute_tax_year_summary(year, transactions, profile, carryforward)`. It also needs *what-if* scenarios — "what does my tax look like if I additionally sell 5 NVDA today at current price?" That is multiple engine calls combined with live-valuation port calls. Service-layer territory.
- The page is forbidden from importing adapters (architectural rule, enforced by import-linter). The carryforward values have to be persisted somewhere; the service layer wraps that.
- Following the TICKET-006 pattern: services are stateless functions, accept ports as parameters, never import adapters directly, no caches.

This ticket creates the service file with three functions:

```python
def compute_current_tax_summary(
    transactions: Sequence[Transaction],
    profile: TaxProfile,
    carryforward_eur_aktien: Money,
    carryforward_eur_general: Money,
    additional_dividend_income_eur: Money,
    additional_interest_income_eur: Money,
    as_of: datetime,
) -> TaxYearSummary:
    ...

def compute_per_position_harvest_impact(
    live_positions: dict[str, LivePosition],
    current_summary: TaxYearSummary,
    profile: TaxProfile,
) -> dict[str, HarvestImpact]:
    ...

def compute_tax_if_full_liquidation(
    live_positions: dict[str, LivePosition],
    current_summary: TaxYearSummary,
    profile: TaxProfile,
) -> TaxYearSummary:
    ...
```

`compute_per_position_harvest_impact` and `compute_tax_if_full_liquidation` are the two "what if I sold X today" functions. Both internally call `compute_tax_year_summary` with synthetic `RealisedGain`s built from current prices.

### 2. The user's tax profile and carryforward values are persisted as a separate JSON file, `data/tax_profile.json`.

Not in `data/portfolio.json` (which is only transactions). Not as Streamlit secrets (this is data the user edits regularly). Not as session state (which would lose the values on app restart).

A new repository: `TaxProfileRepository` (port) and `JsonTaxProfileRepository` (adapter). One file, three fields:

```json
{
  "version": 1,
  "filing_status": "single",
  "carryforward": {
    "2026": {
      "aktien_eur": "0.00",
      "general_eur": "0.00",
      "additional_dividend_income_eur": "0.00",
      "additional_interest_income_eur": "0.00"
    }
  }
}
```

This is small, hand-editable, and survives app restarts. The Tax Dashboard page renders an "Edit profile" expander that updates the file via the repository — same pattern as Manage Portfolio for transactions.

The carryforward dict is keyed by year so that the user can record their 2025 closing carryforward, their 2026 closing carryforward, and so on, accumulating history without ever overwriting old years.

### 3. The harvest computation respects the current allowance state.

Naive ("each position's gain × 26.375%") would be wrong. If the user has €600 of allowance remaining and a position with €400 of unrealised gain, that gain is fully sheltered — tax = €0, not €105.50.

The correct calculation is per-position incremental: starting from the current `TaxYearSummary`, what marginal tax does *this specific gain* add? That is what `compute_per_position_harvest_impact` does — it runs the engine once with the position's gain added, takes the difference, and that is the position's "tax if realised today" value.

This is also why allowance and loss-pot remaining state must be live (read from the current summary), not hardcoded.

### 4. Stale live data degrades the page gracefully, not silently.

If `LivePosition.is_stale` for a position, the harvest computation cannot include it (we don't know its current gain). The page renders such positions in a separate "Positions with stale data — not included in tax estimates" section so the user knows what is missing. Same per-position-failure-isolation contract as TICKET-006.

If the *entire* live valuation is stale (FX down, all positions stale), the harvest table shows a single banner: "Live valuation is currently unavailable; tax estimates require current prices. Realised gains YTD are still accurate." YTD numbers (which only need transactions, not live data) still display correctly.

### 5. The page does not let the user edit the carryforward without acknowledgement.

Carryforward numbers come from the previous year's `Steuerbescheid`. They are not numbers to be guessed. The "Edit carryforward" form has a confirmation prompt: *"Enter the carryforward amounts from your last Steuerbescheid. If you have never received one for this account, leave at €0."* This is a small UX touch, but it follows the TICKET-008c discipline: never silently default a critical input to zero.

### 6. The page caches expensively but invalidates when transactions change.

Same pattern as Live Overview (TICKET-008): `@st.cache_data` keyed on a transactions signature; cache cleared on any transaction CRUD. The Tax Dashboard adds a second cache key element — the tax profile's last-modified timestamp — so editing the carryforward also invalidates the cache.

### 7. Realised gains YTD are reported in *gross* terms (the card the mockup shows) AND in *post-Teilfreistellung* terms (the mathematically correct number).

The mockup tile says "Realised Gains YTD: €X" with subtitle "€Y losses · net €Z". That number on the card is *gross* (pre-Teilfreistellung). The actual taxable amount is post-Teilfreistellung, post-loss-offset, post-allowance. The page surfaces both numbers in two adjacent tiles so the user is not confused. Header on the gross tile says "Realised Gains YTD (gross)"; header on the second one says "Taxable after offsets and allowance".

This is a careful UX call, called out here so a future "let me clean up the duplicate-looking tiles" refactor does not silently merge them.

---

## Acceptance criteria

### `app/ports/tax_profile_repo.py` — new port

- [ ] `TaxProfileRepository(Protocol)` with two methods:
  - `load() -> TaxProfileDocument` — returns the persisted profile + carryforwards. If the file does not exist, returns a sensible default (`SINGLE` filing status, empty carryforward dict). Never raises on "missing file" — it just returns the default.
  - `save(doc: TaxProfileDocument) -> None` — atomic write (same temp-file-then-os.replace pattern as TICKET-003).
- [ ] `TaxProfileDocument` — frozen Pydantic model:
  - `version: int` (defaulting to 1)
  - `filing_status: FilingStatus`
  - `per_year: dict[int, YearlyTaxInputs]`
- [ ] `YearlyTaxInputs` — frozen Pydantic model:
  - `carryforward_aktien_eur: Money`
  - `carryforward_general_eur: Money`
  - `additional_dividend_income_eur: Money`
  - `additional_interest_income_eur: Money`
- [ ] All four `Money` fields validated as EUR.

### `app/adapters/repo_json/tax_profile_repo.py` — new adapter

- [ ] `JsonTaxProfileRepository(TaxProfileRepository)`. Constructor takes `Path`. Behaviour:
  - `load()`: if the path does not exist, return `TaxProfileDocument(version=1, filing_status=SINGLE, per_year={})`. If it exists, read and `model_validate_json`. If the file exists but `version != 1`, raise `LegacyTaxProfileError` with instructions.
  - `save()`: write to `<path>.tmp`, fsync, `os.replace` to `<path>`. Same atomic-write pattern as TICKET-003's transaction repo.
- [ ] Tests in `tests/integration/test_tax_profile_repo.py`:
  - Round-trip: save a doc, load it back, assert equal.
  - Missing file: `load()` on a non-existent path returns the default doc.
  - Atomic write: simulate a write failure halfway through and verify the original file is intact.
  - Wrong version: load a legacy fixture with `version=0`, assert `LegacyTaxProfileError`.

### `app/services/tax_planning.py` — new service

The service has three pure functions, all stateless, all dependency-injected. None of them call `datetime.now()` — `as_of` is passed in.

#### `compute_current_tax_summary`

- [ ] Steps:
  1. Pull the year from `as_of.year`.
  2. Validate the year is supported by the engine (`year in RATES_BY_YEAR`).
  3. Call `compute_tax_year_summary(year, transactions, profile, carryforward_aktien, carryforward_general, dividends, interest)`.
  4. Return the `TaxYearSummary`.
- [ ] Errors propagate unchanged (this is a thin wrapper).

#### `compute_per_position_harvest_impact`

- [ ] Returns a dict keyed by ticker. Each value is a `HarvestImpact` (defined in `app/domain/tax/models.py` as part of this ticket — see below).
- [ ] For each non-stale `LivePosition`:
  1. Synthesise a hypothetical "sell-it-all-today" `RealisedGain`. Cost basis = `position.cost_basis_eur`. Proceeds EUR = `live_value_eur`. Holding period and dates are not needed for tax (no German short-term-vs-long-term distinction since 2009).
  2. Run the engine with this synthetic gain *added* to the existing realised gains. Get a new `TaxYearSummary`.
  3. Compute `incremental_tax_eur = new_summary.total_tax_owed_eur - current_summary.total_tax_owed_eur`. Compute `headroom_remaining_after_eur = new_summary.sparerpauschbetrag_remaining_eur` (and the loss-pot equivalents).
  4. Build the `HarvestImpact` and store.
- [ ] **Stale positions are NOT in the dict.** They appear in a separate `stale_positions: list[str]` companion field of the return value (so wrap into a small NamedTuple or a Pydantic model — `HarvestImpactReport` — that has both `impacts: dict[str, HarvestImpact]` and `stale_positions: list[str]`).

#### `compute_tax_if_full_liquidation`

- [ ] One engine call: synthesise a `RealisedGain` per non-stale `LivePosition` (cost basis from book, proceeds from live). Add to the year's existing realised gains. Run the engine. Return the `TaxYearSummary`.
- [ ] If any positions are stale, the result's `total_taxable_after_loss_offset_eur` understates the real exposure; the page is responsible for displaying the staleness warning, not the service.

### `app/domain/tax/models.py` — extend

- [ ] Add `HarvestImpact` to `models.py`:
  - `ticker: str`
  - `instrument_kind: InstrumentKind`
  - `unrealised_gain_eur: Money` (positive or negative; the gross gain if sold today, before any tax processing)
  - `taxable_gain_after_teilfreistellung_eur: Money` (this position's gain after Teilfreistellung but before offsets)
  - `incremental_tax_eur: Money` (the marginal tax this gain adds to the year's bill)
  - `incremental_soli_eur: Money` (the marginal Soli)
  - `total_incremental_eur: Money` (tax + soli; what the user pays)
  - `is_fully_sheltered: bool` (`incremental_tax_eur == 0`)
- [ ] Add `HarvestImpactReport`:
  - `impacts: dict[str, HarvestImpact]`
  - `stale_tickers: tuple[str, ...]`

### `app/ui/wiring.py` — add lazy singleton

- [ ] `get_tax_profile_repo() -> TaxProfileRepository` — same pattern as the existing transaction repo singleton. Path comes from `Settings.tax_profile_json_path`, defaulting to `data/tax_profile.json`.

### `app/config.py` — add a setting

- [ ] `tax_profile_json_path: str = "data/tax_profile.json"` on the `Settings` class.
- [ ] `.env.example` gets the new `# TAX_PROFILE_JSON_PATH=data/tax_profile.json` line (commented out — defaults are fine).

### `app/ui/pages/tax.py` — new page

The page renders four sections, top-down. All formatting (€, %, signed) goes through `app/ui/format.py`. All HTML emission uses `render_html` (TICKET-008b).

#### Top of file: imports + cache key

- [ ] `import streamlit as st`, plus services and components.
- [ ] `_transactions_signature(transactions)` — same helper as overview.py uses; if not factored, factor it into `app/ui/cache_keys.py` in this ticket and reuse from overview.
- [ ] `_tax_profile_signature(repo)` — read the file's mtime as part of the cache key so editing the profile invalidates.
- [ ] `@st.cache_data` wrapping the service calls, keyed on the two signatures + the year.

#### Section 1 — YTD summary tiles (4-column grid)

- [ ] **Sparerpauschbetrag tile**:
  - Value: `format_eur(summary.sparerpauschbetrag_total_eur)`
  - Subtitle: `f"{format_eur(summary.sparerpauschbetrag_consumed_eur)} used · {format_eur(summary.sparerpauschbetrag_remaining_eur)} remaining"`
  - No sign coloring (this is a budget line).
- [ ] **Realised Gains YTD (gross) tile**:
  - Value: gross sum (sum of `gain.realised_gain_eur` from all 2026 RealisedGains where `gain > 0`)
  - Subtitle: `f"{format_eur(realised_losses_gross)} losses · net {format_eur(net_gross)}"`
  - `gain_class()` color on the net.
- [ ] **Loss Pot Carried-In tile**:
  - Value: `format_eur(summary.aktien_pot.prior_year_carryforward_eur + summary.general_pot.prior_year_carryforward_eur)` — combined for tile clarity, broken out in a hover.
  - Subtitle: `"from prior years · offsets future gains"`. If both pots are zero, subtitle: `"none yet — set in profile if applicable"`.
- [ ] **Tax Headroom tile** (the most useful number on the page):
  - Value: `format_eur(summary.sparerpauschbetrag_remaining_eur + summary.aktien_pot.prior_year_carryforward_eur + summary.aktien_pot.current_year_losses_unconsumed_eur + summary.general_pot.prior_year_carryforward_eur + summary.general_pot.current_year_losses_unconsumed_eur)` — the total amount of additional gain the user could realise today before owing any tax.
  - Subtitle: small breakdown like "€X allowance + €Y aktien pot + €Z general pot".
  - Green coloring.
  - **The math is fragile** — there is a test case below dedicated to it.

#### Section 2 — Sparerpauschbetrag progress bar (full width)

- [ ] Above the bar: `"Sparerpauschbetrag consumed"` left, `f"{pct:.0f}% · {consumed_eur} / {total_eur}"` right (DM Mono font).
- [ ] Bar height 8px, green fill at the consumed-percentage width.
- [ ] CSS class `.tax-progress-wrap` — add to `dark.css`.

#### Section 3 — Total Tax Exposure (4-column grid)

This section answers "what tax would I owe if I closed every position today?"

- [ ] **Net Unrealised Gain tile**: sum of `live_position.unrealised_gain_eur` across non-stale positions. Subtitle: gain-percent.
- [ ] **Sheltered (Allowance + Loss Pot) tile**: amount of the unrealised that would be absorbed by allowance + carryforward + current-year losses if liquidated. Computed by running the engine with the synthetic full-liquidation gains and looking at consumed-allowance + consumed-carryforward.
- [ ] **Taxable Gain tile**: the post-shelter taxable amount. If zero: subtitle says "fully sheltered ✓" with green coloring.
- [ ] **Tax Owed (if closed today) tile**: full `total_tax_owed_eur` from `compute_tax_if_full_liquidation`. If zero: subtitle "€0 — tax-free" with green; else "26.375% Abgeltungsteuer + Soli" with red.
- [ ] If any positions are stale: prominent yellow banner above the section: `"⚠ {N} position(s) have stale prices and are excluded from tax exposure estimates: {ticker_list}. Refresh from Live Overview when prices return."`

#### Section 4 — Harvest Opportunity table

The high-leverage section: which positions should the user sell today to use up unused allowance?

- [ ] Section header: `"Harvest Opportunity"` with subtitle `"Positions with unrealised gains — largest first. 'Tax if Realised' assumes this is the only trade from today, computed sequentially from largest gain."`
- [ ] Right-aligned tile: `"Tax-free headroom"` with the same value as the headroom KPI tile above (so the user sees it next to the table).
- [ ] Columns: Ticker, Name, Gain (€), Gain %, Tax if Realised, Headroom Left, Kind.
- [ ] Sorted by `unrealised_gain_eur` descending. **Only positive-gain positions appear in this table.** A separate `Loss Harvesting` section below handles negative-gain ones.
- [ ] Per-row computation: walks the sorted list, accumulating consumed-allowance. Each row's "Tax if Realised" assumes the rows above have *already been sold* and consumed their share of the allowance. This is the realistic-sequence number a user would see if they actually executed top-down.
- [ ] Stale positions: do NOT appear in this table. Listed in a small footer line: `"Excluded due to stale prices: {tickers}"`.

#### Section 5 — Loss Harvesting (small table)

- [ ] Renders only if there are positions with negative `unrealised_gain_eur`.
- [ ] Columns: Ticker, Loss (€), Loss %, Pot it would feed (Aktien-Pot vs General-Pot), Available to offset future gains.
- [ ] Sorted by absolute loss descending.

#### Section 6 — "Edit Tax Profile" expander

- [ ] Collapsed by default. When expanded, shows:
  - Filing status radio (Single / Joint).
  - For the current year (and the previous one): four `st.number_input` fields — aktien carryforward, general carryforward, dividend income, interest income. Help tooltips for each pointing the user to where on the Steuerbescheid the number lives.
  - Help tooltip for the carryforward fields specifically calls out: *"This is the closing carryforward from your last Steuerbescheid. If you do not have one, leave at €0 — do not guess."*
  - Save button. On save: validate, write via `tax_profile_repo.save()`, clear `st.cache_data`, rerun.
- [ ] After saving: green confirmation `"Tax profile updated."` for one rerun (use the same `form_feedback` session_state pattern as Manage Portfolio).

### `app/ui/pages/overview.py` — update Sparerpauschbetrag and Tax Headroom tiles

- [ ] Replace the two hardcoded tiles with calls to `compute_current_tax_summary`. Pull values from `summary.sparerpauschbetrag_consumed_eur`, `summary.sparerpauschbetrag_total_eur`, and the headroom math used on the Tax Dashboard.
- [ ] Remove the `# Wired in TICKET-010` comments.
- [ ] **No new logic on Live Overview** — the headroom math lives in one place, on the Tax Dashboard's helper function. Live Overview imports and calls it.

### Tests

#### `tests/unit/services/test_tax_planning.py`

- [ ] **`compute_current_tax_summary` is a pure passthrough**: same input, same output as the engine. Mock the engine and assert one call with the same arguments. (Sanity check that the service does not accidentally inject extra logic.)
- [ ] **`compute_per_position_harvest_impact` against a single-position fixture**: 1 position with €500 unrealised gain (AKTIE), current summary has €1,000 allowance unused. Expected: `incremental_tax_eur = €0`, `is_fully_sheltered = True`.
- [ ] **`compute_per_position_harvest_impact` partial-shelter case**: 1 position with €1,500 unrealised gain (AKTIE), allowance €1,000 unused. Expected: incremental tax = (€500 × 0.25) + soli = €125 + €6.875 = €131.875.
- [ ] **`compute_per_position_harvest_impact` ETF Teilfreistellung case**: 1 AKTIENFONDS position with €1,000 unrealised gain, allowance €0 left. Expected: taxable post-Teilfreistellung = €700, incremental tax = €175 + €9.625.
- [ ] **`compute_per_position_harvest_impact` stale position is excluded**: 2 positions, one stale. The dict has 1 key; `stale_tickers` has the other.
- [ ] **`compute_tax_if_full_liquidation`**: portfolio of 3 positions, all live. Verify the result equals running the engine with all 3 synthetic gains added.
- [ ] **All-stale portfolio**: full liquidation summary equals the current summary (no synthetic gains added).

#### `tests/unit/ui/test_tax_page_helpers.py`

- [ ] `_compute_headroom(summary)` — the headroom math (allowance remaining + sum of carryforwards + sum of unconsumed current-year losses). Test against a fixture with each component non-zero. Verify total equals the sum.
- [ ] `_compute_sequential_harvest_impacts(harvest_impacts, current_summary, profile)` — the per-row sequential math for the harvest table. Three positions of €600, €500, €400 unrealised gain (AKTIE), allowance €1,000. Row 1 sells at €600 → still €400 of allowance for row 2 → row 2 €500 sells with €400 sheltered, €100 taxable → tax €25 + soli. Row 3: zero allowance, full tax. Verify all three numbers.

#### `tests/integration/test_tax_dashboard_e2e.py`

- [ ] Build a portfolio fixture with 3 transactions (1 ETN buy, 1 ETN sell from 2026, 1 NVDA buy). Run the page's data-loading function (extract from `tax.py` so it is testable). Assert the four-tile summary and the harvest table contents are what we expect.
- [ ] Run with the engine deliberately erroring (synthesise an unclassified-ticker transaction). Verify the page surfaces a clear error rather than crashing the whole app.

### Lints / quality

- [ ] `pytest` — all tests pass.
- [ ] `ruff check .` — passes.
- [ ] `mypy app/` — passes.
- [ ] `lint-imports` — passes; specifically: `app.ui.pages.tax` imports from `app.services`, `app.domain`, `app.ui.*`. NOT from `app.adapters` (only via wiring.py). NOT from `streamlit` directly bypassing the `render_html` helper.
- [ ] Manual: `streamlit run app/ui/main.py`, navigate to Tax Dashboard. Screenshot of all four sections + harvest table in PR description.

### State updates (per CLAUDE.md session-end ritual)

- [ ] `docs/SESSION_LOG.md` appended.
- [ ] `docs/PROJECT_STATE.md` updated.
- [ ] `docs/TICKETS/BACKLOG.md` updated.
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.

---

## Files created

```
app/ports/tax_profile_repo.py
app/adapters/repo_json/tax_profile_repo.py
app/services/tax_planning.py
app/ui/pages/tax.py
app/ui/cache_keys.py                              ← if not already factored from overview.py
tests/unit/services/test_tax_planning.py
tests/unit/ui/test_tax_page_helpers.py
tests/integration/test_tax_profile_repo.py
tests/integration/test_tax_dashboard_e2e.py
data/tax_profile.json                              ← gitignored; created on first save (TICKET-008c established the gitignore pattern)
tests/fixtures/tax_profile_legacy_v0.json          ← legacy version for the rejection test
```

## Files modified

```
app/config.py                                      ← add tax_profile_json_path setting
app/domain/tax/models.py                           ← add HarvestImpact and HarvestImpactReport
app/domain/tax/__init__.py                         ← re-export the two new types
app/ui/wiring.py                                   ← add get_tax_profile_repo() lazy singleton
app/ui/pages/overview.py                           ← Sparerpauschbetrag and Tax Headroom tiles wired
app/ui/styles/dark.css                             ← .tax-progress-wrap, .harvest-table classes
.env.example                                       ← TAX_PROFILE_JSON_PATH placeholder
.gitignore                                         ← data/tax_profile.json
docs/TICKETS/BACKLOG.md                            ← TICKET-011 row → IN_REVIEW
README.md                                          ← brief mention of tax_profile.json
```

## Files NOT to modify

- `app/domain/tax/engine.py`, `pipeline.py`, `rates.py`, `classification.py` — that is TICKET-010's surface. If a tax-engine bug shows up, it gets its own ticket.
- `app/domain/fifo.py`, `app/domain/realised_gain.py` — engine consumes these unchanged.
- `app/services/valuation.py` — service is fine; this ticket adds a sibling.
- `app/ui/components/*` — reuse existing badges, metric_cards. Adding new components requires explicit ticket scope expansion.

---

## Out of scope

- **Tax engine changes**. This ticket is the page; engine is TICKET-010. Any bug found in the engine while implementing this gets a follow-up ticket.
- **Vorabpauschale display**. The engine does not compute it (out of scope of TICKET-010). The page renders a small "⚠ Vorabpauschale not included for accumulating ETFs (TICKET-010b)" footnote in the Total Tax Exposure section. Just text — no math.
- **Pre-trade sell simulator** as a UI panel. This is TICKET-012, a separate page or panel. The harvest table is a *static estimate*; the simulator is *interactive what-if*.
- **Tax-loss harvesting recommendations / auto-suggestions**. ("You should sell X to lock in a €N loss.") The Loss Harvesting table just shows positions; it does not recommend.
- **Multi-year tax history view** (a chart of past years' tax bills). Future ticket.
- **Tax report export** (CSV or PDF for the tax advisor). Future ticket.
- **Quellensteueranrechnung** (foreign withholding tax credit). Out of scope of the engine; therefore out of scope of the page.
- **Profile editing for past years already filed**. The form lets the user edit current-year and prior-year carryforward inputs but the profile editor is intentionally minimal — not a full multi-year profile manager. Future ticket if it becomes painful.
- **Per-lot tax detail.** Surface-level tax view only. Lot ledger is its own page (TICKET-013ish).

---

## Test cases (selected, illustrative)

1. **The headroom math is right when only allowance is left**:
   - Profile: SINGLE. No carryforward. No realised gains YTD. `summary.sparerpauschbetrag_remaining_eur = €1,000`.
   - Page tile: "Tax Headroom: €1,000.00".
   - Subtitle: "€1,000 allowance + €0 aktien pot + €0 general pot".

2. **The headroom math is right with mixed components**:
   - Profile: SINGLE. Aktien carryforward €300. General carryforward €200. €600 of allowance already consumed (so €400 remaining). Aktien current-year unconsumed losses: €0 (all losses absorbed gains already this year).
   - Tile value: €400 + €300 + €200 = €900.
   - **There is a temptation to add allowance + total carryforward + current-year gross losses; the engine has already done the netting**, so the field on `LossPotState` to use is `prior_year_carryforward_eur` plus *unused* current-year-losses. This is the test that catches double-counting.

3. **The harvest sequential math is right**:
   - 3 positions: P1 unrealised gain €600 (AKTIE), P2 €500 (AKTIE), P3 €400 (AKTIE). Allowance €1,000 fully unused.
   - Row 1 "Tax if Realised": €0 (covered by allowance).
   - Row 2 "Tax if Realised": €25 + Soli €1.375 = €26.375 (€100 spills past allowance).
   - Row 3 "Tax if Realised": €100 + Soli €5.50 = €105.50 (full €400 taxable).
   - Headroom Left after row 1: €400. After row 2: €0. After row 3: €0.

4. **Edit profile flow persists**:
   - Open the expander, change carryforward_aktien from €0 to €1,500, save.
   - File `data/tax_profile.json` exists with the new value.
   - Page reruns and the Tax Headroom tile updates by €1,500.

5. **Stale positions surface in the banner**:
   - Mock a 2-position portfolio with one stale. The exposure section banner shows "1 position has stale prices: NVDA". Harvest table excludes NVDA. Footer line of harvest table reads "Excluded due to stale prices: NVDA."

6. **Live Overview's Sparerpauschbetrag tile is no longer hardcoded**:
   - Add a 2026 sell that produces €400 of taxable gain. Refresh Live Overview. Sparerpauschbetrag tile shows "€400.00 used of €1,000.00", not "€0.00 used of €1.000,00."

---

## Notes (architectural and methodological — for future AI sessions)

### Why the headroom calculation is "fragile"

It is the sum of four components:
1. Allowance remaining (`summary.sparerpauschbetrag_remaining_eur`)
2. Aktien-pot prior-year carryforward (`summary.aktien_pot.prior_year_carryforward_eur`)
3. Aktien-pot current-year unconsumed losses (the *net* amount, after this year's losses already absorbed this year's gains; what is left over)
4. Same as 3 but for the general pot.

The temptation is to add `summary.aktien_pot.current_year_losses_eur` (the gross losses) directly. That double-counts: those losses may have already absorbed gains. The engine's `LossPotState` exposes both fields, and the ticket spec is explicit that the *unconsumed* portion is the right one. The test in `test_tax_page_helpers.py` is dedicated to this distinction.

If TICKET-010's `LossPotState` does not yet expose `current_year_losses_unconsumed_eur` (it is computable from existing fields: `current_year_losses - consumed_against_gains`), this ticket adds the derived field to `LossPotState` so the page does not have to recompute it. That is the only `app/domain/tax/` change that belongs in TICKET-011 — and it is purely additive, not a rule change.

### Why the harvest table is "sequential, not parallel"

If the table showed each position's "tax if realised in isolation", every row's number would assume the full allowance is available. A user reading the table would think "I can sell all three rows tax-free!" and only realise after submitting the trades that allowance is shared across the year. Sequential ("if you sell row 1, then row 2's available allowance is whatever row 1 left over") is the realistic execution number. Showing the parallel-headroom number would be a silent miscount of the kind METHODOLOGY.md bans.

The trade-off is that the order in which the user actually executes might be different from largest-gain-first. We accept this — largest-gain-first is the most-common heuristic, and the user can mentally reorder the rows if their plan differs. Future ticket can add a "drag to reorder" affordance if it becomes painful.

### Why a separate file for the tax profile and not in `portfolio.json`

`portfolio.json` is the book of record — transactions only. Mixing tax profile (a *user setting*) into it would mean every UI that wants to read transactions has to also load and parse profile data. Cleaner: a second tiny JSON file with its own schema, version, and validator. Same pattern other Streamlit apps use for "user prefs vs user data."

The carryforward dict is keyed by year so the user can record their 2025 closing carryforward, their 2026 closing carryforward, and so on. When the user runs the dashboard for the 2027 tax year (some time in 2027 or 2028), they will refer back to the 2026 entry, type the closing number into the 2027 entry, and proceed.

### Why we wire Live Overview's tiles in this ticket and not deferred

The two hardcoded tiles on Overview have been a "TICKET-010 wires this" comment for longer than the engine has existed. Leaving them hardcoded after the page exists would be confusing — the user would see real numbers on the Tax Dashboard and stale placeholders on Live Overview, with no clue why. Wiring them is one function call; it belongs in this ticket.

### Why the page is heavier on UI text than other pages

Tax UX is unforgiving. Wrong-direction errors ("you have €X of headroom" when you actually have €Y) lead to bad financial decisions. The tooltips on the Edit Profile expander, the explicit "if you do not have a Steuerbescheid, leave at €0" instruction, the gross-vs-taxable split on the Realised Gains tile — these are not bloat, they are the discipline the engine's correctness needs at the UX boundary. METHODOLOGY.md says the engine should not silently default critical inputs; the page repeats that contract at the place where users actually enter data.

### Why there is no automated tax-loss-harvesting recommendation

The engine has the data to say "you should sell HY9H.F today to lock in a €40 loss for the general pot." Three reasons we do not:

1. The dashboard is a decision-support tool, not a portfolio manager. A recommendation crosses the line.
2. Lost-pot value depends on next year's expected gains (which the engine does not predict), so the "should you harvest" question requires a forecast we do not make.
3. The Loss Harvesting table already surfaces the data. The user can read it and decide.

Future ticket could add a "year-end loss-harvest assistant" that surfaces ranked suggestions in late December, but that is a deliberate, separate scope.
