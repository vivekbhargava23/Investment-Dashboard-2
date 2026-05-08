# BACKLOG.md

The single index of all tickets. Status flows: DRAFT → READY → IN_PROGRESS → IN_REVIEW → MERGED.

---

## Phase 0 — Foundation

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-000 | Repo scaffolding + CI setup | MERGED | P0 | 30–45 min |
| TICKET-001 | Domain models — Money, Transaction, Position, OpenLot | MERGED | P0 | 1 – 1.5 hr|
| TICKET-002 | FIFO engine — compute_positions, RealisedGain | MERGED | P0 | 2 – 2.5 hr |
| TICKET-003 | JSON Transaction Repository (port + adapter) | MERGED | P0 | 1 – 1.5 hr |
| TICKET-004-005 | yfinance adapter — prices + FX (consolidated, was 004+005) | MERGED | P0 | 2 – 2.5 hr |
| TICKET-006 | Valuation service — compute_live_positions, compute_portfolio_summary | MERGED | P0 | 1 – 1.5 hr |

> Note: TICKET-004 (ECB FX adapter) was removed in chat session 2026-05-03.
> Decision: use yfinance for both prices and FX. Folded into TICKET-004-005.

## Phase 1 — Minimum viable UI

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-007 | Streamlit shell refactor + light theme | MERGED | P1 | 2 – 2.5 hr |
| TICKET-008 — Live Overview — MERGED | P1 | 2 – 2.5 hr |
| TICKET-009 | Manage Portfolio page (original spec — superseded by 009-revised) | CLOSED | P1 | 2 hr |
| TICKET-008c | Currency-correctness audit + JPY support + data migration | MERGED | P0 | 1.5 – 2 hr |
| TICKET-020 | TickerResolver port + yfinance adapter | MERGED | P1 | 1.5 – 2 hr |
| TICKET-009-revised | Manage Portfolio page (EUR-native input) | MERGED | P1 | 3 – 3.5 hr |
| TICKET-021 | Smooth ticker autocomplete (disk cache + streamlit-searchbox) | MERGED | P1 | 1.5 – 2 hr |

## Phase 2 — Tax & decisions

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-010 | Tax engine (Sparerpauschbetrag, Verlustverrechnungstopf, Teilfreistellung, Abgeltungsteuer) | MERGED | P1 | 2.5 – 3.5 hr |
| TICKET-011 | Tax Dashboard page (Sparerpauschbetrag tracker, harvest opportunity, tax exposure) | MERGED | P1 | 2 – 2.5 hr |
| TICKET-012 | Pre-trade sell simulator (FIFO lot preview + tax impact + portfolio impact) | MERGED | P1 | 2.5 – 3 hr |
| TICKET-023 | EUR-denominated & unsupported-suffix price check (SK Hynix bug) | READY | P0 | 1 – 1.5 hr |
| TICKET-024 | Sell simulator cold-start performance (repeated slow renders after restart) | READY | P1 | 1 – 1.5 hr |

## Phase 3 — Performance & history

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-013 | Daily NAV cache | DRAFT | P2 | 2 hr |
| TICKET-014 | Performance page with timeframe toggle | DRAFT | P2 | 1.5 hr |
| TICKET-015 | Lot Ledger page with edit-in-place | DRAFT | P2 | 2 hr |

## Phase 4 — Decision support

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-016 | Thesis state machine (intact/watch/broken) | DRAFT | P2 | 1.5 hr |
| TICKET-017 | Decision Gates page | DRAFT | P2 | 2 hr |
| TICKET-018 | Behavioural Ledger | DRAFT | P2 | 2 hr |
| TICKET-019 | Analytics & Risk page (Benchmark/Drawdown, Correlation, Technicals, Position Sizer, Price Targets) | DRAFT | P3 | TBD |

## Phase 5 — Charts & research

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-022a | Chart service + Plotly components (OHLC, line, sparkline) | DRAFT | P1 | 2 – 2.5 hr |
| TICKET-022b | Research page + Live Overview chart integration | IN_REVIEW | P1 | 2 – 2.5 hr |

---

**Total estimated foundation work (Phase 0 + 1):** ~12 hours of Claude Code time across ~8 sessions.

**Workflow reminder:** Tickets in DRAFT need to be detailed in Claude Chat before they move to READY. Only READY tickets are picked up by Claude Code.
