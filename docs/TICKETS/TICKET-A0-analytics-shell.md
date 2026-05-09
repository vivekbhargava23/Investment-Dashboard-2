# TICKET-A0 — Analytics page shell + analytics stats library

**Status:** IN_REVIEW
**Priority:** P1
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-08)
**Implemented by:** _pending_
**Depends on:** TICKETs 001 (domain — `Decimal`, `Currency`), 007 (Streamlit shell + sidebar registry), 008b (`render_html` helper if used for tab placeholders)

> **After this ticket merges, the Analytics page exists in the sidebar with five empty sub-tabs, and `app/domain/analytics.py` is the single home for every statistical primitive A1–A5 will consume.** Nothing user-visible changes beyond the new (empty) page. The work is foundational: the stats library is the contract that A1–A5 are written against, and the page shell is the container they will fill in.

---

## Problem

The next phase of the dashboard is an Analytics page covering five distinct lenses on the portfolio: **Performance**, **Correlation**, **Technicals**, **Position Sizer**, and **Concentration**. The planning chat (2026-05-08) settled on a 5-sub-tab container rather than five sidebar entries (see `docs/ANALYTICS_DRAFT_HANDOFF.md`).

Tackling the five sub-tabs as a single ticket would produce one unreviewable PR. Tackling them serially without a shared foundation means each ticket re-implements the same stats — `daily_returns`, `volatility`, `sharpe`, `correlation_matrix`, `sma`, `rsi` — drifting in convention and edge-case handling.

This ticket carves out the shared substrate so A1–A5 can be drafted, implemented, and reviewed independently:

1. **The page shell.** A new `Analytics` page in the sidebar, with five `st.tabs()` whose bodies are placeholders (`st.info("Coming in TICKET-AX")`). This locks the navigation, the page title, the icon, and the tab order — so A1–A5 can each fill exactly one tab body without touching shell concerns.

2. **The stats library.** `app/domain/analytics.py`: pure, I/O-free functions with `Decimal` arithmetic, exhaustively unit-tested. Every A1–A5 calculation routes through this module. No sub-tab ticket is allowed to add a new statistical primitive elsewhere; if a future tab needs one, it's added here in a follow-up.

A0 is the cheapest ticket of the six and the prerequisite for every other one. It delivers nothing user-visible beyond the empty page existing — which is the point.

---

## Architectural decisions implemented by this ticket

These were decided in the planning chat 2026-05-08 (see `docs/ANALYTICS_DRAFT_HANDOFF.md` "What's already locked").

### 1. Single sidebar entry, five `st.tabs()` inside

The Analytics page is **one** sidebar entry, not five. Five sidebar entries would clutter navigation and imply each is a peer of Live Overview / Manage Portfolio / Tax Dashboard. They aren't — they're five lenses on the same portfolio.

Tab keys (stable, used in `st.session_state` and tests): `performance`, `correlation`, `technicals`, `sizing`, `concentration`. Default landing tab: `performance` (the one most users will reach for first).

### 2. Sidebar position

Sidebar order after this ticket: **Live Overview → Manage Portfolio → Tax Dashboard → Analytics → Research → Settings**.

Analytics sits between Tax Dashboard and Research. Reasoning: Tax Dashboard and Analytics are both portfolio-wide deep-dive pages on what is owned; Research is for evaluating tickers (owned or not). Grouping the "owned-portfolio" pages together is the cleaner mental model.

Icon: `📊` (per the handoff doc — distinct from `📈` for Research and the existing icons).

### 3. Tab placeholders are `st.info`, not blank

Each tab body contains exactly:

```python
st.info("Coming in TICKET-AX")
```

— where `AX` is the corresponding ticket ID (`A1` for Performance, etc.). This makes it visible on the deployed dashboard which sub-tabs are not yet implemented and gives reviewers a one-glance way to spot a regression where a tab body got accidentally cleared.

### 4. The stats library lives in `app/domain/analytics.py`

`app/domain/` rules apply in full: **zero I/O**, **`Decimal` only** for monetary and rate values, **frozen models** if any models are introduced. No `import requests`, no `import yfinance`, no `import streamlit`. The `import-linter` configuration must enforce this.

The file exports the following pure functions (signatures binding for A1–A5):

```python
def daily_returns(closes: list[Decimal]) -> list[Decimal]: ...
def volatility_annualised(returns: list[Decimal]) -> Decimal: ...           # σ × √252
def drawdown_series(navs: list[Decimal]) -> list[Decimal]: ...              # peak-to-trough %
def max_drawdown(navs: list[Decimal]) -> Decimal: ...                       # min(drawdown_series)
def sharpe(returns: list[Decimal], risk_free: Decimal = Decimal(0)) -> Decimal: ...
def sma(closes: list[Decimal], period: int) -> list[Decimal | None]: ...    # None until enough history
def rsi(closes: list[Decimal], period: int = 14) -> list[Decimal]: ...      # Wilder smoothing
def correlation_matrix(
    returns_by_ticker: dict[str, list[Decimal]],
) -> dict[str, dict[str, Decimal]]: ...
```

Each function has a docstring stating: what it computes, what units the inputs are in, what units the output is in, what it does on edge inputs (empty / single value / mismatched lengths).

### 5. Edge-case behaviour is explicit, not "whatever falls out"

Every function specifies its edge-case behaviour up front. A1–A5 read the docstring, not the implementation:

| Function | Empty input | Single value | Other edge |
|---|---|---|---|
| `daily_returns` | `[]` | `[]` (need 2 closes) | n closes → n-1 returns |
| `volatility_annualised` | raise `ValueError` | raise `ValueError` (need ≥2 returns for variance) | — |
| `drawdown_series` | `[]` | `[Decimal(0)]` (zero drawdown) | always ≤ 0 |
| `max_drawdown` | raise `ValueError` | `Decimal(0)` | always ≤ 0 |
| `sharpe` | raise `ValueError` | raise `ValueError` | zero variance → raise `ValueError` (avoid div-by-zero) |
| `sma` | `[]` | `[None]` if period > 1 | first `period - 1` entries are `None` |
| `rsi` | `[]` | `[]` (need ≥ period+1 closes) | first `period` entries match Wilder seed |
| `correlation_matrix` | `{}` | single ticker → `{T: {T: Decimal(1)}}` | mismatched lengths → raise `ValueError` |

`ValueError` (not silent NaN, not a placeholder return value) is the chosen failure mode. The library's job is to compute correctly; the service layer's job is to present an empty state when the library raises.

### 6. `Decimal` precision is set once

Set `getcontext().prec = 28` at the top of `app/domain/analytics.py` (or use `Decimal.from_float` consistently — pick one and document why). All intermediate calculations use `Decimal`. The `√252` annualisation uses `Decimal(252).sqrt()` (Python's `decimal` supports it natively). **No `float` allowed in the module body.**

If a calculation requires `numpy` (e.g. for matrix correlations to be tractable), convert to `float` *only inside the function body*, do the math, then convert back to `Decimal` at the boundary. The function's signature stays `Decimal`-in / `Decimal`-out. Document this internal `float` conversion in the docstring so future readers know it's deliberate.

### 7. The page shell does not import the stats library

`app/ui/pages/analytics.py` only renders empty tabs. It does **not** import `app/domain/analytics.py` in this ticket — there's nothing to call yet. This keeps the import graph clean: A1–A5 each add their own service-layer module that depends on the stats library, and the page imports those services. The stats library is never imported directly by UI code.

### 8. No service-layer module yet

This ticket does **not** create `app/services/analytics.py`, `app/services/analytics_performance.py`, etc. Those are the responsibility of A1–A5. A0's scope ends at:

- `app/ui/pages/analytics.py` (the shell)
- `app/domain/analytics.py` (the stats library)
- `app/ui/main.py` (sidebar registration)
- Tests for both new modules

### 9. The placeholder constant `MAX_POSITION_WEIGHT` is **not** introduced here

Even though A4 and A5 will both reference a `MAX_POSITION_WEIGHT = Decimal(35)` constant, A0 does not pre-emptively create a shared constants module. **Whoever drafts/implements A4 first introduces the constant in `app/services/analytics_sizer.py`; A5 then imports from there or relocates it** — the relocation decision is made when there are two real consumers, not before. Avoiding speculative shared modules is the rule.

---

## Acceptance criteria

### `app/domain/analytics.py` — new module

- [ ] Module docstring states: "Pure statistical primitives for the Analytics page. Zero I/O, `Decimal` arithmetic, deterministic. A1–A5 consume these functions." Plus a one-line summary per function.

- [ ] All eight functions exported with the exact signatures listed in decision §4. Type hints are exact (no `Any`, no `list` without parameter).

- [ ] **`daily_returns(closes)`**: returns `[(closes[i] - closes[i-1]) / closes[i-1] for i in 1..n-1]`. Empty / single → `[]`. Returns are *fractions*, not percentages (i.e. 0.05, not 5).

- [ ] **`volatility_annualised(returns)`**: sample standard deviation (n-1 denominator) × `Decimal(252).sqrt()`. Raises `ValueError("at least 2 returns required")` on `len(returns) < 2`.

- [ ] **`drawdown_series(navs)`**: for each `nav[i]`, computes `(nav[i] - peak[i]) / peak[i]` where `peak[i]` is the running max up to and including `i`. Returns *fractions* (negative or zero). Empty → `[]`.

- [ ] **`max_drawdown(navs)`**: equivalent to `min(drawdown_series(navs))`. Empty → raises `ValueError`. Single → `Decimal(0)`.

- [ ] **`sharpe(returns, risk_free=0)`**: `(mean(returns) - risk_free) / stdev(returns)` × `Decimal(252).sqrt()` (annualised). `risk_free` is interpreted as a *daily* risk-free rate (caller's responsibility to convert from annual). Raises `ValueError` if `len(returns) < 2` or stdev is zero.

- [ ] **`sma(closes, period)`**: simple moving average. `result[i]` is `None` for `i < period - 1`, else `mean(closes[i - period + 1 : i + 1])`. `period < 1` raises `ValueError`.

- [ ] **`rsi(closes, period=14)`**: Wilder's smoothing (not simple average). First `period` values are `None` or omitted (state explicitly which in the docstring; tests assert the choice). For `len(closes) < period + 1`, returns `[]`. RSI values are in `[0, 100]`; tests assert this invariant.

- [ ] **`correlation_matrix(returns_by_ticker)`**: returns a nested dict where `result[A][B]` is Pearson correlation of the two return series. Diagonal is exactly `Decimal(1)`. Off-diagonal is symmetric (`result[A][B] == result[B][A]`). All input series must have equal length, otherwise raises `ValueError("series length mismatch: A has X, B has Y")`.

- [ ] Domain layer rules: no `import requests`, no `import streamlit`, no `import yfinance`, no file I/O, no `print`, no `logging` calls. Only `decimal`, `math` (if needed for natural log etc.), and optionally `numpy` if the implementer chooses (with the `float`-internal pattern from decision §6).

### `tests/unit/domain/test_analytics.py` — new test module

- [ ] One test class per function (`TestDailyReturns`, `TestVolatilityAnnualised`, `TestDrawdownSeries`, `TestMaxDrawdown`, `TestSharpe`, `TestSma`, `TestRsi`, `TestCorrelationMatrix`).

- [ ] **Each function has a "happy path" test** with hand-computed expected values (not regression-frozen — actual hand-computed). E.g. for `daily_returns([100, 110, 99])`, expected is `[Decimal("0.10"), Decimal("-0.10")]` exactly.

- [ ] **Each function has explicit edge-case tests** matching the table in decision §5. Empty input, single value, error-raising cases (use `pytest.raises(ValueError)` with message-contains assertion).

- [ ] **`drawdown_series` invariant test**: for a randomly-generated NAV series (use `hypothesis` if available, else a fixed long series), assert every value in the result is `≤ Decimal(0)`. This is the "drawdown panel never shows DD > 0" sanity check from A1.

- [ ] **`rsi` range invariant test**: for a randomly-generated long close series, assert every RSI value is in `[Decimal(0), Decimal(100)]`.

- [ ] **`correlation_matrix` symmetry test**: for any 2+ tickers, assert `result[A][B] == result[B][A]` for every pair, and `result[T][T] == Decimal(1)` for every `T`.

- [ ] **`correlation_matrix` mismatched-length test**: pass `{"A": [Decimal(1), Decimal(2)], "B": [Decimal(3)]}` and assert `ValueError` with a message naming the lengths.

- [ ] **`sharpe` zero-variance test**: pass `[Decimal("0.01"), Decimal("0.01"), Decimal("0.01")]` and assert `ValueError` (not infinity, not NaN).

- [ ] **`sma` `period > len(closes)` test**: assert all returned values are `None`.

- [ ] Test module runs in `< 1s` (domain layer rule). No I/O, no network.

### `app/ui/pages/analytics.py` — new page module

- [ ] Single `render(...)` function, signature matching the existing pages (e.g. `overview.py`, `research.py`). Reads service dependencies from `app.ui.wiring` if any are needed; A0 needs none.

- [ ] Page header: `st.markdown("# 📊 Analytics")` followed by a one-line caption: `"Five lenses on your portfolio: performance, correlation, technicals, position sizing, concentration."`.

- [ ] Five tabs created via:
  ```python
  perf_tab, corr_tab, tech_tab, sizing_tab, conc_tab = st.tabs([
      "Performance", "Correlation", "Technicals", "Position Sizer", "Concentration",
  ])
  ```

- [ ] Each tab body contains exactly:
  ```python
  with perf_tab:
      st.info("Coming in TICKET-A1")
  # ... etc, with TICKET-A2, A3, A4, A5 respectively
  ```

- [ ] No other content on the page in this ticket. No KPI strips. No data fetches. No `st.session_state` writes (the default-tab behaviour is whatever Streamlit defaults to — first tab).

- [ ] No imports from `app.domain.analytics` (the stats library is not consumed yet).

### `app/ui/main.py` — sidebar registration

- [ ] Add `"analytics"` to the page registry with sidebar label `"📊 Analytics"`. Route to `app.ui.pages.analytics.render`.

- [ ] Sidebar order: **Live Overview → Manage Portfolio → Tax Dashboard → Analytics → Research → Settings**. Verify this order in the rendered sidebar.

- [ ] No regressions to existing page entries: every existing route still resolves to the same target function.

### `tests/unit/ui/test_analytics_page.py` — new shell test module

These are smoke / call-shape tests, not full Streamlit rendering. Use `pytest-mock` to patch `streamlit`.

- [ ] **Page renders without errors when called with no positions**: mock `streamlit` calls; call `render()`; assert no exception raised.

- [ ] **Five tabs created with the expected labels**: assert `st.tabs` was called once with the list `["Performance", "Correlation", "Technicals", "Position Sizer", "Concentration"]`.

- [ ] **Each tab body calls `st.info` with the corresponding TICKET-AX message**: five separate assertions, one per sub-tab. This is the regression guard — if a future PR removes one of the placeholders without filling it in, this test fails.

- [ ] **Page header uses the `📊` icon**: assert the markdown call contains `"# 📊 Analytics"` exactly.

### Lints / quality

- [ ] `pytest` — all new tests pass; existing tests still pass.
- [ ] `ruff check .` — passes.
- [ ] `mypy app/` — passes (strict on `app/domain/analytics.py`).
- [ ] `lint-imports` — passes:
  - `app/domain/analytics.py` imports only from `decimal`, `math`, and optionally `numpy`. **No imports from `app.adapters`, `app.services`, `app.ui`, or any I/O package.**
  - `app/ui/pages/analytics.py` imports only `streamlit` and (eventually) `app.ui.wiring`. **Not from `app.adapters` or `app.domain`.**

### State updates (per `AGENTS.md` Phase 8b)

- [ ] `docs/SESSION_LOG.md` appended with a new entry.
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-A0 → IN_REVIEW under "In review 👀").
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-A0 row → IN_REVIEW; new "Phase 6 — Analytics" section if not present).
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.

---

## Files created

```
app/domain/analytics.py
app/ui/pages/analytics.py
tests/unit/domain/test_analytics.py
tests/unit/ui/test_analytics_page.py
```

## Files modified

```
app/ui/main.py                          ← register Analytics page in sidebar + router
docs/PROJECT_STATE.md                   ← TICKET-A0 → IN_REVIEW
docs/SESSION_LOG.md                     ← new session entry
docs/TICKETS/BACKLOG.md                 ← new "Phase 6 — Analytics" section + TICKET-A0 row → IN_REVIEW
```

## Files NOT to modify

- `app/ui/pages/overview.py` — out of scope; this ticket adds a new page, doesn't change existing ones.
- `app/ui/pages/research.py` — out of scope.
- `app/ui/pages/manage.py` — out of scope.
- `app/ui/pages/tax.py` — out of scope.
- `app/services/*` — no service module is created in this ticket.
- `app/domain/fifo.py`, `app/domain/tax.py`, etc. — existing domain modules are untouched.
- `pyproject.toml` / `requirements.txt` — no new dependencies. (If the implementer determines `numpy` is needed and isn't already a transitive dep, **stop and report** rather than adding it; that's an architectural decision.)

---

## Out of scope

- **Any sub-tab body content.** Performance, Correlation, Technicals, Position Sizer, Concentration are A1–A5. This ticket renders empty placeholders only.
- **`app/services/analytics.py`** or any analytics service module. Created by A1–A5 as each is implemented.
- **`MAX_POSITION_WEIGHT` constant** or any other shared constants module. Introduced by A4 (first consumer).
- **Persistence** of any kind: no JSON file for analytics state, no `st.session_state` keys for analytics defaults. A1–A5 handle their own state.
- **Plotly chart helpers** for heatmap, weight bars, RSI panel. Those live in `app/ui/components/charts.py` and are added by the relevant sub-tab tickets (A2, A3, A5).
- **Performance budgets.** No render-time SLA. The empty page is fast by definition.
- **Mobile-specific layout.**
- **Renaming `MAX_POSITION_WEIGHT` references** in any future code — A0 doesn't introduce that constant.
- **Adding `numpy` to the dependency list.** If the implementer's chosen approach to `correlation_matrix` requires numpy and it isn't already installed, stop and report.
- **Pre-fetching or caching** anything from the page shell. Nothing to fetch yet.

---

## Test cases (manual review checklist for the PR)

- [ ] Open the dashboard. Sidebar shows the new "📊 Analytics" entry between "🧾 Tax Dashboard" and "📈 Research".
- [ ] Click Analytics. Page header reads "📊 Analytics" with the one-line caption below.
- [ ] Five tabs visible: Performance / Correlation / Technicals / Position Sizer / Concentration. Performance is the active tab on first visit.
- [ ] Click each tab in turn. Each shows an `st.info` banner reading "Coming in TICKET-A1" (or A2 / A3 / A4 / A5 respectively). No layout artefacts, no extra whitespace, no errors in the Streamlit console.
- [ ] Switch to Live Overview, then back to Analytics. Tab state may or may not persist (Streamlit default — not specified by this ticket); either is acceptable for A0.
- [ ] No regressions on Live Overview, Manage Portfolio, Tax Dashboard, Research. Each still renders identically to before this ticket.
- [ ] Refresh the page. Analytics still renders correctly.

---

## Notes (architectural and methodological — for future AI sessions)

### Why the stats library is locked in A0, not deferred to A1

A1 alone needs four of the eight functions (`daily_returns`, `volatility_annualised`, `drawdown_series`, `max_drawdown`, `sharpe`). If we let A1 introduce them, then A2 needs `correlation_matrix` and `daily_returns` — and A2's drafter has to either re-import from A1's service module (wrong layer) or re-implement (drift). Locking the full library in A0 means every sub-tab ticket starts from a known foundation.

The cost is that A0 is the longest-feeling ticket (lots of small functions, lots of edge cases) for the smallest user-visible change (an empty page). That's the right trade. Foundation tickets always look disproportionate.

### Why `Decimal` everywhere, even for unit-less ratios

Sharpe, RSI, correlation, and drawdown are all unit-less or %-valued. Using `float` for them and `Decimal` only for monetary values would be defensible. We use `Decimal` throughout because:

1. The rest of the domain layer is `Decimal`. Mixing `float` and `Decimal` at module boundaries is the source of subtle bugs (1 / 3 ≠ Decimal(1) / Decimal(3) in last digits).
2. A1's KPI strip will display these values to the user. The display layer can format `Decimal` deterministically; `float` introduces "0.30000000000000004" surprises.
3. The performance cost is irrelevant at portfolio scales (≤ 50 positions, ≤ 252 trading days × 5 years = 1,260 closes per ticker).

The escape valve is decision §6: convert to `float` *inside* the function if the math demands it, but the signature stays `Decimal`.

### Why edge cases raise rather than return placeholder values

A `daily_returns([])` returning `[]` is fine — empty in, empty out is a natural identity. But a `volatility_annualised([])` returning `Decimal(0)` would be lying: zero variance is a real signal (a flat-line portfolio). Returning `Decimal("NaN")` would force every caller to NaN-check. Raising `ValueError` puts the burden on the service layer, which has the context to render an empty state ("not enough history yet") with the right user-facing message. The library doesn't know what the right message is; the service does.

### Why no service module yet

A0 is the foundation. A service module would force one of two bad outcomes:
1. An empty `app/services/analytics.py` with no functions yet — invites future drift about what belongs there.
2. A service module with placeholder functions that A1–A5 then have to refactor — extra churn for no gain.

Each sub-tab ticket creates its own focused service module (`analytics_performance.py`, `analytics_correlation.py`, etc.). If a sixth utility function emerges that's shared across tabs, that's the trigger to introduce a shared `app/services/analytics.py`. Not before.

### Why placeholders use `st.info`, not `st.empty()`

`st.empty()` would render a blank tab — visually indistinguishable from a tab whose body got accidentally removed in a future refactor. `st.info("Coming in TICKET-AX")` is a deliberate, visible placeholder that tells the reviewer (a) this is intentional, (b) which ticket fills it. It also makes the regression test in `test_analytics_page.py` meaningful: the test asserts the exact string per tab.

### How this ticket sets up A1–A5

After A0 merges, the drafter for any of A1–A5:

1. Reads the relevant section in `docs/ANALYTICS_DRAFT_HANDOFF.md`.
2. Knows exactly which `analytics.py` functions to call (signatures locked).
3. Knows the page shell exists and which tab body to fill.
4. Creates a focused `app/services/analytics_<tab>.py` for orchestration.
5. Replaces the `st.info(...)` placeholder with the real tab body.

Each sub-tab ticket is then ~150–250 lines of code + tests. A0 is the heavier piece; the rest are mechanical fills against the contract.

### Why TICKET-013 is *not* a dependency of A0 (despite being in the handoff doc's table)

The handoff doc lists A0 as depending on TICKET-013 (NAV cache) and TICKET-022a (chart components). Those are *transitive* dependencies — needed by A1 (NAV) and A2/A3 (charts). **A0 itself depends on neither.** A0 ships as soon as the empty page renders and the stats library passes its tests. This unblocks parallel drafting of A1–A5 even before TICKET-013 is implemented.
