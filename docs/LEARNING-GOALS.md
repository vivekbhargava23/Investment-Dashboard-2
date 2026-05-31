# LEARNING-GOALS.md — the other purpose of this project

This project has two purposes that run in parallel. Both are legitimate. Neither subordinates the other.

1. **A working investment dashboard for Vivek.** Tax-aware, FX-aware, German-rules-aware. Used daily. Has to actually work.
2. **A live lab for learning the AI development ecosystem.** Vivek doesn't write code. The whole project is a vehicle for understanding how AI tools build software in 2025–2026 — agentic CLIs, MCPs, plugins, subagents, embedded LLM features, multi-model workflows, and whatever lands next.

**The two purposes are not in conflict.** Every AI-ecosystem experiment lands as a real ticket and is evaluated like any other: does it make the product better? If yes, file and implement. If only the learning value is real, write it up in `docs/LEARNING-NOTES/` (a notebook, not source code).

This file is the **persistent statement of mission #2**. AGENTS.md, METHODOLOGY.md, and ARCHITECTURE.md cover mission #1 in detail. This file covers what mission #1 doesn't.

---

## Core philosophy — automation-first

**Vivek's time goes into reviewing, deciding, and direction-setting. Not setup, plumbing, or repetitive ritual.**

Any time an AI agent (Claude, Codex, Cowork, anything) is helping Vivek on this project and notices that a task could be automated — even partially — the agent **must surface that automation path explicitly**, and offer to build it. The default answer to "should I just do this manually?" is no. The default answer to "should this be a one-keystroke command?" is yes.

The rule, restated for agents reading this file in a future session:

> **If you see Vivek about to do something that could be a script, a shell function, an alias, a wrapper, a hook, a scheduled task, or an in-agent step — say so. Don't wait for him to ask. Suggest the automation, scope it, and offer to implement it.**

Concrete examples of what this means:

- He runs `git worktree add ...` by hand → suggest a `tools/start-ticket.sh` wrapper or a shell function.
- He activates conda every time he opens a terminal → suggest direnv or a per-worktree auto-activation hook.
- He says `next` in three terminals to start three parallel tickets → suggest a `tools/start-batch.sh TICKET-A TICKET-B TICKET-C` that opens three worktrees and pre-launches three CLI agents.
- He copies ticket markdown from chat to a file → already automated (`bash tools/file.sh`).
- He clicks through GitHub to merge a PR → can't be fully automated (review is human), but the "address review comments" step can be.
- He drags cards on the project board → mostly automated (ADR-010 / TICKET-M8 handles priority ordering on filing). Future automation: a script that re-balances Backlog when a CRITICAL is filed mid-week.

The rule does NOT mean: automate everything blindly. Each suggested automation lands as a ticket and goes through the normal evaluation (worth it? maintainable? testable?). The rule is about *surfacing the option*, not about implementing every possibility.

**When in doubt, automate.** Manual work that happens twice is a script that hasn't been written yet.

---

## The rubric — when does an AI-ecosystem experiment become a ticket?

An experimental integration becomes a real ticket when **both** are true:

1. **It teaches Vivek a concrete AI ecosystem skill** he doesn't have yet — a tool, a pattern, a protocol, a primitive.
2. **It improves the dashboard** in a way that would be worth doing even if the AI angle didn't exist. Either it makes an existing page better, replaces a manual task, or unlocks a feature that's been stuck on the roadmap.

If only #1 is true: write it up as a learning note. Don't ticket. The project stays clean.
If only #2 is true: ticket it normally. The AI angle isn't required.
If both are true: ticket it AND tag it `learning` so future review can find it.

---

## Glossary — what these things actually are

A short, plain-English reference so the rest of this file makes sense. Each entry is what the term means **today**; the ecosystem moves fast.

- **Agent** — an LLM driving a loop: read context → call tools (read files, run shells, hit APIs) → observe results → decide next step. Stops when the goal is reached or it's told to stop.
- **CLI agent** — an agent that runs in your terminal and works on your local files. Claude Code, OpenAI Codex CLI, Aider, Cursor CLI, Gemini CLI, Continue.dev. They differ in model defaults and UI; the core loop is the same.
- **Subagent** — an agent the *main* agent spawns to handle a focused task without polluting the main context window. Used for parallel research, isolated verification passes, or specialized work (e.g. a "security-reviewer" subagent). Each subagent is a fresh context; results come back as a single message.
- **Multi-agent / parallel agent workflow** — running multiple independent agents concurrently, each on its own ticket and branch. Compatible with this project's `one-ticket = one-branch` rule.
- **MCP (Model Context Protocol)** — Anthropic's open protocol for connecting agents to external tools and data sources. An MCP server exposes a tool/resource; an MCP-aware client (Claude Code, Cowork, etc.) discovers and uses it. Examples: an MCP server for Finnhub, FRED, a database, a SaaS API. The agent gets new capabilities without code in the agent itself.
- **Plugin / Skill (Anthropic)** — pre-built bundles of MCP servers + agent skills focused on a domain. Examples relevant here: `finance` (bigquery, ms365 connectors), `product-management` (Slack, Linear, Notion, Figma, etc.). Skills inside a plugin are invocable via the `Skill` tool; some plugins also bundle MCP connectors.
- **Skill (in the Claude Agent SDK sense)** — a packaged unit of agent behaviour: a description + a prompt + a tool/resource list. Triggered by description-match in the user's request.
- **Dynamic workflow** — a workflow where the next step is decided at runtime by an LLM or by tool output, not by a hardcoded script. Most agentic CLIs are dynamic; `tools/file.sh` is the opposite (static).
- **Embedded LLM feature** — calling an LLM from inside the application's own runtime (Python → Anthropic API), not from a CLI. Example: a "Generate analyst summary" button on the Company page that streams a Claude response into the Streamlit UI.
- **Cowork** — Anthropic's desktop mode for non-developer users to drive Claude across files, MCPs, plugins, and connected services. This file is being written from a Cowork session.
- **AGENTS.md convention** — the cross-CLI rulebook standard. Most modern CLI agents look for `AGENTS.md` (some also accept `CLAUDE.md`). This project's `AGENTS.md` is portable: Claude Code, Codex, Aider, and others all execute the same ritual when pointed at it.

---

## Backlog — AI ecosystem experiments worth doing on this project

Each item below is an unfiled candidate. When one becomes worth pursuing, draft it as a normal ticket. Items are not in priority order; they're grouped by ecosystem area.

### Multi-agent and parallel work

- **Parallel implementation with three CLI agents at once.** Run H1 + C2 + M8 simultaneously in three worktrees, each on a different CLI (Claude Code + Codex + Aider). Learn how each handles the same ritual. Outcome: three merged PRs, one comparison note. See ADR-011.
- **Subagent for verification.** Use Claude Code's `general-purpose` subagent as a Step-7 verifier: after the implementing agent passes `pytest && ruff && mypy && lint-imports`, spawn a subagent that re-reads the diff against the ticket's acceptance criteria and reports a pass/fail summary. Distinguishes "tests passed" from "spec actually met".
- **Subagent for code review on PRs.** The methodology's "Reviewing PRs" step is Vivek's. A subagent could pre-screen each PR and post a review comment before Vivek looks. Saves a round-trip when something obvious is wrong.
- **Multi-model panel for hard tickets.** For tickets touching the FIFO engine or tax pipeline (correctness-critical), run two CLI agents in parallel on the same ticket from different worktrees, compare diffs, merge the better one. Learn cross-model output variance on identical specs.

### MCP integrations

- **MCP server for Finnhub.** Replace direct `finnhub_adapter` HTTP calls with an MCP server. Same data, but the agent can also use the MCP at chat time for research on tickers in the portfolio. Learn MCP server authoring + dual-consumer pattern (Streamlit + agent).
- **MCP server for FRED (Federal Reserve Economic Data).** Macro indicators (US 10Y, EUR/USD, inflation) for a "Macro context" panel on the Overview page. Free API. Teaches MCP + Streamlit consumer + agent-shared data source.
- **MCP server for the portfolio's own data.** Expose `portfolio.json` and `tax_summary` via MCP. Then a chat session anywhere (claude.ai, Cowork, Codex) can ask "what's my current exposure" and get a real answer. Teaches MCP + read-only data exposure.
- **MCP server for ECB FX rates.** Once TICKET-C1 lands, the ECB adapter is a candidate to re-package as an MCP server reusable across other projects.

### Plugins and skills

- **Important context on the "Claude finance" plugin.** The `finance` plugin Vivek saw in Cowork is **accounting / audit / corporate-close focused** (`finance:journal-entry`, `finance:reconciliation`, `finance:sox-testing`, `finance:variance-analysis`, `finance:financial-statements`, `finance:audit-support`, `finance:close-management`). It is **not** investment-analysis or investment-banker-pitch shaped. For the investment-analyst angle Vivek mentioned (per-holding summaries on Company Deep Dive, thesis brief generation, etc.) the path is to **build a custom skill** that wraps an Anthropic API call with a sharp finance-analyst prompt + structured output schema. That's a perfectly reasonable learning track — skills are cheap to author, and the dashboard already has the company-data feed to plug in.
- **Try `product-management:competitive-brief` against a portfolio holding.** Generate a competitive analysis for one of your German companies (e.g. RHM.DE). See if the output is useful enough to embed into the Company Deep Dive page as an optional tab. Learn skill-trigger mechanics + skill output formatting.
- **Try `product-management:synthesize-research` on a thesis.** Feed it a year of news headlines for a ticker and see if the synthesized themes match your manual analysis. Tests skills on financial content.
- **Build a custom `analyst-brief` skill** that wraps a Claude API call with a structured prompt for "give me a 5-line investment-banker-style summary of {company} given {profile_data}". Skills are easy to author; this would teach skill authoring + Anthropic API integration in one ticket.

### Embedded LLM features (Anthropic API inside the dashboard)

- **"Generate analyst summary" button on Company Deep Dive.** Click → Claude API call with `CompanyData` + recent news → render a streamed 5-line investment-style brief. Learn: Anthropic API + streaming in Streamlit + prompt engineering for financial content + cost guardrails.
- **"Explain this number" tooltip on the Tax page.** Click any tax-summary value → Claude explains what it means in plain English given the user's profile and YTD activity. Learn: contextual prompting + treating LLM as a UI affordance, not a data source.
- **"What changed?" digest on Overview.** Daily summary of meaningful portfolio movements since yesterday, generated from the day's price deltas + news. Learn: scheduled LLM tasks + structured-output prompting.
- **Thesis ledger with LLM-assisted entry.** When you record a buy, an optional textarea: "Why are you buying this?" The LLM can suggest categories based on `CompanyData`. Replaces the dropped `behaviour.py` stub with something useful.

### Dynamic / agentic workflows in the dashboard

- **Auto-classify imported tickers via LLM.** When CSV import surfaces a new ISIN/ticker on the Mappings page, an LLM call suggests the `instrument_kind` based on the company profile (and writes a confidence score). User still confirms — no silent default — but the dropdown comes pre-filled with high confidence. Builds directly on TICKET-H1.
- **Auto-draft tickets from chat in the Cowork session.** Vivek says "the chart looks weird on small screens" → an agent skill drafts a TICKET-*.md, asks one clarifying question, files it. Reduces friction on the ticket-drafting step.

### Prompt engineering and evals

- **Build a prompt eval for the analyst-summary feature.** 10 reference companies, 10 expected output shapes. Run the prompt against each, score with another LLM. Tune. Teaches: evaluation-driven prompting.
- **A/B two prompt variants** for the "Explain this number" feature. Real usage telemetry (which output got a thumbs-up). Teaches: in-product LLM evaluation.

### Infra and observability

- **OpenTelemetry tracing for Anthropic API calls.** When the dashboard embeds LLM features, instrument the calls so latency, token use, and cost are visible in a real observability tool. Learn: production-grade LLM observability.
- **Per-feature cost budgets.** If a feature exceeds N tokens/day, disable it with a banner. Learn: cost controls as a product concern.

---

## How to add to this backlog

When you finish a Cowork session or a chat session where something AI-related came up, add a one-line bullet to the relevant section above. No formatting work — just capture the idea before it evaporates.

When ticketing one of these: copy the bullet into the ticket's `Notes` section so the implementation agent has the original framing. Mark the bullet here as `→ TICKET-XXX` so the backlog stays a live record.

---

## Cross-references

- Workflow for parallel implementation: `docs/DECISIONS/ADR-011-parallel-agent-workflow.md`
- Project rules (mission #1): `AGENTS.md`, `METHODOLOGY.md`, `ARCHITECTURE.md`
- Vivek's day-to-day reference: `docs/VIVEK.md`
- Past architectural decisions: `docs/DECISIONS/`
