# COMPANY_DEEP_DIVE_HANDOFF.md

Handoff doc for the next chat session. Goal of next chat: **draft tickets C1–C7 for the Company Deep Dive milestone**, ready to file via `tools/draft_ticket.sh`.

This doc captures all decisions made in the brainstorming chat so the next chat starts at "let's draft tickets" — not "let's redesign the page."

---

## What this milestone is

A new **Company Deep Dive** page in the dashboard. Single ticker selected at top, six tabs of analytical views. Plus a **Watchlist** page (favorites) and a **glossary tooltip system** for technical terms.

**Why it exists:** to support complex investment decisions with structured, intuitive company information — beyond what the existing Research page shows. ETFs are out of scope (only individual companies).

**Milestone name:** `Company Deep Dive`

---

## Locked decisions

These were settled in the brainstorm chat. The next chat does not need to revisit them — only draft tickets that reflect them.

### Data & caching
- **Cache model:** local JSON cache with TTL, *not* on-demand fetch
  - Fundamentals: 24h TTL
  - Prices/multiples: 15min TTL during market hours, 24h after close
  - Profile (sector, ISIN): 30 days TTL
- **Cache location:** per-ticker file, `data/companies/<TICKER>.json` (gitignored)
- **Cache trigger:** auto-cache on every company search (cheap, makes revisits instant)
- **Refresh UX:** "Data as of HH:MM" timestamp visible on every page + manual refresh button per tab
- **Cache adapter pattern:** decorator-style adapter wrapping the real data adapter, same Port

### Watchlist
- **Single watchlist** in v1 (no folders/groups)
- **Storage:** `data/watchlist.json` (committed to repo)
- **Toggle:** star icon on company page header
- **Watchlist page:** grid of cards, each card = mini Snapshot tile (price, day Δ%, conviction, next catalyst)
- **Click card → full company page**
- ETFs out of scope; only individual companies
- Portfolio holdings should appear in watchlist automatically (implicit favorites) — design decision for ticket C7

### Edit mode
- Auto-fetched fields are **read-only** (no pencil)
- Manual fields use **inline edit** (click value → input → save on blur)
- One "Edit metadata" section per page at the bottom for bulk-edit of moat notes / peer set / segment overrides
- Manual fields in v1: peer ticker list, moat tag/notes, custom user notes

### Glossary / tooltips
- Small `ⓘ` icon next to non-obvious metric labels
- Hover/tap → 1–2 sentence definition + formula if relevant
- Centralized in `app/ui/glossary.py` with ~30 terms in v1
- Helper function callable from any page: `glossary_tooltip("sharpe_ratio")`
- Reusable / translatable later
- Retrofit onto all tabs as part of C7

### Search UX
- **Ticker symbol only** in v1 (no fuzzy name search)
- Sits at top of company page

### Data sources
- **yfinance** (primary): price, multiples, financials, dividends, share count, sector/industry/employees
- **Finnhub** (gap-filler): next earnings date, insider transactions, institutional holders, better quarterly history
- **Historical multiples** (P/E, EV/EBITDA over 5Y): compute from price history × historical EPS, not fetched directly
- ECB FX already wired in the app
- **Out of scope for v1:** segment revenue mix (would need 10-K parsing or LLM extraction) → Tab 2 (Business) is deferred to a later ticket C8

---

## Page structure (6 tabs)

```
[Snapshot] [Business — deferred] [Financials] [Valuation] [Capital & Owners] [Risk & Thesis — deferred]
```

In v1: Snapshot, Financials, Valuation, Capital & Owners are built. Business and Risk & Thesis are stubs (empty tab with "coming soon" — wait for Panel framework).

### Tab 1 — Snapshot
- Header strip: name, ticker, ISIN, sector, country, mcap, price, day Δ%, ⭐ star toggle
- 5-year price chart with 200DMA overlay
- 4 KPI tiles, each with 8-quarter sparkline behind the number:
  - Revenue growth (3Y CAGR)
  - EBIT margin (latest)
  - Net debt/EBITDA
  - FCF yield
- Valuation band: horizontal bar showing current P/E within own 5Y range, with marker
- Next catalyst card: "Q1 earnings in 12 days" + countdown

### Tab 3 — Financials (the meat, scrollable, three anchored sections)

**Growth section:**
- Revenue, gross profit, EBIT, net income, FCF
- **20-quarter bar+line chart** (bars = absolute, line on secondary axis = YoY%)
- Period toggle: 1Y / 3Y / 5Y / 10Y / MAX

**Profitability section:**
- Gross / EBIT / Net / FCF margins as small-multiples (4 mini line charts)
- ROIC, ROE — line chart, with WACC reference line if available

**Health section:**
- Net debt, Cash, Net debt/EBITDA — dual-axis bar+line
- Interest coverage — line with "danger zone <2x" shaded
- Current ratio, quick ratio — number + trend arrow
- Working capital cycle (DSO, DPO, DIO) — 3-line chart

**UX rule:** every chart has a hover tooltip with exact value + QoQ + YoY delta, and a "show data" expander revealing the underlying table.

### Tab 4 — Valuation
- Current multiples tile grid: P/E, P/S, EV/EBITDA, P/FCF, P/B, Dividend yield — each tile shows number + own-5Y-percentile dot
- **Hero chart: P/E (or EV/EBITDA) over 5Y** with mean ± 1σ bands and current dot at right edge — toggle between P/E and EV/EBITDA
- Peer multiples table: heatmap-colored (green = cheaper than peer median, red = richer)
- Implied growth: reverse-DCF — "current price implies X% growth for 10Y" + sensitivity slider
- Dividend history: 10Y bars with payout ratio line overlaid

### Tab 5 — Capital & Ownership

**Capital allocation:**
- 5Y stacked bar by year: Operating CF split into Capex / Buybacks / Dividends / M&A / Cash retained
- Share count trend — line (rising = dilutive, falling = net buybacks)
- SBC as % of revenue — line (important for tech)

**Ownership:**
- Top 10 institutional holders — table with % held + QoQ change (colored arrow)
- Insider transactions log — timeline strip with green/red dots (buys/sells) sized by $ value
- Insider ownership % — number with peer-median reference

### Tab 2 — Business (stub in v1)
Empty placeholder. Future: stacked area for revenue by segment over time (manual entry), revenue by geography, customer concentration Pareto bar, moat notes card, peer set chips.

### Tab 6 — Risk & Thesis (stub in v1)
Empty placeholder. Waits for Panel framework. Future: beta/vol/maxDD tiles, FX exposure pie, leverage stress test, Bull/Base/Bear range chart, conviction-over-time, decision log.

---

## Cross-cutting visual rules (apply everywhere)

1. Timeline orientation consistent: left = past, right = present
2. Every chart has a period toggle: 1Y / 3Y / 5Y / 10Y / MAX
3. YoY always available as tooltip delta (never force computation)
4. Color semantics global: green = better/cheaper/growing, red = worse/expensive/shrinking, gray = neutral
5. No raw-number tables as primary view — always behind a "show data" expander
6. Annotations on time-series: earnings dates, dividend ex-dates, splits as vertical lines
7. Every non-obvious metric label has a `ⓘ` glossary tooltip

---

## Architecture fit

```
app/domain/company.py          ← CompanyData, FinancialSnapshot, MultipleHistory models (Pydantic v2, frozen)
app/ports/company_data.py      ← Protocol: fetch_company(ticker) → CompanyData
app/adapters/company_yfinance/ ← yfinance implementation
app/adapters/company_finnhub/  ← Finnhub for gaps (insider tx, institutional holders, next earnings)
app/adapters/company_cache/    ← JSON cache wrapper with TTL (decorator pattern)
app/services/company.py        ← Orchestration: fetch-or-cache, watchlist mgmt
app/services/watchlist.py      ← Watchlist CRUD
app/ui/pages/company.py        ← Tabbed company deep dive page
app/ui/pages/watchlist.py      ← Watchlist grid
app/ui/glossary.py             ← Centralized term definitions + tooltip helper
data/companies/<TICKER>.json   ← Cache files (gitignored)
data/watchlist.json            ← Watchlist (committed)
```

Layer rules from `docs/ARCHITECTURE.md` apply: domain has no I/O, services depend on ports, only adapters touch yfinance/Finnhub/file I/O.

---

## Ticket plan (draft these in the next chat)

Seven tickets, all in Milestone `Company Deep Dive`. Suggested order = dependency order.

| # | Ticket title | Priority | Est | Depends on |
|---|---|---|---|---|
| **C1** | Company data layer: `CompanyData` model, ports, yfinance+Finnhub adapters, JSON cache with TTL | HIGH | 1.5h | — |
| **C2** | Company page shell: new `company.py` Streamlit page with ticker search, tab structure, cache-age banner, refresh button | HIGH | 1h | C1 |
| **C3** | Snapshot tab: header strip, 5Y price chart, 4 KPI tiles with sparklines, valuation band, next catalyst | HIGH | 1.5h | C2 |
| **C4** | Financials tab: Growth (bar+line), Profitability (small-multiples), Health (dual-axis + ratios) sections | HIGH | 2h | C2 |
| **C5** | Valuation tab: multiples grid, P/E-over-time hero chart with σ bands, peer table heatmap, dividend history | HIGH | 1.5h | C2 |
| **C6** | Capital & Ownership tab: cash-flow allocation stacked bar, share count, SBC%, institutional holders table, insider timeline | HIGH | 1.5h | C2 |
| **C7** | Watchlist page + ⭐ star toggle on company header + glossary tooltip system (`app/ui/glossary.py`) retrofitted across all tabs | HIGH | 1.5h | C3–C6 (so it can retrofit them) |

**Stubs added in C2** for Business (Tab 2) and Risk & Thesis (Tab 6) — empty tabs with "coming soon" + brief note explaining what they'll contain.

Total: ~10.5h of implementation work across 7 sessions.

---

## Things to decide in the next chat (don't pre-decide)

These are spec details the next chat should think through when drafting each ticket. Listed here so they aren't forgotten:

1. **C1:** exact shape of `CompanyData` Pydantic model — what fields, what's optional, how nested
2. **C1:** cache file format — single big JSON per ticker, or split into `<TICKER>_profile.json` + `<TICKER>_prices.json` + `<TICKER>_financials.json` for independent TTLs?
3. **C1:** what happens when yfinance returns partial data — `CompanyData` with optionals, or raise?
4. **C2:** ticker search input — autocomplete from cached tickers + free input?
5. **C3:** sparkline library — recharts/plotly/vega — match what other pages already use
6. **C4:** how to compute YoY% on quarterly bars when first 4 quarters don't have a prior year — show as gap or as 0?
7. **C5:** computing historical P/E — use trailing 4Q EPS at each historical date, or use calendar-year EPS? Pick one and document.
8. **C5:** peer set source — manual user entry only in v1, or seeded from Finnhub `company-peers`?
9. **C6:** SBC data availability — yfinance often misses this for non-US. What's the fallback?
10. **C7:** auto-include portfolio companies in watchlist? Yes/no. (Brainstorm leaned yes, but confirm in ticket spec.)
11. **C7:** glossary v1 term list — draft the ~30 terms

---

## Files to attach in the next chat

The next chat needs these files in its context to draft tickets correctly:

1. **`docs/PROJECT_STATE.md`** — current project state (paste at top, per the chat handoff protocol)
2. **Last 3 entries from `docs/SESSION_LOG.md`** — recent context
3. **`docs/METHODOLOGY.md`** — the ticket-drafting checklist, the Standard Handoff Bundle format, the lifecycle vocabulary
4. **`docs/ARCHITECTURE.md`** — layer rules so tickets reflect them (no I/O in domain, etc.)
5. **`docs/WORKFLOW.md`** — Vivek's day-to-day touchpoints (so the chat knows what handoff to produce)
6. **`docs/TICKETS/BACKLOG.md`** — to know what TICKET number to start at and what Milestones exist
7. **This file: `COMPANY_DEEP_DIVE_HANDOFF.md`** — all the locked decisions
8. **Sample of an existing well-formed ticket** (e.g. one of the recent MERGED ones like TICKET-A4 or TICKET-U1) — so the chat matches your ticket format exactly
9. **`tools/draft_ticket.sh`** (or a short description of what it expects on stdin) — so the chat produces the right shell block format. The spec format is:
   ```
   ID: TICKET-<NNN>
   TITLE: <one-line>
   MILESTONE: Company Deep Dive
   PRIORITY: HIGH
   ESTIMATE: <text>
   NEXT_UP: true|false
   ---
   <full markdown ticket body>
   ```

---

## How to open the next chat

Paste this:

> I'm continuing work on my investment dashboard. We've finished brainstorming the Company Deep Dive milestone and now need to draft 7 tickets (C1–C7) ready to file via `tools/draft_ticket.sh`.
>
> Here are the relevant files:
>
> [attach the 9 files above]
>
> Please draft TICKET-C1 first as a Standard Handoff Bundle (ticket .md + shell block). After I confirm, we'll move to C2, and so on.

Then go ticket by ticket, one chat-message → one ticket → one shell block → you run it → next ticket. That keeps each session tight and avoids context blowup.

---

## Anti-patterns to avoid in the next chat

(From METHODOLOGY.md's ticket-drafting checklist — re-stated here so they're top of mind.)

- ❌ No "documented approximation" placeholders. If yfinance doesn't expose segment data, the ticket says "segment data out of scope," not "use sector as proxy for now."
- ❌ No silent fallback to defaults. If FX or price fetch fails, the UI shows it — never silently substitutes.
- ❌ No module names colliding with stdlib. `company.py` is fine; avoid `html.py`, `json.py`, `email.py` etc.
- ❌ Bench-test each ticket spec against the real workflow before marking QUEUED — would I actually be able to fill out / look at / click through what this ticket produces, with data that actually exists from yfinance/Finnhub?
- ❌ Every acceptance criterion must be observable, not just "tests pass." Tests passing is necessary, not sufficient.
- ❌ Update `PROJECT_STATE.md` "Next up" when filing the first ticket.
