# Redesign Discussion — Handoff

> **Purpose:** Paste this at the start of a fresh chat to continue the **dashboard redesign
> discussion**. This session set the strategy, reconciled it against the live board, and filed a
> consolidated set of tickets. The next chat is for **design discussion** (Wave B/C, open
> decisions, the two-surface buildout) — not implementation, and not drafting more tickets unless
> explicitly asked.
>
> **Read alongside:** `docs/REDESIGN_STRATEGY.md` (the *why/what*) and
> `docs/REDESIGN_BUILD_PLAN.md` (the *how/order* + ticket index). This file is the orientation
> layer that ties them together and lists what's still open to discuss.
>
> Date of this handoff: **2026-06-04**.

---

## 1. The north star (locked)

Reorganize the app around **zoomed-out vs zoomed-in**, driven by one persistent focus ticker:

- **Portfolio Home** — everything about the whole portfolio (a long, chart-rich overview).
- **Company Workspace** — everything about one stock (chart, fundamentals, technicals, your
  tranches, notes). Absorbs the old Research tab.
- A single **focus ticker** persists across views — pick Micron once, every surface reflects it,
  no re-typing, no full reload.

This dissolves four original complaints at once: redundant Research tab, re-entering tickers, the
"everything refreshes" feeling, and detail hidden in the sidebar instead of a long overview.

## 2. The eight ideas (the "dashboard from scratch" brainstorm)

Built backwards from the questions you actually ask, at three moments — **glance / review / decide**:

1. "What changed since I last looked" feed (movers, 52w, earnings)
2. Honest scoreboard — **XIRR vs just-holding-the-index** (the brutal-truth metric)
3. Concentration + **effective number of stocks** ("you have fewer bets than you think")
4. P&L attribution ("who's actually carrying me")
5. Downside framed viscerally — current drawdown, underwater chart, "a 2020 move = €X"
6. Tranche + **tax-aware selling surfaced inline** at the decision point
7. Forward-looking **catalyst strip** (earnings/ex-div per holding)
8. **What-if sandbox** (simulate the next tranche's impact before buying)

Two cross-cutting principles: **every number explains itself** ("how was this computed?" + an
"ask AI to explain" affordance), and **end at "so what?"** (nudge toward an action, not just figures).

## 3. Analytics rebuilt around decision-questions (important to carry forward)

The current Analytics page shows numbers for the sake of it (organized by stat category). The
rethink organizes every metric around a question:

1. **"Am I actually doing well?"** → XIRR + benchmark-relative; alpha/beta as the second layer. Equity curve vs benchmark.
2. **"How much risk am I carrying?"** → volatility, max + *current* drawdown (underwater chart), Sharpe/Sortino.
3. **"Where is my risk concentrated?"** → top-N weight, HHI / effective-N, sector/currency/geo exposure, correlation heatmap. (Most important for a concentrated book.)
4. **"What's driving my P&L?"** → per-position attribution (waterfall).

Technicals (RSI/MAs) demoted to the Company surface for a single name, not portfolio analytics.

## 4. Current state of the codebase / board

- **Board (GitHub Projects #2): ~77 Done.** Almost everything is already merged — the CSV cluster,
  `H1`, the `M`-series, `A0–A5`, `C1–C4`, and crucially **`THESIS-1`, `R5` (caching), `PERF-1`,
  `ROBUST-1`**. The `Status:` lines in ticket files are decorative/stale — the board is truth.
- `THESIS-1` already made thesis/horizon **editable data** (`app/domain/thesis_map.py`). Decision
  this session: **remove the thesis/horizon columns from the overview anyway, but keep the data layer.**
- `ROBUST-1` already shipped router-error surfacing + HTML escaping.
- Existing engines to **reuse, not rebuild:** FIFO, full German tax engine, sell simulator,
  Herfindahl/concentration, correlation, drawdown funcs, `CompanyData.next_catalyst`, the NAV
  snapshot service (`TICKET-013`).
- **NAV history is essentially empty** (`data/nav_snapshots.json`) — the service exists but nothing
  has populated it. This blocks every time-series view (scoreboard, drawdown, attribution).

## 5. What's been filed (the consolidated tickets)

8 redesign tickets, milestone **Dashboard Redesign**, issues **#139–#146**. Implementation order
(reordered on the board):

```
RD0 #139  Navigation & focus spine (focus ticker + retire Research)   — no deps
RD1 #140  Overview & Tax HTML overhaul (components, drop thesis cols)  — no deps; builds positions_table
RD2 #141  Sortable positions table                                     — needs RD1
RD3 #142  Unified ticker searchbox                                     — needs RD0   (was R3)
RD4 #143  Split analytics.py + explain-this-number component           — no deps     (was C5 + explain)
RD5 #144  NAV history backfill + capture                               — no deps; START EARLY (Opus)
RD6 #145  Inline tranches + tax-aware sell                             — needs RD1+RD2 (Wave A)
RD7 #146  Concentration + effective-N block                            — needs RD4    (Wave A)
```

- Folded & closed: `R3→RD3`, `C5→RD4`, `C6→RD1` (issues #103/#110/#111).
- **Kept open:** `R4` #104 (unify period selector) — Wave B chart polish.
- Highest-value proof slice: **RD0 → RD1 → RD6.**
- These cover Foundation + Wave A only. **Wave B (RD8–RD10) and Wave C (RD11–RD13) are NOT drafted**
  — they're scoped in `REDESIGN_BUILD_PLAN.md` and are the main subject for the next discussion.

## 6. Open decisions for the next discussion

These are the real forks to resolve before Wave B work — bring them to the fresh chat:

1. **Benchmark** for the equity curve / alpha / scoreboard — single (VWCE) or selectable?
2. **XIRR vs TWR** as the headline return number (money-weighted vs time-weighted).
3. **Where Analytics lives long-term** — its own tab, or dissolved into Portfolio Home once rich?
4. **Streamlit's full-rerun model** — is focus-state + the merged caching enough for the "instant"
   feel, or does it need a deeper fix?
5. **Wave B/C detailed design** — what each of RD8–RD13 actually looks like (charts, layout,
   data sources for 52w/earnings, the what-if interaction).
6. **CSV import + reset rethink** — the import workbench is merged but the upload flow is
   undocumented and there's no "wipe & start fresh." This is a separate parallel track to scope.
7. **Two-surface buildout** — RD0–RD7 add the spine and blocks; the actual Portfolio Home page and
   Company Workspace restructure haven't been designed as tickets yet.

## 7. Workflow notes / loose ends

- **`.claude/settings.json` fix is pending** — it was malformed (junk + carriage returns) and
  caused permission-prompt fatigue. A corrected version was generated; apply it by copying the
  prepared file over `.claude/settings.json` (the app blocks the agent from writing there directly).
- **`gh issue close` takes one issue number per call** — loop for multiple, never space-separate.
- The agent in Cowork has **no `gh` and no network git fetch** — board/issue actions are done by
  Vivek in the terminal or via the board UI. Project board is #2.
- Division of labor (see `AGENTS.md`): Vivek picks/reviews/merges; the implementation agent writes
  code/tests, opens PRs, moves board status. One ticket = one branch = one PR.
