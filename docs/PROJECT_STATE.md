 # PROJECT_STATE.md

> **This is the single source of truth for project state.**
> Paste this file at the start of any new Claude chat.
> Claude Code updates this at the end of every session.

**Last updated:** 2026-05-09 by Claude Code (TICKET-A2 merged, TICKET-A3 starting)

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
  (also: fixed pre-existing test import break: test_html_helper.py referenced app.ui.html instead of app.ui.render)
- TICKET-008c — Currency enum JPY, ticker↔currency validator, LegacyDataError, migration script (PR #19)
- TICKET-020 — TickerResolver port + yfinance adapter (PR #20)
- TICKET-009-revised — Manage Portfolio page (EUR-native input, two-step form) (PR #21)
- TICKET-010 — Tax engine (Sparerpauschbetrag, Verlustverrechnungstöpfe, Teilfreistellung, Abgeltungsteuer) (PR #22)
- TICKET-011 — Tax Dashboard page (YTD tiles, harvest opportunity, tax exposure, profile editor) (PR #23)
- TICKET-012 — Pre-trade sell simulator (FIFO lot preview, marginal tax, portfolio impact, Manage Portfolio handoff) (PR #26)
- TICKET-021 — Smooth ticker autocomplete (disk cache + streamlit-searchbox) (PR #27)
- TICKET-023 — EUR-denominated & unsupported-suffix price check + Add form UX (price-per-share input, shares step=1, back-navigation state restore) (PR #28)
- TICKET-024 — Sell simulator cold-start performance (PR #29)
- TICKET-022a — Chart service + Plotly components (OHLC, line, sparkline) (PR #37)
- TICKET-022b — Research page + Live Overview chart integration (PR #38)
- TICKET-013 — Daily NAV snapshot service
- TICKET-A0 — Analytics page shell + analytics stats library (PR #41)
- TICKET-A1 — Analytics: Performance tab v1 (PR #42)
- TICKET-A5 — Analytics: Concentration tab v1 (PR #43)
- TICKET-A4 — Analytics: Position Sizer tab v1 (PR #45)
- TICKET-A2 — Analytics: Correlation tab v1 (PR #46)

### In review 👀
- (none)

### Closed without merging ⊘
- TICKET-009 — Manage Portfolio page (original spec) — superseded by TICKET-009-revised. See ADR-005 and PR #14.

### In progress 🚧
- (none)

### Next up 📋 (in order)
1. TICKET-A3 — Analytics: Technicals tab v1
2. TICKET-U1 — Sidebar and topbar visual polish
3. *Panel framework brainstorm session (see PANEL_BRAINSTORM_HANDOFF.md)*

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

- **Investment Panel framework** — schema-first design pending in a dedicated brainstorm session. See `docs/PANEL_BRAINSTORM_HANDOFF.md`. Old TICKET-016 / 017 / 018 (Thesis state, Decision Gates, Behavioural Ledger) likely get replaced by Panel-driven equivalents once the schema lands.
- **Hardcoded `_PLACEHOLDER_THESIS_STATUS` / `_PLACEHOLDER_HORIZON` dicts in `app/ui/pages/overview.py`** — still 12-ticker fixed. Adding a 13th ticker via Manage Portfolio defaults silently. Slated to migrate to Panel-managed JSON once schema lands; not blocking.
- **TICKET-013 (Daily NAV cache)** — drafted as READY (2026-05-08). Decided to proceed independently of the Panel design; the snapshot table is foundational enough that Panel work can layer on top later if needed.

---

## How this file gets maintained

- **Claude Code** updates the "Done", "In progress", "Next up", and "Blocked" sections at every session end as part of the session-end ritual.
- **Claude Chat (Vivek + Claude)** updates the "Stack", "Architecture", "Key decisions", and "Open questions" sections after architectural conversations.
- All changes go through PRs. Both AI surfaces propose changes via diffs, never silent edits.
