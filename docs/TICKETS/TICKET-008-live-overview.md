# TICKET-008 — Live Overview page wiring + portfolio seed bootstrap

**Status:** READY
**Priority:** P1
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-03)
**Implemented by:** _pending_
**Depends on:** TICKETs 001 (domain), 002 (FIFO), 003 (repo), 004-005 (yfinance), 006 (valuation service), 007 (UI shell)

> **This is the first ticket that produces a working prototype.** After this ticket lands, `streamlit run app/ui/main.py` shows real portfolio data with live prices, the Refresh button works end-to-end, and the user can see their holdings in the dark-themed dashboard. Manage Portfolio (TICKET-009) is the next step for editing data through the UI; until then, edits happen via the seed script or hand-editing JSON.

---

## Problem

We have:
- A working backend (TICKETs 001–006): persist transactions, compute positions, fetch live prices/FX, assemble live valuation.
- A visual shell (TICKET-007): dark theme, sidebar, topbar, page routing — all placeholders.

What's missing: **the connection between them**. This ticket wires the Live Overview placeholder to call the valuation service with real transactions, render the KPI tiles + positions table from the result, and hook the Refresh button to actually clear caches.

It also solves the **bootstrap problem**: we have no way to create transactions yet (Manage Portfolio UI is TICKET-009). This ticket ships a one-off CLI seed script that reads a CSV (`docs/reference/seed_portfolio.csv` — Vivek's actual portfolio) and writes `data/portfolio.json` in the new schema. Run once after install, you have a populated portfolio.

---

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-03:

1. **Seed CSV lives at `docs/reference/seed_portfolio.csv` and is committed to git.** It is reference data, not secret. Future tickets can re-seed for testing. The seed CSV is the canonical "what does Vivek's portfolio look like" reference for any AI session that needs realistic test data.

2. **`data/portfolio.json` remains gitignored.** It is the user's live working data. The seed script writes it; the user (or TICKET-009 in the future) edits it.

3. **Streamlit caching wraps the service calls, not the service itself.** The service (TICKET-006) is stateless by contract. Streamlit's `@st.cache_data` lives in `app/ui/pages/overview.py` (and any other page that calls services). This is the **upper cache layer** of the two-cache architecture; the adapter cache (TICKET-004-005) is the lower layer.

4. **The cache key is derived from a "transactions signature."** Streamlit can't hash arbitrary objects. We pass a short string signature: `f"{len(transactions)}:{max(tx.id for tx in transactions, default='empty')}"`. Adding/removing a transaction changes the count; editing changes by replacing the tx (so the max id may not change, but TICKET-009 will explicitly call `st.cache_data.clear()` after edits — handled there, not here).

5. **Refresh button clears both cache layers and reruns.** Topbar's Refresh handler (built in TICKET-007 as a placeholder `st.rerun()`) is upgraded here to: `service.clear_caches(price_provider, fx_provider); st.cache_data.clear(); st.rerun()`.

6. **Adapters are constructed once at module level in a wiring module.** New file: `app/ui/wiring.py`. Module-level singletons: `_repository`, `_price_provider`, `_fx_provider`. Pages import these via `from app.ui.wiring import get_repository, get_price_provider, get_fx_provider`. This is the dependency-injection seam: tests use the real services with fake providers; production uses real ones. Streamlit's process model (single-process for a session) makes module-level singletons safe.

7. **Positions table sorts by weight descending.** Largest position first, matching the mockup.

8. **Stale positions render gracefully.** If `live_price_native is None` (yfinance failed for that ticker), price/value/gain columns show "—" and the row gets a small grey indicator. Cost basis still shows correctly. Summary tiles indicate partial staleness.

9. **Tax tiles use placeholder values for now.** Sparerpauschbetrag and Tax Headroom tiles render with hardcoded numbers (Sparerpauschbetrag = €1000 total / €0 used, Tax Headroom = €1000 + realised_losses estimate). Comment in code: "Real values from tax engine in TICKET-010." This keeps visual fidelity to the mockup without scope-creeping the tax engine into this ticket.

10. **Charts (portfolio performance, allocation pies) are NOT in this ticket.** The mockup has them on Live Overview. Per scope discipline: this ticket is KPIs + table only. Charts are TICKET-014 (Performance page) and a future TICKET-008b if we want allocation visuals on the Overview specifically.

---

## Acceptance criteria

### `docs/reference/seed_portfolio.csv` — committed seed data

- [ ] CSV file with header row: `ticker,type,trade_date,shares,price_native,currency,fx_rate_eur,notes`
- [ ] Realistic transaction list seeded from Vivek's actual portfolio (2025-2026 trades). Use the data below verbatim:

```csv
ticker,type,trade_date,shares,price_native,currency,fx_rate_eur,notes
VUSA.DE,buy,2024-08-01,32.0000,97.5000,EUR,1.0,Core S&P 500 ETF entry
ETN,buy,2025-01-15,5.0000,320.0000,USD,0.9300,Eaton — power infra entry
ASX,buy,2025-02-28,100.0000,9.5000,USD,0.9150,ASE Tech — packaging
MU,buy,2025-03-10,4.0000,85.0000,USD,0.9200,Micron HBM3E entry
ANET,buy,2025-04-05,10.0000,105.0000,USD,0.9250,Arista Networks entry
NVDA,buy,2025-05-12,9.0000,115.0000,USD,0.9100,NVIDIA — AI compute
HY9H.F,buy,2025-05-22,1.0000,178.5000,EUR,1.0,SK Hynix GDR — first lot
HY9H.F,buy,2025-05-23,1.0000,179.2000,EUR,1.0,SK Hynix GDR — second lot
MRVL,buy,2025-06-15,10.0000,58.0000,USD,0.8950,Marvell — custom silicon
APD,buy,2025-07-22,4.0000,250.0000,USD,0.9050,Air Products — under review
AVGO,buy,2025-08-20,4.0000,195.0000,USD,0.8950,Broadcom — XPU
5631.T,buy,2025-11-10,1.0000,4200.0000,USD,0.9300,Japan Steel Works (use USD as approximation; KRW/JPY not supported in v1)
RHM.DE,buy,2026-03-27,1.0000,1452.7500,EUR,1.0,Rheinmetall — long-standing target
HY9H.F,buy,2026-03-31,10.0000,121.4000,EUR,1.0,SK Hynix — fifth lot
ETN,sell,2026-03-12,1.0000,340.0000,USD,0.9180,Trim — partial sell
ETN,sell,2026-05-01,1.0000,355.0000,USD,0.9200,Trim — second partial
HY9H.F,buy,2026-05-02,1.0000,135.0000,EUR,1.0,SK Hynix — recent add
HY9H.F,sell,2026-01-02,1.0000,165.0000,EUR,1.0,Tax-loss harvest from first lot
```

> **Note on `5631.T` (Japan Steel Works):** Currency enum supports only EUR and USD. Treating this position as USD is a known approximation for v1. A future ticket extending the Currency enum will fix it. Documented inline in the CSV `notes` column.

> **Note on price realism:** prices are best-effort approximations. Vivek can edit via TICKET-009's UI once that ships; meanwhile the values are sane enough to demonstrate the app working.

### `app/scripts/__init__.py`
- [ ] Empty init file (the package exists so the script can run as a module).

### `app/scripts/seed_portfolio.py` — one-off seed CLI

- [ ] Reads CSV from `docs/reference/seed_portfolio.csv` by default; accepts `--input` to override.
- [ ] Writes JSON to `data/portfolio.json` by default; accepts `--output` to override.
- [ ] **Refuses to overwrite an existing output file** unless `--force` is passed. Prints a clear message: `"Refusing to overwrite data/portfolio.json. Use --force or pick a different --output."`
- [ ] Uses `csv.DictReader` to parse the CSV.
- [ ] For each row, constructs a `Transaction` (TICKET-001) with `id` auto-generated (UUID4 default factory).
- [ ] Validates each row before construction. On any validation error: prints the row number and error, skips the row, continues. At the end: prints summary `"X transactions imported, Y rows skipped."`
- [ ] Creates the `data/` directory if missing.
- [ ] Uses `JsonTransactionRepository` (TICKET-003) to write — guarantees atomic write and schema-correct output.
- [ ] Run via: `python -m app.scripts.seed_portfolio` (preferred) or `python app/scripts/seed_portfolio.py` (fallback).
- [ ] CLI argparse help: `python -m app.scripts.seed_portfolio --help` shows usage clearly.
- [ ] Prints to stdout only (no logging framework — it's a one-off script).

### `app/ui/wiring.py` — adapter singletons + DI seam

- [ ] Module-level lazy initialization (function-scope, not import-time, so tests can monkeypatch):

```python
from functools import lru_cache
from pathlib import Path
from app.adapters.repo_json import JsonTransactionRepository
from app.adapters.yfinance_feed import YfinanceAdapter
from app.config import get_settings
from app.ports.repository import TransactionRepository
from app.ports.price_feed import PriceProvider
from app.ports.fx_feed import FxProvider

@lru_cache(maxsize=1)
def get_repository() -> TransactionRepository:
    settings = get_settings()
    return JsonTransactionRepository(Path(settings.portfolio_json_path))

@lru_cache(maxsize=1)
def get_price_provider() -> PriceProvider:
    return YfinanceAdapter()

@lru_cache(maxsize=1)
def get_fx_provider() -> FxProvider:
    # Same instance; YfinanceAdapter implements both PriceProvider and FxProvider.
    return get_price_provider()  # type: ignore[return-value]
```

- [ ] **Why `@lru_cache`?** It's the canonical Python idiom for "memoize a function's output." Within a Streamlit process, `get_repository()` returns the same instance every time. This is the ONE place in the codebase where a cache lives at the wiring layer — and it caches *singletons*, not data. It does not violate the "service layer is stateless" rule.
- [ ] No tests for `wiring.py` itself (it's just imports + singletons). The integration is verified by `tests/integration/test_overview_e2e.py` below.

### `app/ui/pages/overview.py` — the wired Live Overview

Replaces the placeholder from TICKET-007 with the real implementation.

#### Imports
- [ ] From the domain: `Transaction`, `LivePosition`, `PortfolioSummary`, `Money`.
- [ ] From the services: `compute_live_positions`, `compute_portfolio_summary`, `clear_caches`.
- [ ] From the wiring: `get_repository`, `get_price_provider`, `get_fx_provider`.
- [ ] From the UI helpers: formatting and components.
- [ ] `import streamlit as st`, `from datetime import datetime`.

#### Cache wrappers (defined inside `overview.py`)

```python
@st.cache_data(ttl=60, show_spinner=False)
def _cached_live_positions(transactions_signature: str) -> dict[str, LivePosition]:
    transactions = get_repository().load_all()
    return compute_live_positions(transactions, get_price_provider(), get_fx_provider())

@st.cache_data(ttl=60, show_spinner=False)
def _cached_summary(transactions_signature: str, as_of_iso: str) -> PortfolioSummary:
    live_positions = _cached_live_positions(transactions_signature)
    return compute_portfolio_summary(live_positions, datetime.fromisoformat(as_of_iso))

def _transactions_signature(transactions: list[Transaction]) -> str:
    if not transactions:
        return "empty"
    sorted_ids = sorted(tx.id for tx in transactions)
    return f"{len(transactions)}:{sorted_ids[-1]}"
```

#### `render()` function

- [ ] Loads transactions from repository.
- [ ] Computes signature.
- [ ] Calls `_cached_live_positions` and `_cached_summary` with the signature.
- [ ] Renders the page in this order:
  1. KPI tile row 1 (2 large tiles): Total Portfolio Value, Total Unrealised Gain.
  2. KPI tile row 2 (4 small tiles): Positions, Thesis Status, Sparerpauschbetrag, Tax Headroom.
  3. Sparerpauschbetrag progress bar (full-width, beneath tile row 2).
  4. Positions table.
  5. Footer: "● LIVE · refreshed Xm ago" or "● PARTIAL · N of M positions stale" depending on `summary.staleness`.

#### KPI tile values

- [ ] **Total Portfolio Value tile**: `format_eur(summary.total_value_eur)`. Subtitle: `"€{cost_basis} cost basis"`.
- [ ] **Total Unrealised Gain tile**: `format_eur(summary.total_unrealised_gain_eur, signed=True)`. Subtitle: `format_pct(summary.total_unrealised_gain_pct, signed=True)` with `gain_class()` for color.
- [ ] **Positions tile**: count = `len(live_positions)`. Subtitle: count of intact thesis positions. Below: a strip of small ticker pills with their thesis-status colour. **Thesis status comes from `live_position.position.ticker` matched against a dict of thesis statuses** — these are placeholder hardcoded values for this ticket (see "Placeholder thesis status data" below). TICKET-016 makes them real.
- [ ] **Thesis Status tile**: 3-segment pill (intact / watch / broken counts). Hardcoded counts based on the placeholder data.
- [ ] **Sparerpauschbetrag tile**: hardcoded `€0,00 used of €1.000,00` for now. Comment: "Wired in TICKET-010".
- [ ] **Tax Headroom tile**: hardcoded `€1.000,00`. Comment: "Wired in TICKET-010".
- [ ] **Sparerpauschbetrag progress bar (full width)**: 0% used. Comment: "Wired in TICKET-010".

#### Placeholder thesis status data

- [ ] At the top of `overview.py`, a clearly-marked placeholder dict:

```python
# PLACEHOLDER — TICKET-016 replaces with real thesis state machine.
_PLACEHOLDER_THESIS_STATUS: dict[str, Literal["intact", "watch", "broken"]] = {
    "NVDA": "intact",
    "RHM.DE": "intact",
    "MU": "intact",
    "HY9H.F": "intact",
    "MRVL": "intact",
    "APD": "watch",
    "ANET": "intact",
    "AVGO": "intact",
    "ETN": "intact",
    "ASX": "intact",
    "VUSA.DE": "intact",
    "5631.T": "intact",
}
_PLACEHOLDER_HORIZON: dict[str, Literal["H1", "H2", "H3"]] = {
    "NVDA": "H1", "ETN": "H1", "ANET": "H1",
    "RHM.DE": "H2", "MU": "H2", "HY9H.F": "H2", "MRVL": "H2", "APD": "H2", "AVGO": "H2", "ASX": "H2",
    "VUSA.DE": "H3", "5631.T": "H3",
}
```

- [ ] If a ticker is not in the dict, default to `"intact"` and `"H2"` and emit no warning. (TICKET-016 won't have this gap.)

#### Positions table

- [ ] Columns (in order): Ticker, Name, CCY, Price, Shares, Cost (€), Value (€), Gain (€), Weight, Horizon, Thesis, Lots.
- [ ] Sorted by weight descending. Weight = `live_value_eur / total_value_eur` (positions with `live_value_eur=None` get weight 0 and sort to the bottom).
- [ ] Stale positions (any of price/value/gain is None): those cells show `—` (em dash). Cost basis still shows correctly. Whole row gets `.stale` CSS class for subtle grey-out (defined in `dark.css` — add this class).
- [ ] **Name** is read from a hardcoded ticker→name dict at the top of the file (placeholder — same as the thesis status dict). TICKET-009 will pull this from the Transaction's metadata if we add a name field, or keep this dict as the canonical reference.
- [ ] Each row's Thesis cell uses `render_thesis_badge()` from `app/ui/components/badges.py`.
- [ ] Each row's Weight cell shows `"X.X%"` plus a tiny inline progress bar (CSS-only, ~30px wide).
- [ ] **Implementation note:** Streamlit's `st.dataframe` does not support custom HTML/CSS in cells. Use `st.markdown(unsafe_allow_html=True)` to render the entire table as one HTML `<table>` with custom classes. This is the same approach the React mockup uses.
- [ ] The HTML table includes a `<tbody>` with one `<tr>` per position. CSS class `.positions-table` styled in `dark.css`.

#### Refresh button — wired

- [ ] Replace TICKET-007's placeholder `st.rerun()` in `app/ui/components/topbar.py` with a real handler:

```python
def _handle_refresh() -> None:
    from app.ui.wiring import get_price_provider, get_fx_provider
    from app.services.valuation import clear_caches
    clear_caches(get_price_provider(), get_fx_provider())
    st.cache_data.clear()
    st.rerun()
```

- [ ] The button calls `_handle_refresh` on click. The function lives in `topbar.py` (next to the button) so it's local to the rendering logic.
- [ ] The topbar's hardcoded `"USD/EUR 1.0786 · 14:14"` is replaced with live values. Implementation:
  - Try `get_fx_provider().get_current_rate(EUR, USD)` for the rate.
  - On `FxRateUnavailableError`, render `"FX —"` instead.
  - Time is `datetime.now().strftime("%H:%M")`.
  - The full string: `f"USD/EUR {rate:.4f} · {time}"`.

### Tests

#### `tests/integration/test_seed_script.py`

- [ ] **End-to-end seed**: copy the committed `docs/reference/seed_portfolio.csv` into a temp dir, run `seed_portfolio.main(input_path, output_path)`, verify the output JSON loads via `JsonTransactionRepository.load_all()` and contains the expected number of transactions (count rows in CSV, subtract any malformed).
- [ ] **Refuses to overwrite**: write a non-empty file at the output path, run the seed, expect `SystemExit` (or whatever non-zero return). Output file unchanged.
- [ ] **`--force` overwrites**: same setup, with `--force` flag, expect success.
- [ ] **Skips malformed rows gracefully**: feed a CSV with one bad row (e.g., `shares=NOT_A_NUMBER`). Other rows still imported. Stdout shows the skip count.

#### `tests/unit/ui/test_overview_helpers.py`

- [ ] **`_transactions_signature` is deterministic**: same list → same signature. Different lists → different signatures.
- [ ] **`_transactions_signature` for empty list**: returns `"empty"`.
- [ ] **`_transactions_signature` is order-insensitive on input**: shuffling the input list produces the same signature (because the function sorts internally).

#### `tests/unit/ui/test_overview_render.py`

- [ ] Streamlit rendering can't be unit-tested headlessly without significant fixture work, so we limit ourselves to data-pipeline tests:
  - **Weight calculation correct**: build a mock summary + 3 positions with known live_value_eurs, assert weights sum to 1.0 within 0.0001 tolerance.
  - **Stale rows sort to bottom**: positions with `live_value_eur=None` appear last in the sorted order.
  - **Placeholder thesis status defaults**: a ticker not in the placeholder dict → `"intact"`.

#### `tests/integration/test_overview_e2e.py`

- [ ] **Smoke test the wiring end-to-end with fakes:**
  1. Load the seed CSV.
  2. Run the seed script logic (or the equivalent setup) into a temp file.
  3. Construct a `JsonTransactionRepository` pointing at the temp file.
  4. Construct `FakePriceProvider` and `FakeFxProvider` with hardcoded values.
  5. Call `compute_live_positions(repo.load_all(), fake_price, fake_fx)`.
  6. Assert: dict has expected number of tickers, all have non-None `live_value_eur` (since fakes don't fail), summary's `staleness="live"`.
- [ ] This test is the closest thing to "does the prototype actually work?" available in pytest. It does not run Streamlit itself.

#### Manual review checklist (in PR description)

- [ ] All 4 small + 2 large KPI tiles render without errors
- [ ] Total Portfolio Value matches sum of position values manually verified
- [ ] Refresh button: click it, see prices change (or fail gracefully if yfinance is offline)
- [ ] Positions table: sorted by weight descending, all 12 (or however many seeded) tickers visible
- [ ] Stale handling: temporarily disconnect network, click Refresh, verify "—" appears in price columns and the row dims
- [ ] Topbar: shows real FX rate and current time

### Lints / quality
- [ ] `pytest` — all tests pass (existing + new); integration tests still skipped by default unless `--run-integration`
- [ ] `ruff check .` — passes
- [ ] `mypy app/` — passes; UI standard mode
- [ ] `lint-imports` — passes; `app.ui.pages.overview` imports from `app.services.*`, `app.domain.*`, `app.ui.*`. NOT from `app.adapters.*` (only via wiring.py).

### State updates (per CLAUDE.md session-end ritual)
- [ ] `docs/SESSION_LOG.md` appended
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-008 → IN_REVIEW)
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-008 row → IN_REVIEW)
- [ ] Ticket file `Status: IN_REVIEW`
- [ ] PR opened via `gh pr create --fill --base main`

---

## Files created

```
docs/reference/seed_portfolio.csv
app/scripts/__init__.py
app/scripts/seed_portfolio.py
app/ui/wiring.py
tests/integration/test_seed_script.py
tests/unit/ui/test_overview_helpers.py
tests/unit/ui/test_overview_render.py
tests/integration/test_overview_e2e.py
```

## Files modified

```
app/ui/pages/overview.py        ← replaces TICKET-007 placeholder with real implementation
app/ui/components/topbar.py     ← Refresh button gets real handler; FX rate/time wired
app/ui/styles/dark.css          ← add .stale row class, .positions-table styles
docs/TICKETS/BACKLOG.md         ← TICKET-008 → IN_REVIEW
README.md                       ← add a "First-time portfolio setup" section pointing to the seed script
```

---

## Out of scope

- **Manage Portfolio UI** — TICKET-009. Until then, edits via seed script or hand-editing JSON.
- **Tax engine** — TICKET-010. Sparerpauschbetrag and Tax Headroom tiles are hardcoded.
- **Charts** (portfolio performance line chart, allocation pies) — out of this ticket's scope. Performance chart is TICKET-014. If allocation pies are wanted on the Overview specifically, future TICKET-008b.
- **Real thesis state machine** — TICKET-016. Placeholder dict for now.
- **Currency support beyond EUR/USD** — Japan Steel Works treated as USD approximation. Future ticket extends the Currency enum.
- **CSV import from real broker exports** (Scalable, IBKR, etc.) — the seed script reads our own CSV format. A future ticket can add broker-specific importers.
- **Sub-tabs on the Overview page** (the React mockup has none, but some other pages do) — irrelevant here, single page.
- **Per-ticker drill-down (clicking a position to expand)** — out of scope. Lot Ledger (TICKET-015) covers this.

---

## Notes (architectural and methodological — for future AI sessions)

### Why this is the "first prototype" milestone

Foundation tickets (000–006) are invisible to the user — backend code, no UI. TICKET-007 is the visual shell with no data. **TICKET-008 is the first time the user opens the app and sees their actual portfolio.** It's the milestone we've been building toward.

After this ticket merges:
- `streamlit run app/ui/main.py` shows a real, dark-themed dashboard
- KPI tiles show live numbers
- Positions table shows live prices and gains
- Refresh button refetches everything
- Network failures degrade gracefully (per-ticker stale rendering)

This is the moment the project becomes useful even if no further ticket is built. Everything after is depth (tax, charts, decision gates) — the core "I can see my portfolio" works.

### How the two-cache architecture cooperates here

```
USER ACTION (click Refresh OR change page)
         │
         ▼
overview.py: render() called
         │
         ▼
_cached_live_positions(signature)         ← @st.cache_data layer (TTL 60s)
         │ cache hit? return immediately. Cache miss: continue.
         ▼
service.compute_live_positions(...)       ← Stateless. Calls ports.
         │
         ▼
adapter.get_current_price("NVDA")         ← Adapter cache (TTL 60s)
         │ cache hit? return. Cache miss: hit yfinance.
         ▼
yfinance API
```

When the user clicks **Refresh**:
1. `clear_caches(...)` flushes adapter caches.
2. `st.cache_data.clear()` flushes Streamlit caches.
3. `st.rerun()` forces a rerender.
4. The rerender calls `_cached_live_positions` which now misses both caches and pulls fresh from yfinance.

Both caches are empty exactly when the user wants fresh data. They are full exactly when the user is exploring (clicking pages, hovering rows). This is what produces the "snap to click" feel.

### Why the cache key is a "signature" string and not transactions themselves

Streamlit's `@st.cache_data` requires hashable arguments. `list[Transaction]` is not hashable (Pydantic models are sometimes hashable if frozen, lists never are). Solutions:
1. Pass a tuple of frozen Transactions — works but slow to hash for 100+ transactions.
2. Pass a signature string — cheap to hash, invalidates when count or max-id changes.

We use option 2. The signature changes whenever:
- A transaction is added (count changes, last id changes).
- A transaction is deleted (count changes).
- A transaction is edited *with id preserved* — count and max-id may not change → signature collision. **TICKET-009 handles this** by explicitly calling `st.cache_data.clear()` after every edit, so we never depend on the signature alone for edit invalidation.

### Why Streamlit's `st.dataframe` is not used

`st.dataframe` is convenient but doesn't support custom HTML in cells. We need:
- Color-coded thesis pills
- Inline weight progress bars
- Per-row stale styling
- Custom column alignment

These need raw HTML. `st.markdown(unsafe_allow_html=True)` with a hand-built `<table>` gives full control. The downside is no built-in sorting/filtering, but the table is small (≤20 rows) and we control sort order in code.

### Why the seed script lives in `app/scripts/`

`app/scripts/` is for one-off operational tools that ship with the package but aren't part of the running app. The seed script is the first; future scripts may include broker import, data migration, etc.

It is **not** a service or an adapter. It composes the existing pieces (`Transaction` from domain, `JsonTransactionRepository` from adapters) to do a one-time setup task. It can import from any layer because it's the wiring point — the same as `app/ui/main.py` is the wiring point for the running app.

### Why module-level singletons in `wiring.py`

Three things must be true:
1. The repository must be the same instance across all pages (otherwise saved transactions don't show up).
2. The price/fx provider's cache must persist across page navigations (otherwise every page change refetches from yfinance — defeating the cache).
3. Tests must be able to substitute fakes.

`@lru_cache(maxsize=1)` on a getter function gives us all three: same instance per process, can be replaced via `monkeypatch.setattr` in tests, no global mutation bugs.

### Methodology note (for future AI sessions)

This ticket establishes the pattern for every later UI page that calls services:
1. Page imports services + wiring (not adapters directly)
2. Page wraps service calls in `@st.cache_data` with a stable signature
3. Page renders the result via shared format helpers and components
4. Refresh button clears the right cache layers

TICKETs 011 (Tax Dashboard), 014 (Performance), 015 (Lot Ledger), 017 (Decision Gates), 018 (Behavioural Ledger) all follow this pattern. None of them need to re-derive how caching works — they reference this ticket.

The placeholder pattern (`_PLACEHOLDER_THESIS_STATUS`) is also a precedent: when a downstream ticket needs data that another ticket will provide, hardcode reasonable defaults with a clear comment pointing to the future ticket. Don't block on dependencies that aren't strictly necessary.
