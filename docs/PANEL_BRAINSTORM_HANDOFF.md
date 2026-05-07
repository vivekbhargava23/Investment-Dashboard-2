# Investment Panel — Brainstorm Handoff

> **Purpose of this file:** Hand-off context from the planning session of 2026-05-06 into a dedicated future Claude Chat session focused only on the Investment Panel framework. Paste this at the start of that session along with `PROJECT_STATE.md`.

---

## Where we landed

The Investment Panel work has been **separated from the rest of the dashboard roadmap**. The dashboard work (TICKET-012 sell simulator, TICKET-021 ticker autocomplete, TICKET-022 charting module) proceeds independently. The Panel design happens in its own session.

Key principle agreed: **schema first, code later.** We design the data structures the Panel produces and the dashboard consumes, before any code is written. The Streamlit Panel page is the *last* deliverable, not the first.

Second principle agreed: **Claude Chat hosts the discussion; the dashboard hosts the state.** We do not try to host the panel discussion inside the Streamlit app. Claude Chat is better at that than anything we'd build. The dashboard's role is to be the persistent memory and surfacing layer.

---

## What the Panel framework is meant to do

Stated plainly: **over time, the dashboard should know more about each stock than any single panel session does, and surface that accumulated knowledge at the moment of decision.**

Reference material from Vivek (in project knowledge):
- `Investment_Panel_v7.docx` — the full panel framework: 11 experts, Session Open Protocol, scoring rubric, behavioural ledger, time horizons, verdict definitions
- `Investment_Panel_Session1__1_.docx` — Discovery-mode session output (10 candidate names, Company Cards, Score Cards, Decision Log empty, Watchlist)
- `Investment_Panel_Session2.docx` — Research/Execution-mode session output (SK Hynix lot analysis, geopolitical mapping, 5-item Decision Log)

These are reference points, not templates. The schema must be designed from goals, not from those examples.

---

## What was rejected as a frame

Earlier in the planning session I proposed a "Path 1 (single-agent prompt) vs Path 2 (multi-agent)" framing. **Vivek correctly pushed back on this** — it's infrastructure-first thinking. The actual question is the schema and the workflow, not the orchestration. The session-hosting approach (Claude Chat for sessions, dashboard for state) makes the Path 1 vs Path 2 question moot.

---

## Open design questions to answer in the brainstorm session

These are the questions the next session needs to resolve. Order matters — Q1 and Q2 shape everything else.

### Q1 — Unit of accumulation
What is the primary entity the dashboard accumulates around?

- Per-ticker: dashboard knows things about NVDA, RHM, etc.
- Per-thesis: dashboard knows things about "AI infra power", "EU defence rearmament", "HBM supply concentration"
- Action-centric: dashboard's home page is open decisions + questions across portfolio
- Mix with one primary view — needs to be specified

This decides what the Panel page's main list looks like.

### Q2 — Primary use case at the moment of decision
When Vivek is about to act on a position, what does the dashboard show in 10 seconds?

- "Everything we've ever said about NVDA" (ticker-centric)
- "Current state of the AI infra thesis and which positions express it" (thesis-centric)
- "Open decisions + questions" (action-centric)
- "What's changed since last session" (diff-centric)
- Other

This shapes the Panel page layout more than anything else.

### Q3 — Authorship workflow
How does state get into the dashboard?

- Vivek writes markdown after each Claude Chat session, dashboard parses
- Claude in chat outputs structured JSON at session end, Vivek pastes
- Dashboard has forms for direct entry between sessions
- Mix — but pick the one that has to work first

Probably ends up mixed. Pick the primary path.

### Q4 — Time scope per record
For each Company Card / thesis / etc.:

- Track *current state only* (last thesis, last verdict, last score)
- Track *history* (all theses ever held, all verdict changes, score trajectories)

History is more powerful but doubles schema complexity. Could phase in.

### Q5 — Score system
- Keep the 5-dimension × 3-horizon scoring rubric from `Investment_Panel_v7.docx`
- Design a fresh scoring system
- Skip explicit scoring; let verdict (BUY/HOLD/TRIM/SELL) carry the signal

### Q6 — Coverage scope
Does every owned ticker get a Company Card automatically, or only ones the panel formally discussed? What about watchlist names that aren't owned?

### Q7 — Decision lifecycle
A Decision Log entry's lifecycle: Pending → Executed → Closed-out? Linked to a real `Transaction` in `portfolio.json` once executed? This is where Panel data touches portfolio data.

### Q8 — Open Question resolution
When a question resolves: stays in log with resolved-date and answer? Moves to archive? Gets converted into a thesis update or score change?

---

## Strawman artifact list (to confirm or revise)

Pulled from the v7 doc + the two real sessions, listed for reference. **The next session should confirm, drop, or replace.**

1. **Session Brief** — one-paragraph executive summary per session
2. **Company Card** — durable per-ticker record (thesis, bull/bear, scores, verdict, catalysts)
3. **Decision Log** — concrete actions with priority, timing, rationale, size
4. **Open Questions** — questions with status (Open / Resolves [date] / Resolved / Dropped)
5. **Watchlist** — flagged names without full Company Cards yet
6. **Position State Deltas** — before/after view per session, reconciled against `portfolio.json`
7. **Sector Heatmap** — was in Session 1, may be redundant
8. **Conviction Tracker** — multi-session score trends, may belong inside Company Card

Likely the right list is 5–6 items, not 8. Cut what doesn't pull weight.

---

## Recommended design process for the next session

Do not try to design the schema in the abstract. Instead:

1. **Pick one concrete near-term decision** Vivek would actually use the dashboard for. Examples:
   - "Thinking about adding to RHM next week — what do I want to see?"
   - "Reviewing whether MU is still a hold post-earnings — what do I want to see?"
   - "Onboarding 3 new ideas from research over the next month — what flow do I want?"
2. Walk through that interaction step by step in the dashboard.
3. The interaction dictates the schema. The schema gets the bones right because it was designed against a real use case.
4. Once one interaction works, sanity-check the schema against the other two real-session docs (Session 1 and Session 2) — does the existing output fit cleanly into the schema? If not, schema is wrong.
5. Output two artifacts:
   - `PANEL_SCHEMA.md` — markdown spec of the data structures
   - `PANEL_SESSION_TEMPLATE.md` — the markdown template Claude Chat fills in at session end

Only after these exist do we draft tickets for the dashboard side.

---

## Tentative ticket sequence (post-schema)

These get added to the backlog *after* the schema design session produces the two artifacts above. Numbering placeholder.

- **TICKET-040** — Panel schema v1 docs (the two markdown artifacts above; no code)
- **TICKET-041** — Replay Session 1 + Session 2 in v1 schema as validation; produce seed JSON files for the dashboard to consume
- **TICKET-042** — `app/ui/pages/panel.py` — read-only Panel page surfacing the schema's primary view (whatever Q1 + Q2 decide)
- **TICKET-043** — Cross-page integration (e.g., positions on Live Overview link to their Company Card; Decision Log entries with `ticker` field link to the position)

Anything beyond that is post-usage. After 5+ real panel sessions running through the schema, re-evaluate.

---

## Wider roadmap context (so the brainstorm session stays aligned)

The dashboard work happens in parallel and should not be blocked by Panel design:

1. TICKET-012 — Pre-trade sell simulator (drafted, ready to move to READY)
2. TICKET-021 — Smooth ticker autocomplete (new, to be drafted)
3. TICKET-022a — Chart service + components (new, to be drafted)
4. TICKET-022b — Research page + Live Overview chart integration (new, to be drafted)
5. **Panel schema design session** (this brainstorm)
6. TICKET-040+ — Panel implementation tickets

Tickets 013–019 from the original backlog are deferred or replaced; some (016 Thesis state, 017 Decision Gates, 018 Behavioural Ledger) will likely be replaced entirely by Panel-driven equivalents.

---

## How to start the next brainstorm session

Open a new Claude Chat. Paste:

1. `PROJECT_STATE.md` (current dashboard state)
2. This file (`PANEL_BRAINSTORM_HANDOFF.md`)
3. The three reference documents from project knowledge (`Investment_Panel_v7.docx`, `Investment_Panel_Session1__1_.docx`, `Investment_Panel_Session2.docx`)

Open with: *"Let's design the Panel schema. Start by picking one concrete near-term decision and walk me through what the dashboard should show me at that moment."*

Then drive Q1 and Q2 first; everything else falls out.

---

*Drafted 2026-05-06 in planning session — Vivek + Claude.*
