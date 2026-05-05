 # PROJECT_STATE.md

> **This is the single source of truth for project state.**
> Paste this file at the start of any new Claude chat.
> Claude Code updates this at the end of every session.

**Last updated:** 2026-05-05 by Claude Chat (drafted tax engine, page, and simulator tickets)

---

## Project overview

Personal investment dashboard for tracking a Scalable Capital portfolio.
- German tax-aware (FIFO, Sparerpauschbetrag, Verlustverrechnungstopf)
- FX-aware (USD GDRs converted to EUR at transaction-date ECB rates)
- Live valuation layer (yfinance + Finnhub)
- Decision support layer (thesis tracking, decision gates, behavioural ledger)

This is a **greenfield rebuild**. The previous attempt
(github.com/vivekbhargava23/investment-panel-dashboard-2026) is archived as reference only.

---

## Stack

- **Language:** Python 3.11+
- **UI:** Streamlit (custom CSS for the dark mode look in the mockup)
- **Models:** Pydantic v2
- **Storage:** JSON file via repository pattern (swappable to SQLite later)
- **Pricing:** yfinance (Frankfurt/EUR) + Finnhub (US/USD), with fallback chain
- **FX:** ECB reference rates, cached locally
- **Testing:** pytest + hypothesis for the FIFO engine
- **Linting:** ruff, mypy strict on domain layer, import-linter for layer boundaries
- **CI:** GitHub Actions on every push and PR

---

## Workflow (who does what)

- **Vivek**: picks tickets, drafts them in Claude Chat, reviews PRs, merges PRs
- **Claude Chat**: helps draft tickets and ADRs, reviews architecture, holds strategic context
- **Claude Code**: implements tickets end-to-end (code + tests + commits + push + PR)

`main` is branch-protected. Only Vivek can merge.

---

## Architecture (high level)

```
app/
  domain/        ← Pure Python, no I/O. Models, FIFO, tax, thesis state.
  services/      ← Orchestration. Combines domain + ports.
  ports/         ← Interfaces (Protocols). Domain depends on these.
  adapters/      ← Concrete implementations. Swap freely.
  ui/            ← Streamlit pages. Render only — no logic.
tests/
  unit/          ← Domain only. No I/O. Runs in <1s.
  integration/   ← Services with fakes.
  e2e/           ← Full stack with real adapters.
docs/            ← All project state lives here.
```

See `docs/ARCHITECTURE.md` for the full rules.

---

## Current status

**Phase:** 0 — Foundation
**Sprint:** Sprint 0 — Repo setup and architecture scaffolding

### Done ✓
- TICKET-000 — Repo scaffolding and CI setup
- TICKET-001 — Domain models (Lot, Transaction, Position, Money, Currency)
- TICKET-002 — FIFO engine with replay-on-edit
- TICKET-003 — JSON Transaction Repository (port + adapter)
- TICKET-004-005 — yfinance adapter (prices + FX)
- TICKET-006 — Valuation service (lots × prices × FX → positions)
- TICKET-007 — Streamlit shell refactor + light theme
- TICKET-008 — Live Overview page (KPI tiles + positions table)
- TICKET-008b — Positions table HTML leak fix + render_html helper

### In review 👀
- (none)

### Closed without merging ⊘
- TICKET-009 — Manage Portfolio page (original spec) — superseded by TICKET-009-revised. See ADR-005 and PR #14.

### In progress 🚧
- (none)

### Next up 📋 (in order)
1. TICKET-008c — Currency-correctness audit + JPY support + data migration (P0)
2. TICKET-020 — TickerResolver port + yfinance adapter (P1)
3. TICKET-009-revised — Manage Portfolio (EUR-native input) (P1)
4. TICKET-010 — Tax engine (Sparerpauschbetrag, Verlustverrechnungstopf, Teilfreistellung, Abgeltungsteuer) (P1)
5. TICKET-011 — Tax Dashboard page (Sparerpauschbetrag tracker, harvest opportunity, tax exposure) (P1)
6. TICKET-012 — Pre-trade sell simulator (FIFO lot preview + tax impact + portfolio impact) (P1)

See `docs/TICKETS/BACKLOG.md` for the full ticket list with statuses.

### Blocked 🚫
- (none)

---

## Key decisions made so far

- ADR-001: Streamlit over FastAPI+React — fast iteration, single user, custom CSS sufficient
- ADR-002: JSON over SQLite (port preserved for swap)
- ADR-003: FIFO replay-on-edit (not immutable lots) — keeps data model clean, audit trail via git
- ADR-004: Cost basis frozen at transaction-date ECB FX
- ADR-005: User input is EUR-native; currency and FX inferred from ticker + broker EUR total

See `docs/DECISIONS/` for full ADRs.

---

## Open questions / parking lot

- (none yet)

---

## How this file gets maintained

- **Claude Code** updates the "Done", "In progress", "Next up", and "Blocked" sections at every session end as part of the session-end ritual.
- **Claude Chat (Vivek + Claude)** updates the "Stack", "Architecture", "Key decisions", and "Open questions" sections after architectural conversations.
- All changes go through PRs. Both AI surfaces propose changes via diffs, never silent edits.
