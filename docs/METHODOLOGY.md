# METHODOLOGY.md

For the day-to-day Vivek-facing workflow, see `docs/VIVEK.md`. This file documents the why and the conventions.

How we work on this project. Read once, then refer back when in doubt.

---

## The three surfaces and their roles

| Surface | Role | Memory model |
|---|---|---|
| **Chat surface** (claude.ai, ChatGPT, Gemini, etc.) | Architectural thinking, ticket drafting, code review, design discussions | Per-chat; varies by provider |
| **Implementation agent** (Claude Code, GPT Codex, Gemini CLI, etc.) | Implementation, file edits, tests, commits, PRs | Per-session, reads `AGENTS.md` + module instruction files |
| **Git repo** | Source of truth for code AND project state | Perfect, persistent |

**Single source of truth: the git repo.** All AI surfaces read from `docs/` and propose changes. None holds state in its own memory.

---

## The token-efficiency contract

The previous build burned tokens on:
- Long context windows loaded with irrelevant files
- Exploratory coding ("let me try a few things")
- Scope creep within a session
- Re-explaining the architecture every chat

This build prevents all four:

1. **Per-module instruction files** keep context small. A 30-line file in `app/domain/fifo/CLAUDE.md` is worth more than a 500-line root file. (These are named `CLAUDE.md` by convention because Claude Code auto-loads them; other agents should read them when directed by `AGENTS.md`.)
2. **Tickets are written in chat first.** The implementation agent receives complete tickets and executes. No thinking happens in implementation sessions.
3. **One ticket per session.** When the ticket is done, the session ends. Next ticket = next session.
4. **`CONTEXT.md` is auto-available.** Chat in the Projects folder sees `docs/CONTEXT.md` automatically — no manual paste required.

---

## Model guidance

- **Default: use the standard/mid-tier model** for 95% of work — implementation, tests, refactors, doc updates.
- **Escalate to the strongest available model only for:**
  - Architectural design ("design the X flow with these constraints")
  - Hard debugging when the default model has tried twice and is going in circles
  - Cross-cutting refactors touching 8+ files
- **Use the lightest model** for trivia: renames, formatting, commit messages.

How you switch models depends on your CLI (e.g. Claude Code: `/model opus`; Codex: model flag; etc.).

---

## The ticket lifecycle

```
QUEUED → IN_PROGRESS → IN_REVIEW → MERGED
```

**Who sets each status:**

| Transition | Who does it | When |
|---|---|---|
| (chat draft) → QUEUED | Vivek (after chat drafting session) | Ticket file committed to `docs/TICKETS/`; GitHub issue created |
| QUEUED → IN_PROGRESS | Implementation agent | Step 5 of the ritual (branching) |
| IN_PROGRESS → IN_REVIEW | Implementation agent | Step 8b of the ritual (pre-push doc commit) |
| IN_REVIEW → MERGED | Implementation agent | Step 2 of the *next* ticket's ritual (housekeeping) |

**Note:** The agent does NOT update status to MERGED in the same session it opens the PR.
The MERGED transition happens at the start of the next session, after confirming via
`gh issue view <N> --json state -q .state` that the issue is CLOSED. This prevents the
failure mode where an agent writes to `main` after being told "I merged it."

## Ticket lifecycle states

- **QUEUED** — spec is complete and committed to `docs/TICKETS/`. GitHub issue exists with label `queued`. Waiting to be picked up. (Note: "queued" intentionally avoids "ready" because "ready" reads as an instruction; "queued" is a state.)
- **IN_PROGRESS** — branch open, work happening. Issue label `in-progress`.
- **IN_REVIEW** — PR open, awaiting Vivek's merge. Implicit (no label needed) when issue has a linked open PR.
- **MERGED** — landed on main. Implicit (issue is closed by `Closes #N` in PR body).

Edge cases:
- **CLOSED** — abandoned without merging. Issue closed manually with reason "not planned".
- **SUPERSEDED** — replaced by a later ticket. Label `superseded`, issue closed.

There is no DRAFT status. Tickets are drafted in chat; they only land in `docs/TICKETS/` once they are QUEUED.

---

## Priority levels

- **CRITICAL** — data correctness, security, or blocks active work. Drop everything.
- **HIGH** — core feature for the current Milestone.
- **MEDIUM** — polish or quality-of-life on shipped work.
- **LOW** — speculative, or contingent on a design decision not yet made.

---

## Milestones

Milestones group tickets by feature theme. A Milestone is "open" while it has unmerged tickets in it; "shipped" once all its tickets are MERGED. Milestones don't have deadlines — they're organizing buckets, not deliverable targets.

Current Milestones (mirrored as GitHub Milestones):
- **Foundation** (data model, FIFO, repository) — shipped
- **UI core** (shell, Live Overview, Manage Portfolio) — shipped
- **Tax engine** (engine, dashboard, simulator) — shipped
- **Charts & research** — shipped
- **Analytics & Risk** — shipped
- **UI polish** — shipped
- **Investment Panel** — pending design

Each ticket is assigned to exactly one Milestone via the GitHub issue's `milestone` field.

---

### A ticket file looks like this

```markdown
# TICKET-XXX — Short title

**Status:** QUEUED | IN_PROGRESS | IN_REVIEW | MERGED
**Priority:** CRITICAL | HIGH | MEDIUM | LOW
**Estimated session length:** 30 min | 1 hr | 2 hr
**Drafted by:** Vivek + AI (chat session YYYY-MM-DD)
**Implemented by:** <agent name> (session YYYY-MM-DD)

## Problem
What needs to happen and why.

## Acceptance criteria
- [ ] Specific, testable outcome 1
- [ ] Specific, testable outcome 2
- [ ] Tests pass: `pytest tests/unit/test_xxx.py`
- [ ] Lints pass: `ruff check . && mypy app/`

## Files likely touched
- `app/domain/...`
- `tests/unit/...`

## Out of scope
- Things explicitly NOT included (defends against scope creep)

## Test cases
1. Given X, when Y, then Z
2. Edge case: ...

## Notes
Any context the implementation agent needs that isn't in the architecture docs.
```

---

## Ticket-drafting checklist (chat surface)

Before a ticket moves from chat draft → QUEUED, walk this list. Each item is a real lesson from a session that went sideways.

- [ ] **Bench-test the spec against the real workflow.** Open the actual application or service the user will use, and trace the spec against what they actually see and have. *Lesson from TICKET-009 (2026-05-04):* the original form spec was internally consistent and demanded fields (native price, FX rate) that Scalable Capital's confirmations don't surface. The user couldn't fill those fields without inventing data, and the form happily accepted invented data. Three silent-corruption bugs followed. A 5-minute thought experiment of "what would I actually type into this form when looking at a Scalable confirmation?" would have caught the mismatch before any code was written.
- [ ] **No "documented approximation" placeholders.** If the spec says "use X as approximation; Y not supported in v1" that is a future bug. Approximations marked TODO have a way of staying. Either properly support what is needed, or leave it out entirely with no half-implementation. *Lesson from TICKET-008c (2026-05-04):* the seed CSV's `5631.T,...,USD,...,Japan Steel Works (use USD as approximation; KRW/JPY not supported in v1)` produced €4,000 of fake gain on Live Overview that the user only caught months later because the absolute number happened to be implausible.
- [ ] **No module names that collide with Python stdlib.** `html`, `email`, `string`, `io`, `time`, `json`, `logging`, `csv`, `tokenize`, `code` — any of these as a filename in your package will shadow the stdlib in unpredictable contexts. *Lesson from TICKET-008b (2026-05-04):* `app/ui/html.py` shadowed `html` in Streamlit's import context, breaking the bs4 → yfinance import chain on app startup.
- [ ] **No silent fallback to a default value without surfacing it.** If the form's "FX rate auto-fill" can quietly fall back to `1.0` when yfinance is offline, that is silent corruption waiting to happen. Every fallback path either (a) surfaces a banner the user must acknowledge, or (b) refuses to submit. *Lesson from TICKET-009 (2026-05-04).*
- [ ] **Test cases include at least one that would catch the real-world failure mode.** "Tests pass" is necessary, not sufficient — a test that asserts the form *constructs a Transaction* says nothing about whether the form *records the right values*. Aim for one acceptance test per spec rule that would observably fail if the rule were violated.
- [ ] **`tools/draft_ticket.sh` appends to `STATE.md` "Up next" automatically.** The agent reads "Up next" for the execution-time menu; if a ticket is filed but not in "Up next", it won't appear in the menu.
- [ ] **Re-check the parking lot.** If the new ticket resolves an item in `STATE.md`'s "Open questions / parking lot," remove or update that bullet in the same commit.

The first two items are about the *spec*; the last three are about the *implementation*. Both can be checked at draft time. None of them require running code.

---

## The chat handoff protocol

When Claude Chat (or any chat surface) drafts a ticket, the final response **must** be structured as a **Standard Handoff Bundle**:

1. **Ticket file content** — delivered as a `.md` file (not pasted inline in chat), ready to write to `docs/TICKETS/TICKET-<N>-<slug>.md`.
2. **Milestone assignment** — which Milestone the ticket belongs to (for GitHub milestone tagging).
3. **ADR file content** — if any architectural decision was made, also as a `.md` file for `docs/DECISIONS/`.
4. **One shell block** invoking `tools/draft_ticket.sh` with the spec on stdin.

**If Vivek runs the shell block, the entire repo state update is one paste.** He never edits `STATE.md` or ticket files by hand. The script:
- Writes the ticket file to `docs/TICKETS/`
- Appends to `STATE.md` "Up next" section
- Creates the GitHub issue with labels matching priority + `queued`
- Commits with `docs: draft TICKET-<N> <title>`
- Pushes to main

The spec format piped to `tools/draft_ticket.sh`:

```
ID: TICKET-<NNN>
TITLE: <one-line title>
MILESTONE: <name, must match an existing Milestone>
PRIORITY: CRITICAL | HIGH | MEDIUM | LOW
ESTIMATE: <free text, e.g. "1 – 1.5 hr">
---
<full markdown ticket body, including the Status/Priority/etc. header lines>
```

---

## Ticket drafting in chat — the verification protocol

### Required reads

Before drafting any ticket, chat must have access to `docs/CONTEXT.md` (auto-generated, current with main). `STATE.md` alone is insufficient — it contains project state but not code signatures or the current UI surface. `CONTEXT.md` provides both.

`CONTEXT.md` is committed to main on every merge (via the `update-context.yml` GitHub Action) and is included in the Projects folder automatically. No manual paste required.

### Mandatory verification before drafting

Chat must perform these four checks before writing a ticket spec:

1. **Locate the affected code in CONTEXT.md.** If the ticket touches `function_name` or `ClassName`, find it in the `Public interfaces` section and confirm its current signature and field set. If chat cannot locate what it is about to modify, ask Vivek before drafting — do not invent a signature.

2. **For UI tickets, require a screenshot or page description from Vivek.** CONTEXT.md's `UI surface` section lists page filenames and docstrings, not what the rendered page actually looks like. Chat must say: *"Please share a screenshot or describe what's currently on the [page] page before I draft this."*

3. **State assumptions explicitly in the ticket's Notes section.** Every assumption that could not be verified from CONTEXT.md gets written down. Example: *"Assumes `OpenLot.split()` does not exist and will be created. Confirm before implementing."* This gives the agent a chance to catch a wrong assumption before writing code, rather than discovering the mismatch mid-implementation.

4. **Check for conflicts.** Scan `Open issues` and `Recent merges` in CONTEXT.md. If something equivalent is already in flight or was just merged, flag it to Vivek before drafting.

### The agent's recourse when an assumption is wrong

If the agent encounters an assumption in a ticket's Notes section that turns out to be wrong — for example, a function chat assumed did not exist actually does, with a different signature — the agent stops at Step 7 (gate check) and reports the discrepancy. This is the existing Stop Conditions rule applied to spec assumptions. The correct response is a targeted fix in the same session, not heroic rewriting: if the scope is small, fix it; if it requires architectural reconsideration, open a follow-up ticket.

Anti-pattern: ❌ Proceeding past a wrong assumption on the theory that "the tests will catch it." They will not, if the wrong assumption propagated into the tests themselves.

---

## Reviewing PRs

When the implementation agent opens a PR, Vivek's review walks four checks:

1. **Read the ticket file.** Re-anchor on what the spec asked for. If memory of the spec disagrees with what the file says, the file wins — the agent worked from the file.
2. **Read the diff.** Map each acceptance-criterion checkbox to a concrete change. Unchecked criteria → request changes.
3. **Run the app.** Not just `pytest`. Open Streamlit, click through the relevant page, observe the working state. *"Verification" means observed working behavior in the running app, not just tests passing.* Tests catching what they were written to catch is necessary, not sufficient. *Lesson from TICKET-008b (2026-05-04):* the positions table HTML leak passed every existing test — there was no test for "does the rendered output start with `<` instead of literal HTML text" because nobody thought to write one.
4. **Screenshot before/after when the change is user-visible.** Drop the screenshots in the PR description. This is the cheapest possible "I observed it working" record. For a future AI session opening the PR weeks later, the screenshot is worth more than a paragraph of description.

If all four pass, merge. If any fail, comment on the PR with the specific finding and let the agent address it in the next session.

---

## Vivek's role in the implementation loop

Vivek does **not** write code. Vivek does:

1. **Picks the next ticket** from the execution-time menu (says `next` in Claude Code).
2. **Tells the implementation agent:** "Implement TICKET-XXX." That's the entire instruction.
3. **Reviews the PR** when the agent opens it. Reads the diff, reads the ticket, reads the test results.
4. **Merges or requests changes.** If changes needed, comments on the PR — the agent picks up the comments in the next session.
5. **Drafts ADRs and tickets in the chat surface** before implementation.

If Vivek finds himself running `pytest` or editing code directly, that's a signal something is wrong with the workflow — fix the workflow, don't take over from the agent.

---

## The session-end ritual (the implementation agent does this every time)

The complete ritual is in `AGENTS.md`. Summary:

1. Run `pytest && ruff check . && mypy app/ && lint-imports`. If any fail, **stop**.
2. Commit with conventional commits.
3. Update `docs/STATE.md` if any ticket status changed (In progress, In review sections).
4. Update the ticket file's `Status:` line.
5. Commit the doc updates (step 3–4) as a separate `docs:` commit **on the branch, before pushing**.
6. Push branch.
7. Open PR with `gh pr create --base main` — body must include `Closes #<N>`.
8. Print PR URL for Vivek.
9. **Stop. Do not do anything else.**

---

## When something architectural changes

If a chat session produces a real architectural decision (e.g. "we're switching from JSON to SQLite"), the chat ends with three deliverables:

1. **Updated `STATE.md`** (in a code block ready to copy)
2. **A new ADR file** in `docs/DECISIONS/` (in a code block)
3. **A new or updated ticket** if implementation work follows

Vivek commits all three in one commit: `docs: ADR-XXX <title>`. Or — better — Vivek opens an implementation session and says "create ADR-XXX from the chat output below" and pastes the ADR. The agent commits and opens a PR.

---

## Anti-patterns we've banned

- ❌ "While I'm here, let me also fix..." → New ticket.
- ❌ "Let me try a few approaches and see what works." → Design first in chat, then implement.
- ❌ "I'll add a quick test later." → No test, no commit.
- ❌ "This file is fine, just trust me." → Run the linter.
- ❌ Loading the whole repo into the agent's context → Per-module instruction files.
- ❌ Editing `docs/ARCHITECTURE.md` mid-implementation → Architecture changes are their own ticket.
- ❌ Vivek writing code directly → Fix the workflow instead.
- ❌ The agent merging its own PRs → Vivek merges.
- ❌ The agent pushing to main → Branch protection rejects this; if it doesn't, branch protection is broken.
- ❌ Open-ended fix instructions like "reconcile X and Y" or "consolidate the implementation" → Scope-expansion verbs license agents to rewrite far beyond the actual bug. Bug-fix tickets get explicit "Files NOT to modify" sections. *Lesson from TICKET-008b debugging (2026-05-04):* "fix the problem" produced a sprawling consolidated diff; the targeted fix was 30 lines.
- ❌ Documented approximations in seed data ("use X as proxy; Y not supported v1") → File a real ticket or omit. The TODO will not get done before it bites.
- ❌ Silent fallbacks to default values when an upstream lookup fails → Either show the user, or refuse to proceed. Never both fail and continue.
- ❌ Doc updates after the PR is opened → Doc updates are on the branch before push. Never after.
- ❌ Writing to `main` after Vivek says "merged" → The session is over. MERGED status is set in the next session's Step 2.
- ❌ Drafting new QUEUED tickets without appending to `STATE.md`'s "Up next" section → `tools/draft_ticket.sh` does this automatically. If you draft a ticket file manually, you must also update "Up next". Stale pointers cause the wrong ticket to appear in the menu.
