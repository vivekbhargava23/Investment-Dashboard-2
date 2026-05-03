# BACKLOG.md

The single index of all tickets. Status flows: DRAFT → READY → IN_PROGRESS → IN_REVIEW → MERGED.

---

## Phase 0 — Foundation

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-000 | Repo scaffolding + CI setup | MERGED | P0 | 30–45 min |
| TICKET-001 | Domain models — Money, Transaction, Position, OpenLot | MERGED | P0 | 1 – 1.5 hr |
| TICKET-002 | FIFO engine — compute_positions, RealisedGain | MERGED | P0 | 2 – 2.5 hr |
| TICKET-003 | JSON Transaction Repository (port + adapter) | READY | P0 | 1 – 1.5 hr |
| TICKET-004-005 | yfinance adapter — prices + FX (consolidated) | READY | P0 | 2 – 2.5 hr |
| TICKET-006 | Valuation service | DRAFT | P0 | 1 hr |

> Note: TICKET-004 (ECB FX adapter) was removed in chat session 2026-05-03.
> Decision: use yfinance for both prices and FX. Folded into TICKET-005.

## Phase 1 — Minimum viable UI

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-007 | Streamlit shell + dark CSS theme | DRAFT | P1 | 1 hr |
| TICKET-008 | Live Overview page — KPI tiles + positions table | DRAFT | P1 | 2 hr |
| TICKET-009 | Manage Portfolio page — add/edit/delete lots | DRAFT | P1 | 2 hr |

## Phase 2 — Tax & decisions

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|
| TICKET-010 | Tax engine — Sparerpauschbetrag + Verlustverrechnungstopf | DRAFT | P1 | 2 hr |
| TICKET-011 | Tax Dashboard page | DRAFT | P1 | 1.5 hr |
| TICKET-012 | Pre-trade sell simulator | DRAFT | P1 | 2 hr |

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

---

**Total estimated foundation work:** ~28 hours of Claude Code time across ~14 sessions.

**Workflow reminder:** Tickets in DRAFT need to be detailed in Claude Chat before they move to READY. Only READY tickets are picked up by Claude Code.
