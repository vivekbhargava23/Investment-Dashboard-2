# BACKLOG.md

The single index of all tickets. Status flows: QUEUED → IN_PROGRESS → IN_REVIEW → MERGED.

**Status conventions:**
- `QUEUED` — fully specified and committed to `docs/TICKETS/`; GitHub issue exists with label `queued`; waiting to be picked up
- `IN_PROGRESS` — branch open, work happening; GitHub issue label `in-progress`
- `IN_REVIEW` — PR open, awaiting Vivek's merge
- `MERGED` — landed on `main` (issue auto-closed by `Closes #N` in PR)
- `CLOSED` — abandoned without merging (see notes for replacement ticket)
- `SUPERSEDED` — replaced by a later ticket; see notes

**Priority conventions:**
- `CRITICAL` — data correctness, security, or blocks active work
- `HIGH` — core feature for the current Milestone
- `MEDIUM` — quality-of-life or polish on shipped work
- `LOW` — speculative or contingent on a design decision not yet made

---

## Milestone — Foundation (data model, FIFO, repository)

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-000 | Repo scaffolding + CI setup | MERGED | CRITICAL | 30–45 min |
| TICKET-001 | Domain models — Money, Transaction, Position, OpenLot | MERGED | CRITICAL | 1 – 1.5 hr |
| TICKET-002 | FIFO engine — compute_positions, RealisedGain | MERGED | CRITICAL | 2 – 2.5 hr |
| TICKET-003 | JSON Transaction Repository (port + adapter) | MERGED | CRITICAL | 1 – 1.5 hr |
| TICKET-004-005 | yfinance adapter — prices + FX (consolidated, was 004+005) | MERGED | CRITICAL | 2 – 2.5 hr |
| TICKET-006 | Valuation service — compute_live_positions, compute_portfolio_summary | MERGED | CRITICAL | 1 – 1.5 hr |

> Note: TICKET-004 (ECB FX adapter) was removed in chat session 2026-05-03.
> Decision: use yfinance for both prices and FX. Folded into TICKET-004-005.

---

## Milestone — UI core (shell, Live Overview, Manage Portfolio)

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-007 | Streamlit shell refactor + light theme | MERGED | HIGH | 2 – 2.5 hr |
| TICKET-008 | Live Overview | MERGED | HIGH | 2 – 2.5 hr |
| TICKET-008b | Positions table HTML leak fix + render_html helper | MERGED | CRITICAL | 45 min |
| TICKET-008c | Currency-correctness audit + JPY support + data migration | MERGED | CRITICAL | 1.5 – 2 hr |
| TICKET-009 | Manage Portfolio page (original spec) | CLOSED | — | — |
| TICKET-020 | TickerResolver port + yfinance adapter | MERGED | HIGH | 1.5 – 2 hr |
| TICKET-009-revised | Manage Portfolio page (EUR-native input) | MERGED | HIGH | 3 – 3.5 hr |
| TICKET-021 | Smooth ticker autocomplete (disk cache + streamlit-searchbox) | MERGED | MEDIUM | 1.5 – 2 hr |

> Note: TICKET-009 closed without merging (see ADR-005 and PR #14). Replaced by TICKET-009-revised.

---

## Milestone — Tax engine

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-010 | Tax engine (Sparerpauschbetrag, Verlustverrechnungstopf, Teilfreistellung, Abgeltungsteuer) | MERGED | HIGH | 2.5 – 3.5 hr |
| TICKET-011 | Tax Dashboard page (Sparerpauschbetrag tracker, harvest opportunity, tax exposure) | MERGED | HIGH | 2 – 2.5 hr |
| TICKET-012 | Pre-trade sell simulator (FIFO lot preview + tax impact + portfolio impact) | MERGED | HIGH | 2.5 – 3 hr |
| TICKET-023 | EUR-denominated & unsupported-suffix price check (SK Hynix bug) | MERGED | CRITICAL | 1 – 1.5 hr |
| TICKET-024 | Sell simulator cold-start performance | MERGED | MEDIUM | 1 – 1.5 hr |

---

## Milestone — Charts & research

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-013 | Daily NAV snapshot service | MERGED | HIGH | 2 – 2.5 hr |
| TICKET-022a | Chart service + Plotly components (OHLC, line, sparkline) | MERGED | HIGH | 2 – 2.5 hr |
| TICKET-022b | Research page + Live Overview chart integration | MERGED | HIGH | 2 – 2.5 hr |

---

## Milestone — Analytics & Risk

> TICKET-019 (single Analytics & Risk page covering Benchmark, Correlation, Technicals, Position Sizer, Price Targets) was SUPERSEDED by the A0–A5 series, which splits the page into a tabbed shell + one tab per concern. See chat session 2026-05-09 for the decision.

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-019 | Analytics & Risk page (single-page spec) | SUPERSEDED | — | — |
| TICKET-A0 | Analytics page shell + analytics stats library | MERGED | HIGH | 2 – 2.5 hr |
| TICKET-A1 | Analytics: Performance tab v1 (KPIs, dual-line indexed chart, drawdown panel) | MERGED | HIGH | 2.5 – 3 hr |
| TICKET-A4 | Analytics: Position Sizer tab v1 (risk-based and weight-based calculator) | MERGED | HIGH | 2.5 – 3 hr |
| TICKET-A5 | Analytics: Concentration tab v1 (KPIs, weight bars, currency donut, table) | MERGED | HIGH | 2 – 2.5 hr |
| TICKET-A2 | Analytics: Correlation tab v1 (heatmap, avg-corr table, cluster warnings) | MERGED | HIGH | 2 – 2.5 hr |
| TICKET-A3 | Analytics: Technicals tab v1 (per-ticker chart with MA + RSI signals) | MERGED | HIGH | 2 – 2.5 hr |

---

## Milestone — UI polish

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-U1 | Sidebar and topbar visual polish | MERGED | HIGH | 90 min |

---

## Milestone — Workflow & tooling

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-M1 | Workflow vocabulary cleanup + GitHub Issues integration | IN_REVIEW | HIGH | 2 – 2.5 hr |
| TICKET-M2 | Add WORKFLOW.md (Vivek-facing workflow guide) | QUEUED | HIGH | 45 – 60 min |
| TICKET-M3 | Tooling self-heal: branch guard, auto-milestone, Next-up reconciliation, GitHub Actions post-merge housekeeping | QUEUED | HIGH | 1.5 – 2 hr |

---

## Milestone — Company Deep Dive

| ID | Title | Status | Priority | Est |
| TICKET-025 | Company data layer: models, ports, yfinance + Finnhub adapters, JSON cache with TTL | IN_REVIEW | HIGH | 1.5 – 2 hr |
|---|---|---|---|---|

---

## Milestone — Investment Panel framework (pending design)

> See `docs/PANEL_BRAINSTORM_HANDOFF.md`. Schema-first design pending. The tickets below are placeholders from the original plan; they will likely be replaced by Panel-driven equivalents once the schema lands.

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-014 | Performance page with timeframe toggle | LOW | LOW | 1.5 hr |
| TICKET-015 | Lot Ledger page with edit-in-place | LOW | LOW | 2 hr |
| TICKET-016 | Thesis state machine (intact/watch/broken) | LOW | LOW | 1.5 hr |
| TICKET-017 | Decision Gates page | LOW | LOW | 2 hr |
| TICKET-018 | Behavioural Ledger | LOW | LOW | 2 hr |

---

## Next up (in execution order)

1. TICKET-025 — Company data layer: models, ports, yfinance + Finnhub adapters, JSON cache with TTL
1. TICKET-M2 — Add WORKFLOW.md (Vivek-facing workflow guide)
1. TICKET-M1 — Workflow vocabulary cleanup + GitHub Issues integration *(in review)*
2. *Panel framework brainstorm session*

---

**Workflow reminder:** Tickets must be fully specified in Claude Chat before they move to QUEUED. Only QUEUED tickets are picked up by the implementation agent.
