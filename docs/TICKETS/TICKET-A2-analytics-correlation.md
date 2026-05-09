# TICKET-A2 — Analytics: Correlation tab v1

**Status:** IN_REVIEW
**Priority:** P1
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-09)
**Implemented by:** GPT Codex (GPT-5, session 2026-05-09)
**Depends on:** TICKET-A0 (analytics page shell + `app/domain/analytics.py`), TICKET-022a (`OhlcDataProvider` port + adapter), TICKET-006 (live positions for the universe)

> **After this ticket merges, the Correlation sub-tab on the Analytics page renders a pairwise-correlation heatmap, an avg-correlation table with diversification badges, and an auto-warning when ≥3 positions form a high-correlation cluster.** The tab is the second user-visible analytics surface (after A1's Performance) and the first consumer of `analytics.correlation_matrix` from A0.

---

## Problem

Concentration risk is partly a count problem (how many positions) and partly a correlation problem (how independently they move). Two positions with weight 15% each contribute very different risk depending on whether their daily returns correlate at 0.2 or at 0.9. The current dashboard surfaces position weights (Live Overview, A5 Concentration) but offers no view of how correlated those positions are with each other.

This ticket adds the Correlation sub-tab, replacing the `st.info("Coming in TICKET-A2")` placeholder from A0. The tab answers three questions in one view:

1. **Pairwise:** Which specific pairs move together? (heatmap)
2. **Per-position:** Which positions are the strongest diversifiers vs the weakest? (avg-correlation table)
3. **Cluster:** Are there hidden groupings of three or more positions that all move together? (auto-warning)

The user's portfolio is currently 13 positions; the design must work for 5 and for 30+ without code changes.

---

## Architectural decisions implemented by this ticket

### 1. Correlation universe is "live positions only"

The matrix covers every position currently held with `qty > 0`, fetched via `compute_live_positions(...)`. Closed lots (sold out completely) are excluded — correlation is a forward-looking risk lens; what was held last year doesn't drive today's portfolio variance.

The universe is recomputed on every render. No persistence, no caching at the universe level. (Per-ticker OHLC fetches are cached via the existing `OhlcDataProvider` adapter cache.)

### 2. Insufficient-history positions are excluded explicitly, not padded

If a position has fewer trading days of close history than the selected window (e.g. a position bought 20 days ago against a 60D window), it is **excluded from the matrix entirely** and listed in a "Skipped: insufficient history" banner above the matrix.

**Why not pad with zeros / NaN / "available days only":**

- Padding with zeros (or any constant) corrupts every correlation involving that ticker — a flat-line series correlates 0 with everything, which is a fake "diversifier" signal.
- Computing pairwise on each pair's overlapping window (variable window per cell) produces a matrix where cells aren't comparable to each other and the avg-correlation column averages apples and oranges.
- The honest answer is "we don't have enough data on this ticker yet." The banner names the skipped tickers and their available-days count so the user can either pick a shorter window or wait.

The skipped-tickers banner uses `st.warning` and lists each as `TICKER (X days available, window requires Y)`.

### 3. Window selector: 30D / 60D / 90D as `st.radio`, default 30D

Three windows offer enough flexibility without a UI sprawl. 30D matches the typical "recent regime" lens; 90D smooths out individual events. Longer windows (180D, 1Y) are out of scope for v1 — they'd push more positions into the skipped-history bucket and add visual clutter for marginal value.

The selector lives at the top of the tab, full width. Selection persists in `st.session_state["correlation_window"]` so switching tabs and back doesn't reset it.

### 4. Heatmap uses Plotly directly, not a chart component

No existing chart component fits a 2D heatmap. Per the handoff, this ticket uses `plotly.graph_objects.Heatmap` directly via the same module pattern as `app/ui/components/charts.py`. The new helper goes in that file (or a sibling `charts_heatmap.py` if the implementer prefers — both are acceptable; pick one and document).

The helper signature is:

```python
def render_correlation_heatmap(
    matrix: dict[str, dict[str, Decimal]],
    *,
    height: int = 500,
) -> None: ...
```

It calls `st.plotly_chart(..., use_container_width=True)` internally and reads colours from `app/ui/components/_chart_styles.py`. No new style constants are introduced in this ticket; if the existing palette doesn't include a red→neutral→green diverging scale, define `CORRELATION_COLORSCALE` as a module-level constant in `_chart_styles.py` (in scope, since A2 is the first consumer of a diverging colour scale).

Cells display the correlation rounded to 2 decimals. Diagonal cells display `—` (em-dash) instead of `1.00` to make the structure more readable. Hover tooltip shows `Ticker A vs Ticker B: 0.42`.

### 5. Diversification bucket thresholds are constants, not inputs

```python
# In app/services/analytics_correlation.py
DIVERSIFICATION_BUCKETS = (
    (Decimal("0.2"), "high",      "green"),
    (Decimal("0.4"), "moderate",  "amber"),
    (Decimal("0.6"), "low",       "amber"),
    # ≥ 0.6 → "very low" / "red"
)
```

Avg correlation `< 0.2` → "high diversifier" (green). `< 0.4` → "moderate" (amber). `< 0.6` → "low" (amber). `≥ 0.6` → "very low" (red).

These thresholds are not user-configurable in v1. If the user wants to tune them, that's a v2 concern.

The badge styling reuses the existing thesis-status badge component (`app/ui/components/badges.py` if it exists, otherwise a small inline style — implementer's call). No new badge primitive is introduced.

### 6. Cluster detection: union-find over edges where corr > 0.6

The cluster warning fires when **any cluster of size ≥ 3** exists where every pair within the cluster has correlation `> 0.6`.

Algorithm (pure function in `app/domain/analytics.py` — added in this ticket as it's a primitive on the matrix output):

```python
def correlation_clusters(
    matrix: dict[str, dict[str, Decimal]],
    threshold: Decimal,
    min_size: int = 3,
) -> list[list[str]]: ...
```

- Build edges: for every off-diagonal pair `(A, B)` where `matrix[A][B] > threshold`, add an edge.
- Union-find to connected components.
- Return only components with `len >= min_size`, sorted descending by size, then alphabetically by first member.

This is a primitive — it lives in the domain layer, has its own unit tests, and follows the same edge-case rules as the rest of `analytics.py` (empty matrix → `[]`; single ticker → `[]`).

The warning card uses `st.warning` and lists each cluster as: *"3 positions move together (avg corr > 0.6): AAPL, MSFT, GOOGL. They may not be acting as independent diversifiers."* For multiple clusters, one warning card per cluster.

**Note on the algorithm choice:** Connected components is the simplest correct answer and matches what the user is likely to read into the warning ("these all move together"). True clique detection (every pair within the cluster crosses threshold) is stricter and produces fewer false positives, but is exponential in the worst case. Connected-components can produce a "cluster" of {A,B,C} where A↔B = 0.7, B↔C = 0.7, A↔C = 0.3 — technically not a clique. We accept this for v1; the warning text says "may not be acting as independent diversifiers," which is honest about the connected-components definition.

### 7. Layout: window selector → skipped banner (if any) → two-column grid → cluster warnings

```
┌─────────────────────────────────────────────────────────┐
│ Window: ( ) 30D  (•) 60D  ( ) 90D                       │
├─────────────────────────────────────────────────────────┤
│ ⚠ Skipped: TKRA (12 days available, window requires 60) │  ← only if any skipped
├──────────────────────────────────┬──────────────────────┤
│                                  │                      │
│      Pairwise heatmap            │  Avg correlation     │
│      (Plotly)                    │  table               │
│      st.columns([2, 1])          │                      │
│                                  │                      │
├──────────────────────────────────┴──────────────────────┤
│ ⚠ Cluster warning(s) — one card per cluster of size ≥ 3 │  ← only if any
└─────────────────────────────────────────────────────────┘
```

Empty states:

- **Universe < 2 tickers** (after skipping): show `st.info("Need at least 2 positions with sufficient history to compute correlations.")` and render nothing else.
- **All correlations below threshold**: cluster warnings section is empty (not rendered), no placeholder.

### 8. Service-layer module: `app/services/analytics_correlation.py`

```python
def build_correlation_view(
    *,
    repo: TransactionRepository,
    price_feed: PriceFeed,
    fx_feed: FxFeed,
    ohlc: OhlcDataProvider,
    as_of: date,
    window_days: int,
) -> CorrelationView: ...
```

`CorrelationView` is a frozen Pydantic model with:

- `matrix: dict[str, dict[str, Decimal]]` — square matrix over `included_tickers`
- `included_tickers: list[str]` — alphabetical order, defines row/column order in the heatmap
- `skipped: list[SkippedTicker]` — `(ticker, available_days, required_days)`
- `avg_correlation: dict[str, Decimal]` — per included ticker, mean of off-diagonal values in its row
- `clusters: list[list[str]]` — output of `correlation_clusters`

The service:

1. Calls `compute_live_positions(...)` to get the universe (qty > 0).
2. For each ticker, requests `window_days` of close history from `OhlcDataProvider`. (Fetch a buffer — `window_days + 5` calendar days — to ensure `window_days` of trading days.)
3. Partitions into included vs skipped based on returns count `≥ window_days - 1`. (n closes → n-1 returns; we want n-1 ≥ window_days - 1, i.e. n ≥ window_days.)
4. Truncates each included series to the most recent `window_days` closes (alignment is on calendar dates, not array indices — different exchanges have different holidays; the service intersects the trading-date sets across included tickers and uses only dates present for all).
5. Calls `analytics.daily_returns` per ticker, then `analytics.correlation_matrix`.
6. Computes `avg_correlation` per ticker as the mean of its row excluding the diagonal.
7. Calls `analytics.correlation_clusters(matrix, threshold=Decimal("0.6"))`.
8. Returns `CorrelationView`.

The trading-date intersection in step 4 is important: if AAPL has a close for 2026-04-15 (NYSE open) but RHM.DE doesn't (Karfreitag), that date is dropped from both. Otherwise the index alignment is nominal and the returns are nonsense.

### 9. Sortable table uses `st.dataframe`, not a custom component

Columns: Ticker / Name / Avg Correlation / Bucket (badge). Sorted descending by Avg Correlation by default. Streamlit's built-in `st.dataframe(..., use_container_width=True)` provides click-to-sort for free; no custom logic needed. The bucket column renders the badge as styled HTML via the existing `render_html` helper from TICKET-008b.

### 10. No new persistence, no new domain models beyond `correlation_clusters`

The only new thing in `app/domain/` is the `correlation_clusters` function. No new dataclasses. `CorrelationView` lives in the service layer (`analytics_correlation.py`) because it's a UI-shaped DTO, not a domain concept.

---

## Acceptance criteria

### `app/domain/analytics.py` — additions

- [ ] New function `correlation_clusters(matrix, threshold, min_size=3) -> list[list[str]]` with signature exactly as in decision §6.
- [ ] Docstring states: input shape, threshold semantics (`>` not `>=`), min_size semantics, edge cases (empty matrix → `[]`, single ticker → `[]`, no edges crossing threshold → `[]`).
- [ ] Output ordering: clusters sorted descending by size, ties broken alphabetically by first member; tickers within each cluster sorted alphabetically.
- [ ] Domain layer rules: zero I/O, `Decimal` only, no `print`, no `logging`.

### `app/services/analytics_correlation.py` — new module

- [ ] Single public function `build_correlation_view(...)` with signature in decision §8.
- [ ] Frozen Pydantic `CorrelationView` and `SkippedTicker` models with exact fields in decision §8.
- [ ] Module-level constants: `CLUSTER_THRESHOLD = Decimal("0.6")`, `MIN_CLUSTER_SIZE = 3`, `DIVERSIFICATION_BUCKETS` tuple as in decision §5.
- [ ] Bucket-classification helper: `def diversification_bucket(avg_corr: Decimal) -> tuple[str, str]` returning `(label, colour_token)`.
- [ ] Trading-date intersection across included tickers as described in decision §8 step 4. Dates present in fewer than all included tickers are dropped from all series before correlation.
- [ ] Service raises no exceptions for "empty universe" — returns a `CorrelationView` with empty matrix, empty included_tickers, populated skipped if applicable. The page layer renders the empty state.

### `app/ui/components/charts.py` (or sibling file)

- [ ] New helper `render_correlation_heatmap(matrix, *, height=500) -> None` per decision §4.
- [ ] Diagonal renders as `—`, off-diagonal as 2-decimal correlation values.
- [ ] Hover tooltip format: `Ticker A vs Ticker B: 0.42`.
- [ ] Diverging colour scale (red high → neutral mid → green low), with neutral exactly at 0.5 (correlation midpoint, not at 0). Reasoning: a correlation of 0 is "uncorrelated" which is the *desired* state for diversification, not the neutral point. Neutral at 0.5 makes the heatmap visually emphasise the high-correlation regions, which are what the user is looking for.
- [ ] The colour scale is symmetric across the visible range `[-1, 1]`. Negative correlations (rare in a long-only equity portfolio but possible) render as the strongest "green" / desirable end.

### `app/ui/components/_chart_styles.py` — additions

- [ ] `CORRELATION_COLORSCALE` constant — Plotly-compatible colorscale list. Red anchor at 1.0, neutral grey at 0.5, green at -1.0 (or wherever the scale's lower bound sits — pick one and document).

### `app/ui/pages/analytics.py` — modifications

- [ ] Replace the `st.info("Coming in TICKET-A2")` in the Correlation tab body with a call to a new private function `_render_correlation_tab(...)` that takes the wired services as arguments.
- [ ] `_render_correlation_tab` reads `st.session_state["correlation_window"]` (default 30), renders the `st.radio` window selector, calls `build_correlation_view(...)`, then renders skipped banner / heatmap / table / cluster warnings per the layout in decision §7.
- [ ] Other tab placeholders (`st.info("Coming in TICKET-AX")` for A1/A3/A4/A5) remain untouched.
- [ ] Page imports: now imports from `app.services.analytics_correlation`. Still no direct import of `app.domain.analytics`.

### `tests/unit/domain/test_analytics.py` — additions

- [ ] New `TestCorrelationClusters` class.
- [ ] **Happy path**: matrix `{A: {A:1, B:0.7, C:0.8}, B: {A:0.7, B:1, C:0.75}, C: {A:0.8, B:0.75, C:1}}`, threshold 0.6, min_size 3 → `[[A, B, C]]`.
- [ ] **Below threshold**: same matrix with threshold 0.9 → `[]`.
- [ ] **Two disjoint clusters**: 6×6 matrix where {A,B,C} are mutually high and {D,E,F} are mutually high, no cross-edges above threshold → returns both clusters, ordered descending by size (ties → alpha by first member).
- [ ] **min_size = 2**: pair {A,B} above threshold, no triple → with `min_size=2` returns `[[A,B]]`; with `min_size=3` returns `[]`.
- [ ] **Edge: empty matrix** → `[]`.
- [ ] **Edge: single ticker** (`{T: {T: 1}}`) → `[]`.
- [ ] **Threshold semantics**: edge at exactly 0.6 with threshold 0.6 → no edge (uses `>`, not `>=`). Test asserts a cluster that depends on the strict comparison comes back as `[]`.
- [ ] **Connected-components edge case**: matrix where A↔B = 0.7, B↔C = 0.7, A↔C = 0.3, threshold 0.6 → returns `[[A,B,C]]` (per the documented connected-components semantics, not strict-clique).

### `tests/unit/services/test_analytics_correlation.py` — new module

- [ ] **Universe filtering**: given a portfolio with two open positions and one closed position (qty=0), the closed one is not in `included_tickers` and not in `skipped`.
- [ ] **Insufficient-history skipping**: given a 60D window and a position with 30 close days, the ticker appears in `skipped` with `available_days=30, required_days=60`, and is not in `matrix` or `avg_correlation`.
- [ ] **Trading-date intersection**: given two tickers where ticker A has 60 closes including 2026-04-03 and ticker B has 59 closes (missing 2026-04-03), both are included but the matrix is computed on the 59 overlapping dates. Test asserts the correlation value matches a hand-computed value on the intersected series.
- [ ] **Avg correlation excludes diagonal**: for a 3-ticker matrix `{A: {A:1, B:0.5, C:0.5}, ...}`, `avg_correlation[A] == Decimal("0.5")` (mean of B and C, not including A↔A=1).
- [ ] **Empty universe**: no open positions → returns empty `CorrelationView` (no exception).
- [ ] **Single open position**: returns `CorrelationView` with `included_tickers=[T]`, `matrix={T:{T:1}}`, `avg_correlation` either empty or with `T → Decimal(0)` (pick one and document; favour empty since "average correlation to others" with no others is undefined).

### `tests/unit/ui/test_analytics_page.py` — additions

- [ ] **Existing test for A2 placeholder is updated**: instead of asserting `st.info("Coming in TICKET-A2")` is called, asserts the new `_render_correlation_tab` is called when the Correlation tab is active. The other four placeholder assertions (A1/A3/A4/A5) remain.

### Lints / quality

- [ ] `pytest` — all new tests pass; existing tests still pass.
- [ ] `ruff check .` — passes.
- [ ] `mypy app/` — passes.
- [ ] `lint-imports` — passes:
  - `app/domain/analytics.py` continues to have zero I/O imports. `correlation_clusters` is pure.
  - `app/services/analytics_correlation.py` imports only from `app.domain`, `app.ports`, `pydantic`, `decimal`, `datetime`. No `streamlit`, no `requests`, no `yfinance`.
  - `app/ui/pages/analytics.py` imports only `streamlit`, `app.services.analytics_correlation`, `app.ui.components.*`, `app.ui.wiring`. **Not** `app.domain.analytics` directly.

### State updates (per `AGENTS.md` Phase 8b)

- [ ] `docs/SESSION_LOG.md` appended with a new entry.
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-A2 → IN_REVIEW under "In review 👀").
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-A2 row → IN_REVIEW).
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.

---

## Files created

```
app/services/analytics_correlation.py
tests/unit/services/test_analytics_correlation.py
```

## Files modified

```
app/domain/analytics.py                    ← add correlation_clusters function + tests
app/ui/pages/analytics.py                  ← replace A2 placeholder with _render_correlation_tab
app/ui/components/charts.py                ← add render_correlation_heatmap
app/ui/components/_chart_styles.py         ← add CORRELATION_COLORSCALE
tests/unit/domain/test_analytics.py        ← add TestCorrelationClusters class
tests/unit/ui/test_analytics_page.py       ← update A2 assertion
docs/PROJECT_STATE.md                      ← TICKET-A2 → IN_REVIEW
docs/SESSION_LOG.md                        ← new session entry
docs/TICKETS/BACKLOG.md                    ← TICKET-A2 row → IN_REVIEW
```

## Files NOT to modify

- `app/ui/pages/overview.py` — out of scope.
- `app/ui/pages/research.py` — out of scope.
- `app/ui/pages/manage.py` — out of scope.
- `app/ui/pages/tax.py` — out of scope.
- `app/services/analytics_performance.py`, `app/services/analytics_sizer.py`, `app/services/analytics_concentration.py` — touched only by their respective tickets (A1, A4, A5). If those don't exist yet, do not create empty stubs.
- `app/domain/analytics.py` signatures from A0 (`daily_returns`, `volatility_annualised`, `drawdown_series`, `max_drawdown`, `sharpe`, `sma`, `rsi`, `correlation_matrix`) — extending the file is fine; do not modify existing functions.
- `pyproject.toml` / `requirements.txt` — no new dependencies. Plotly is already installed (used by TICKET-022a/b). If the implementer's chosen colour-scale needs a new package, **stop and report**.

---

## Out of scope

- **Hierarchical clustering reorder** of the heatmap (rows/columns reordered to put correlated clusters adjacent). Useful for >20 positions; deferred to A2.x.
- **Rolling-correlation chart** between two pickable tickers over time. Different question ("how does correlation evolve") and deserves its own design.
- **Sector / region / factor correlation** — needs sector/region tags from Panel work. Out of v1.
- **Exporting the matrix to CSV.**
- **Configurable cluster threshold or bucket thresholds** in UI. Constants in code for v1.
- **Long windows** (180D, 1Y). 30/60/90 only in v1.
- **Cross-asset correlation** (vs SPY, vs gold, vs DXY). Pure intra-portfolio in v1.
- **Pre-computing the matrix nightly** (caching layer). Recompute on render; OHLC is already cached at the adapter level.
- **Click-to-jump from a cluster name into Technicals tab** filtered to that ticker. Static warning text only in v1.
- **Recording correlation snapshots** for historical comparison. No persistence.
- **Negative-correlation special-casing.** A negative correlation renders as a green cell and that's it; no separate "hedge" badge.

---

## Test cases (manual review checklist for the PR)

- [ ] Open the dashboard → Analytics → Correlation tab. Tab loads without error.
- [ ] With the current 13-position portfolio at 30D window, heatmap is 13×13, diagonal shows `—`, off-diagonal cells show 2-decimal values, cells are colour-graded.
- [ ] Hover any off-diagonal cell. Tooltip reads `TICKER_A vs TICKER_B: 0.NN`.
- [ ] The avg-correlation table on the right has 13 rows, sorted descending by Avg Correlation. Click the column header to reverse sort. Bucket badges render with the right colours per the thresholds in decision §5.
- [ ] Switch the window radio from 30D → 60D → 90D. Heatmap and table update on each switch. If any position is excluded at the longer windows, the skipped-tickers banner appears with the correct list.
- [ ] If any cluster of ≥3 positions exists with mutual correlation > 0.6 in the connected-components sense, one warning card per cluster renders below the heatmap. Cluster member list is alphabetical.
- [ ] If no clusters exist, no warning card area renders (no empty placeholder).
- [ ] Manually compute correlation between two of your positions over the last 30 trading days from a known external source (e.g. yfinance script, or a data provider) and confirm the heatmap cell is within rounding of that value.
- [ ] Switch to Live Overview, then back to Analytics → Correlation. Window selection persists (still on 60D if that's what you'd selected).
- [ ] Add a new position to the portfolio with only a few days of history. Reload Analytics → Correlation at 30D window. The new ticker appears in the skipped banner, not in the heatmap.
- [ ] No regressions on Performance / Technicals / Position Sizer / Concentration tab placeholders or implementations (whichever exist at merge time).
- [ ] No regressions on Live Overview, Manage Portfolio, Tax Dashboard, Research.

---

## Notes (architectural and methodological — for future AI sessions)

### Why connected-components and not cliques

True clique detection (every pair within the cluster crosses threshold) is the technically purer answer. Connected-components admits a cluster {A,B,C} where A↔C is below threshold as long as A↔B and B↔C are above. We accept this for v1 because:

1. The user's question is "are these positions secretly tied together," and B being a bridge between A and C is real signal — they all share an exposure to whatever B reflects.
2. Clique detection on graphs of arbitrary size is exponential; connected-components is linear. Performance only matters at >50 positions, but it's the right algorithmic choice for an ongoing primitive.
3. The warning text ("may not be acting as independent diversifiers") is honest about the connected-components definition.

If false positives become a problem in practice, A2.x can swap in clique detection — `correlation_clusters` is one function with a clear signature.

### Why neutral colour at 0.5, not 0

A naive heatmap puts neutral grey at 0 (the centre of the `[-1, 1]` range). For a long-only equity portfolio, almost every correlation is in `[0, 1]`; centring at 0 means the bulk of cells are in the warm half of the scale and the visual contrast is muted — exactly the wrong outcome when the user is looking for the high-correlation cells. Centring neutral at 0.5 puts the grey midpoint in the middle of the typical observed range, which means high cells (>0.5) saturate to red and low cells (<0.5) saturate to green. The trade-off is that genuine negative correlations become indistinguishable from very-low-positive — that's acceptable for v1 because they're rare and the avg-correlation table catches them numerically.

### Why trading-date intersection, not array-index alignment

Different exchanges have different holiday calendars. Frankfurt closes for Karfreitag and Tag der Deutschen Einheit; NYSE doesn't. If we naïvely zip two close arrays of length 60, we'd be correlating position A's "60th most recent trading day" with position B's "60th most recent trading day" — which are different calendar dates, and the returns aren't comparable. The right thing is to align on date, intersect, and compute on the overlap.

This is a known source of subtle correlation bugs in retail portfolio tools. Doing it correctly in v1 is cheaper than retrofitting later.

### Why insufficient-history positions are skipped, not partially included

Three approaches were considered:

1. **Pad with zeros / NaN.** Zeros corrupt the correlation (a flat-line series correlates 0 with everything, registering as a fake diversifier). NaN propagates through everything and the matrix is unusable.
2. **Compute pairwise on each pair's overlapping window.** Cells of the matrix are no longer comparable to each other (some computed on 60 days, some on 12), and the avg-correlation column averages across non-comparable cells. The resulting numbers are nominal and misleading.
3. **Skip the ticker entirely with a banner.** The user knows which tickers were excluded and why. The matrix that does render is internally consistent and honestly labelled.

Option 3 is the only honest answer. It's also the only one the user can act on (either pick a shorter window or wait).

### Why this ticket adds `correlation_clusters` to `app/domain/analytics.py` and not to the service module

`correlation_clusters` is a pure function over a `dict[str, dict[str, Decimal]]`. It has no I/O, no service dependencies, and is the kind of thing A1/A4/A5 might also want eventually (e.g. concentration analysis flagging correlation clusters in A5). Per A0's decision §4, the stats library is the single home for statistical primitives. Adding a ninth function here is exactly the path A0 anticipated.

### Why the diversification bucket logic is in the service layer, not the UI

The bucket label and colour are derived data, not presentation data. The same logic might appear later in a tooltip elsewhere, or in an export. Keeping it in `analytics_correlation.py` as a pure helper means there's one source of truth for "what's a high diversifier."

### What this ticket does NOT lock in for A3 / A4 / A5

- The heatmap helper is specific to correlation. A5's weight bar chart is a different chart type and doesn't reuse it.
- The diversification bucket constants are correlation-specific; the position-weight buckets in A4/A5 use their own constants (`MAX_POSITION_WEIGHT = 35` etc.) and are not relocated.
- The cluster-warning UI pattern (`st.warning` per cluster) is not extracted as a reusable component in this ticket; if A5 (or a future ticket) wants similar warning cards, the extraction can happen then.
