# TICKET-026 — Company Deep Dive page shell: ticker search, tab structure, chart style sampler, cache-age banner, refresh button

**Status:** QUEUED
**Priority:** HIGH
**Estimated session length:** 1.5 – 2 hr
**Drafted by:** Vivek + Claude (chat 2026-05-13)
**Implemented by:** Claude Code (session TBD)
**Depends on:** TICKET-025 (CompanyData model, CompanyDataProvider port, all adapters, services — merged)

> **After this ticket merges, the Company Deep Dive page exists in the sidebar, loads company data for any ticker, and presents six tabs (four empty, two stubs).** It also introduces a chart theme module with 3 style options rendered as a sampler so Vivek picks the visual direction for the entire milestone before any tab content is built.

---

## Problem

TICKET-025 built the full data layer (domain models, port, adapters, cache, service) but there is no UI to consume it. The Company Deep Dive milestone needs a page shell before any tab content (C3–C6) can be implemented. This ticket creates the page, wires the data provider, and establishes the visual foundation.

Additionally, the app's existing charts (plotly with default styling) look generic. Before building 15+ charts across C3–C6, this ticket introduces a chart theme module with 3 style variations rendered on the page as a sampler. Vivek picks a style during PR review; the chosen style becomes the standard for all subsequent tickets. The sampler is removed in C3 (when real Snapshot content replaces it).

---

## Acceptance criteria

### `app/ui/pages/company.py` — new page

- [ ] New Streamlit page file with `def render() -> None`.
- [ ] **Page title:** "Company Deep Dive" (rendered as `st.title`).
- [ ] **Ticker input:** uses the existing `render_ticker_searchbox` component from `app/ui/components/ticker_searchbox.py`. Key: `"company_ticker"`. Placeholder: `"Search by ticker or company name..."`.
- [ ] **Recent tickers section:** below the search box, show a row of `st.button` pills for the last 5 tickers the user has viewed. Source: scan `data/companies/` for subdirectories, sort by most-recent `profile.json` `fetched_at` timestamp, take top 5. Clicking a pill sets the ticker. If no cached companies exist, hide this section.
- [ ] **On ticker selection:** call `get_company_provider().get_company(ticker)` to get `CompanyData`. Show a `st.spinner("Loading company data...")` during the fetch.
- [ ] **Error handling:** if `CompanyDataError` is raised (invalid ticker, all sources down), show `st.error(str(e))`. Do not crash the page.
- [ ] **Cache-age banner:** after data loads, show a subtle info line: `"Data as of {time} · Profile {age} · Prices {age} · Financials {age}"` using the three `*_fetched_at` fields on `CompanyData`. Format ages as "2m ago", "3h ago", "1d ago" using a helper function in `app/ui/format.py`.
- [ ] **Refresh button:** a `st.button("🔄 Refresh")` in the top-right (same row as the title, via `st.columns`). On click, calls `refresh_company_section` for all three sections sequentially, then reruns. (Per-section refresh buttons come in C3–C6 per tab.)
- [ ] **Fetch-error banners:** for each key in `CompanyData.fetch_errors`, show `st.warning(f"{section}: {error}")` below the cache-age line.
- [ ] **Six tabs** via `st.tabs(["Snapshot", "Business", "Financials", "Valuation", "Capital & Owners", "Risk & Thesis"])`.
  - **Snapshot tab:** placeholder text `"Snapshot content — TICKET-027"`. Plus the chart style sampler (see below).
  - **Business tab (stub):** `st.info("📋 Business tab coming soon — waiting for segment data sources and Panel framework.")` with a brief note: "Will include: revenue by segment, revenue by geography, customer concentration, moat notes, peer set."
  - **Financials tab:** placeholder text `"Financials content — TICKET-028"`.
  - **Valuation tab:** placeholder text `"Valuation content — TICKET-029"`.
  - **Capital & Owners tab:** placeholder text `"Capital & Ownership content — TICKET-030"`.
  - **Risk & Thesis tab (stub):** `st.info("📋 Risk & Thesis tab coming soon — waiting for Panel framework.")` with a brief note: "Will include: beta, volatility, max drawdown, FX exposure, leverage stress test, conviction tracker, decision log."
- [ ] **No business logic in this file.** All data comes from the service layer via the provider. Tab content is delegated to separate modules in C3–C6.

### `app/ui/components/chart_theme.py` — new module: chart style system

- [ ] Defines a `ChartStyle` frozen Pydantic model (or a simple dataclass) holding: `bg_color`, `grid_color`, `text_color`, `font_family`, `font_size`, `accent_colors` (list of 6 hex strings for series), `bar_opacity`, `line_width`, `grid_width`, `show_gridx`, `show_gridy`, `margin` dict, `hover_template_style`.
- [ ] Defines three named presets:
  - **`STYLE_CLEAN`** — light/minimal: white background, very light gray grid (#f0f0f0), dark text, thin lines (1.5px), muted accent palette (slate blue, muted teal, warm gray, dusty rose, sage, amber). Font: the app's existing CSS font stack. Goal: Bloomberg-terminal-inspired clarity without the clutter.
  - **`STYLE_DARK`** — dark theme: #1a1a2e background, subtle grid (#2a2a3e), light text (#e0e0e0), slightly thicker lines (2px), vibrant accents on dark (electric blue, coral, mint, gold, violet, salmon). Goal: modern fintech dashboard feel.
  - **`STYLE_EDITORIAL`** — magazine/print: off-white (#fafaf8) background, no vertical grid, horizontal grid only in light gray, serif-adjacent font for titles, clean sans for data, muted earth-tone accents (navy, terracotta, forest, charcoal, burgundy, olive). Goal: FT/Economist chart aesthetic.
- [ ] Defines `apply_style(fig: go.Figure, style: ChartStyle) -> go.Figure` — applies the style's layout properties to any plotly figure. Returns the figure for chaining.
- [ ] Defines `get_accent_color(style: ChartStyle, index: int) -> str` — returns the accent color at index (mod length for wrap-around).
- [ ] Defines `styled_bar_trace(style: ChartStyle, index: int, **kwargs) -> go.Bar` — convenience for creating a bar trace with the style's colors and opacity pre-applied.
- [ ] Defines `styled_line_trace(style: ChartStyle, index: int, **kwargs) -> go.Scatter` — convenience for creating a line trace with style's colors and width pre-applied.
- [ ] **No I/O, no Streamlit imports.** This is a pure plotly-styling module. Streamlit rendering happens in the page files.

### Chart style sampler (temporary, in Snapshot tab placeholder)

- [ ] Renders three identical sample charts side by side (via `st.columns(3)`), each applying one of the three styles. The sample chart: a simple 12-point bar+line chart with fake data (e.g. quarterly revenue bars + margin% line on secondary axis) — enough to show the visual character of each style.
- [ ] Below each chart, the style name and a 1-line description.
- [ ] A `st.info` note: "Pick a chart style during PR review. The chosen style will be applied across all Company Deep Dive tabs. The sampler will be removed in TICKET-027."
- [ ] **This sampler is explicitly temporary.** TICKET-027 (Snapshot tab) removes it and replaces with real content.

### `app/ui/wiring.py` — add company provider

- [ ] Add `get_company_provider() -> CompanyDataProvider` function. Implementation: calls `build_company_provider()` from `app/adapters/company_factory.py`. Uses `@st.cache_resource` for singleton behavior (the provider holds cache state; creating multiple instances wastes memory).
- [ ] Import `CompanyDataProvider` from `app/ports/company_data`.
- [ ] Import `build_company_provider` from `app/adapters/company_factory`.

### `app/ui/format.py` — add relative time formatter

- [ ] Add `format_relative_time(dt: datetime | None) -> str` — returns human-readable relative time: "just now" (<1min), "2m ago", "1h ago", "3h ago", "1d ago", "5d ago", etc. Returns "unknown" if `dt` is None.
- [ ] Pure function, no side effects. Accepts timezone-aware datetime, compares to `datetime.now(UTC)`.

### `app/ui/main.py` — register the new page

- [ ] Add the Company Deep Dive page to the Streamlit navigation. It should appear in the sidebar under the PORTFOLIO section, after "Research". Sidebar label: "Company". Icon: `🏢` (or whatever icon convention the existing pages use — match the pattern).
- [ ] Import `app.ui.pages.company` and wire its `render()` function.

### `.gitignore` — verify `data/companies/` is already gitignored

- [ ] TICKET-025 should have added this. Verify it's present. If missing, add `data/companies/`.

### Tests

- [ ] `tests/unit/ui/test_chart_theme.py` — new test file:
  - `apply_style` on a bare `go.Figure()` sets layout properties (bg_color, font, grid) correctly for each of the 3 styles.
  - `get_accent_color` wraps around when index > len(accent_colors).
  - `styled_bar_trace` returns a `go.Bar` with correct marker color and opacity.
  - `styled_line_trace` returns a `go.Scatter` with correct line color and width.
- [ ] `tests/unit/ui/test_format_relative_time.py` — new test file:
  - `format_relative_time(None)` → `"unknown"`.
  - `format_relative_time(now - 30s)` → `"just now"`.
  - `format_relative_time(now - 5min)` → `"5m ago"`.
  - `format_relative_time(now - 3hr)` → `"3h ago"`.
  - `format_relative_time(now - 2days)` → `"2d ago"`.

### State updates (per `AGENTS.md` Step 8b)

- [ ] `docs/STATE.md` updated (TICKET-026 in "In review 👀").
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --base main`, body contains `Closes #<N>`.

---

## Files created

```
app/ui/pages/company.py
app/ui/components/chart_theme.py
tests/unit/ui/test_chart_theme.py
tests/unit/ui/test_format_relative_time.py
```

## Files modified

```
app/ui/wiring.py               ← add get_company_provider()
app/ui/format.py               ← add format_relative_time()
app/ui/main.py                 ← register Company page in sidebar nav
```

## Files NOT to modify

- `app/domain/**` — no domain changes in this ticket.
- `app/ports/**` — ports are stable from TICKET-025.
- `app/adapters/**` — adapters are stable from TICKET-025.
- `app/services/**` — services are stable from TICKET-025.
- `app/ui/pages/research.py` — Research page stays as-is. Do not consolidate or refactor it.
- `app/ui/pages/overview.py` — Live Overview is unrelated.
- `app/ui/components/ticker_searchbox.py` — reuse as-is; do not modify.
- `app/ui/components/charts.py` — existing chart components stay. The new `chart_theme.py` is additive, not a replacement. Existing pages continue using their current chart calls until a future "retrofit" ticket.
- `pyproject.toml` / `environment.yml` — no new dependencies.
- `.importlinter` — existing rules cover the new files.

---

## Out of scope

- **Tab content** — Snapshot, Financials, Valuation, Capital & Owners content. All TICKET-027 through TICKET-030.
- **Watchlist** — star toggle, watchlist page, `data/watchlist.json`. TICKET-031.
- **Glossary** — `app/ui/glossary.py`, ⓘ tooltips. TICKET-031.
- **Per-tab refresh buttons** — each tab gets its own section-specific refresh in C3–C6. This ticket only has the global refresh button.
- **Retrofitting chart theme to existing pages** (Research, Analytics, etc.) — future ticket after style is chosen.
- **Killing or merging the Research page** — separate decision, separate ticket.
- **`@st.cache_data` on company data** — caching is at the adapter layer, not UI.
- **Background refresh / auto-refresh timer** — out of scope for entire milestone.

---

## Test cases (manual review checklist for the PR)

- [ ] Open the app. "Company" appears in the sidebar under PORTFOLIO, after Research. Click it.
- [ ] Page shows title "Company Deep Dive", the ticker searchbox, and the refresh button.
- [ ] Type "NVDA" into the searchbox. Select the match. Page loads data with spinner. Six tabs appear.
- [ ] Cache-age banner shows three timestamps. All say "just now" or "Xm ago" on first load.
- [ ] Click each tab. Snapshot shows the chart style sampler (3 charts). Business and Risk & Thesis show stub messages. Financials, Valuation, Capital & Owners show placeholder text.
- [ ] The 3 sample charts in the sampler are visually distinct. Each has a different feel.
- [ ] Click Refresh. Page reloads with updated timestamps.
- [ ] Type a nonsense ticker (e.g. "ZZZZZNOTREAL"). Error message appears, no crash.
- [ ] Navigate to other pages (Live Overview, Research). They work unchanged.
- [ ] `pytest && ruff check . && mypy app/ && lint-imports` — all pass.

---

## Notes

### Why the chart style sampler is in this ticket, not a separate one

The style decision gates everything visual in C3–C6. If we pick the style in C2's PR review, C3 (Snapshot tab) implements real charts with the chosen style from day one. Without this, C3 would either pick a style unilaterally or defer styling to a retrofit pass.

### Why reuse `render_ticker_searchbox` instead of plain `st.text_input`

The searchbox component already exists, supports fuzzy name+ticker matching, and provides a better UX than raw ticker entry. The handoff doc said "ticker symbol only in v1" but the searchbox already handles both — there's no cost to reusing it and it's strictly better UX.

### Why `@st.cache_resource` for the company provider

The `CacheCompanyAdapter` holds file-path state and the inner composite holds adapter instances. Creating a new one on every Streamlit rerun wastes setup. `cache_resource` gives us a singleton for the session. This matches how `get_price_provider()` etc. likely work in `wiring.py`.

### Assumption: sidebar registration pattern

Assumes `app/ui/main.py` or `app/ui/components/sidebar.py` has a page registry dict or list that maps page names → render functions. The agent should inspect the actual registration mechanism and follow the existing pattern. If the pattern is `st.navigation` or `st.Page`, follow that. If it's a manual dict in `sidebar.py`, add to that dict.

### Assumption: `render_ticker_searchbox` returns `TickerMatch | None`

Confirmed from CONTEXT.md. The `TickerMatch.symbol` field gives us the ticker string to pass to `get_company_provider().get_company(symbol)`.
