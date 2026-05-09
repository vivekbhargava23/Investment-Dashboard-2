# BACKLOG.md

The single index of all tickets. Status flows: DRAFT → READY → IN_PROGRESS → IN_REVIEW → MERGED.

**Status conventions:**
- `DRAFT` — sketched, not yet detailed enough to implement
- `READY` — fully specified, picked up by the implementation agent next
- `IN_PROGRESS` — branch open, work happening
- `IN_REVIEW` — PR open, awaiting Vivek's merge
- `MERGED` — landed on `main`
- `CLOSED` — abandoned without merging (see notes for replacement ticket)
- `SUPERSEDED` — replaced by a later ticket; see notes

**Priority conventions:**
- `P0` — blocker: data correctness, security, or unblocks other work
- `P1` — core feature for the current phase
- `P2` — quality-of-life or polish on shipped work
- `P3` — speculative or contingent on a design decision not yet made

---

## Phase 0 — Foundation (data model, FIFO, repository)

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-000 | Repo scaffolding + CI setup | MERGED | P0 | 30–45 min |
| TICKET-001 | Domain models — Money, Transaction, Position, OpenLot | MERGED | P0 | 1 – 1.5 hr |
| TICKET-002 | FIFO engine — compute_positions, RealisedGain | MERGED | P0 | 2 – 2.5 hr |
| TICKET-003 | JSON Transaction Repository (port + adapter) | MERGED | P0 | 1 – 1.5 hr |
| TICKET-004-005 | yfinance adapter — prices + FX (consolidated, was 004+005) | MERGED | P0 | 2 – 2.5 hr |
| TICKET-006 | Valuation service — compute_live_positions, compute_portfolio_summary | MERGED | P0 | 1 – 1.5 hr |

> Note: TICKET-004 (ECB FX adapter) was removed in chat session 2026-05-03.
> Decision: use yfinance for both prices and FX. Folded into TICKET-004-005.

---

## Phase 1 — Minimum viable UI (shell, Live Overview, Manage Portfolio)

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-007 | Streamlit shell refactor + light theme | MERGED | P1 | 2 – 2.5 hr |
| TICKET-008 | Live Overview | MERGED | P1 | 2 – 2.5 hr |
| TICKET-008b | Positions table HTML leak fix + render_html helper | MERGED | P0 | 45 min |
| TICKET-008c | Currency-correctness audit + JPY support + data migration | MERGED | P0 | 1.5 – 2 hr |
| TICKET-009 | Manage Portfolio page (original spec) | CLOSED | — | — |
| TICKET-020 | TickerResolver port + yfinance adapter | MERGED | P1 | 1.5 – 2 hr |
| TICKET-009-revised | Manage Portfolio page (EUR-native input) | MERGED | P1 | 3 – 3.5 hr |
| TICKET-021 | Smooth ticker autocomplete (disk cache + streamlit-searchbox) | MERGED | P2 | 1.5 – 2 hr |

> Note: TICKET-009 closed without merging (see ADR-005 and PR #14). Replaced by TICKET-009-revised.

---

## Phase 2 — Tax engine & decision support

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-010 | Tax engine (Sparerpauschbetrag, Verlustverrechnungstopf, Teilfreistellung, Abgeltungsteuer) | MERGED | P1 | 2.5 – 3.5 hr |
| TICKET-011 | Tax Dashboard page (Sparerpauschbetrag tracker, harvest opportunity, tax exposure) | MERGED | P1 | 2 – 2.5 hr |
| TICKET-012 | Pre-trade sell simulator (FIFO lot preview + tax impact + portfolio impact) | MERGED | P1 | 2.5 – 3 hr |
| TICKET-023 | EUR-denominated & unsupported-suffix price check (SK Hynix bug) | MERGED | P0 | 1 – 1.5 hr |
| TICKET-024 | Sell simulator cold-start performance | MERGED | P2 | 1 – 1.5 hr |

---

## Phase 3 — Charts, history & research

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-013 | Daily NAV snapshot service | MERGED | P1 | 2 – 2.5 hr |
| TICKET-022a | Chart service + Plotly components (OHLC, line, sparkline) | MERGED | P1 | 2 – 2.5 hr |
| TICKET-022b | Research page + Live Overview chart integration | MERGED | P1 | 2 – 2.5 hr |

---

## Phase 4 — Analytics & Risk page

> TICKET-019 (single Analytics & Risk page covering Benchmark, Correlation, Technicals, Position Sizer, Price Targets) was SUPERSEDED by the A0–A5 series, which splits the page into a tabbed shell + one tab per concern. See chat session 2026-05-09 for the decision.

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-019 | Analytics & Risk page (single-page spec) | SUPERSEDED | — | — |
| TICKET-A0 | Analytics page shell + analytics stats library | MERGED | P1 | 2 – 2.5 hr |
| TICKET-A1 | Analytics: Performance tab v1 (KPIs, dual-line indexed chart, drawdown panel) | MERGED | P1 | 2.5 – 3 hr |
| TICKET-A4 | Analytics: Position Sizer tab v1 (risk-based and weight-based calculator) | MERGED | P1 | 2.5 – 3 hr |
| TICKET-A5 | Analytics: Concentration tab v1 (KPIs, weight bars, currency donut, table) | MERGED | P1 | 2 – 2.5 hr |
| TICKET-A2 | Analytics: Correlation tab v1 (heatmap, avg-corr table, cluster warnings) | MERGED | P1 | 2 – 2.5 hr |
| TICKET-A3 | Analytics: Technicals tab v1 (per-ticker chart with MA + RSI signals) | READY | P1 | 2 – 2.5 hr |

---

## Phase 5 — UI polish

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-U1 | Sidebar and topbar visual polish | READY | P1 | 90 min |

---

## Phase 6 — Investment Panel framework (pending design)

> See `docs/PANEL_BRAINSTORM_HANDOFF.md`. Schema-first design pending. The tickets below are placeholders from the original plan; they will likely be replaced by Panel-driven equivalents once the schema lands.

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-014 | Performance page with timeframe toggle | DRAFT | P3 | 1.5 hr |
| TICKET-015 | Lot Ledger page with edit-in-place | DRAFT | P3 | 2 hr |
| TICKET-016 | Thesis state machine (intact/watch/broken) | DRAFT | P3 | 1.5 hr |
| TICKET-017 | Decision Gates page | DRAFT | P3 | 2 hr |
| TICKET-018 | Behavioural Ledger | DRAFT | P3 | 2 hr |

---

## Next up (in execution order)

1. TICKET-A3 — Analytics: Technicals tab v1
2. TICKET-U1 — Sidebar and topbar visual polish
3. *Panel framework brainstorm session*

---

**Workflow reminder:** Tickets in DRAFT need to be detailed in Claude Chat before they move to READY. Only READY tickets are picked up by the implementation agent.
