# STATE.md

<!-- The section headers below are matched by tools/sync_state.py regexes.
     If you rename or reorder them, update sync_state.py in the same PR. -->

> **This is the single source of truth for project state.**
> For chat sessions, `docs/CONTEXT.md` (auto-generated) contains this file plus code interfaces, UI surface, and GitHub activity — no manual paste required.

**Last updated:** 2026-05-13 by GitHub Actions (post-merge housekeeping)

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

**Milestone:** Company Deep Dive

### Done ✓ (last 5)
- TICKET-025 — Company data layer: models, ports, yfinance + Finnhub adapters, JSON cache with TTL (PR #53)
- TICKET-M3 — Tooling self-heal: branch guard, auto-milestone, Next-up reconciliation, GitHub Actions post-merge housekeeping (PR #56)
- TICKET-WFTEST — Housekeeping workflow smoke test (PR #58)
- TICKET-M4a — Auto-generated CONTEXT.md + chat verification protocol (PR #61)

### In review 👀

- TICKET-M4b — Consolidate workflow files, execution-time menu, Vivek quick-reference (PR pending)

### Closed without merging ⊘
- TICKET-009 — Manage Portfolio page (original spec) — superseded by TICKET-009-revised. See ADR-005 and PR #14.

### In progress 🚧

(none)

### Next up 📋

1. TICKET-M4b — Consolidate workflow files, execution-time menu, Vivek quick-reference
2. *C2 — Company Deep Dive page and Snapshot tab*
3. *C2 — Company Deep Dive page and Snapshot tab*
4. *Panel framework brainstorm session (see PANEL_BRAINSTORM_HANDOFF.md)*

### Blocked 🚫
- (none)

### Recent activity 📅

- 2026-05-13 — TICKET-M4a merged (PR #61)
- 2026-05-13 — TICKET-WFTEST merged (PR #58)
- 2026-05-13 — TICKET-M3 merged (PR #56)
- 2026-05-13 — TICKET-025 merged (PR #53)
- 2026-05-13 — TICKET-M2 merged (PR #52)

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

---

## How this file gets maintained

- **Claude Code** updates "In progress", "Next up", "In review", and "Done" sections as part of the implementation ritual (Steps 5, 8b).
- **GitHub Actions** (`post-merge-housekeeping.yml`) updates "Recent activity", "In review → Done", and the ticket file status on every merge.
- **Claude Chat (Vivek + Claude)** updates "Stack", "Architecture", "Key decisions", and "Open questions" after architectural conversations.
