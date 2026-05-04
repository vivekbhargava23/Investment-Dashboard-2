# METHODOLOGY.md

How we work on this project. Read once, then refer back when in doubt.

---

## The three surfaces and their roles

| Surface | Role | Memory model |
|---|---|---|
| **Claude Chat** (claude.ai) | Architectural thinking, ticket drafting, code review, design discussions | Per-chat + memory + past chats search |
| **Claude Code** (terminal) | Implementation, file edits, tests, commits, PRs | Per-session, reads `CLAUDE.md` files |
| **Git repo** | Source of truth for code AND project state | Perfect, persistent |

**Single source of truth: the git repo.** Both AI surfaces read from `docs/` and propose changes. Neither holds state in its own memory.

---

## The token-efficiency contract

The previous build burned tokens on:
- Long context windows loaded with irrelevant files
- Exploratory coding ("let me try a few things")
- Scope creep within a session
- Re-explaining the architecture every chat

This build prevents all four:

1. **Per-module `CLAUDE.md` files** keep context small. A 30-line file in `app/domain/fifo/CLAUDE.md` is worth more than a 500-line root file.
2. **Tickets are written in chat first.** Claude Code receives complete tickets and executes. No thinking happens in Claude Code sessions.
3. **One ticket per session.** When the ticket is done, the session ends. Next ticket = next session.
4. **`PROJECT_STATE.md` is paste-able.** No re-explaining anything when starting a new chat.

---

## Model choice in Claude Code

- **Default: Claude Sonnet 4.6.** Use for 95% of work — implementation, tests, refactors, doc updates.
- **Switch to Claude Opus 4.7 only for:**
  - Architectural design ("design the X flow with these constraints")
  - Hard debugging when Sonnet has tried twice and is going in circles
  - Cross-cutting refactors touching 8+ files
- **Claude Haiku 4.5** for trivia: renames, formatting, commit messages.

Switch in Claude Code with `/model opus`, `/model sonnet`, `/model haiku`.

---

## The ticket lifecycle

```
DRAFT (Claude Chat) → READY (file in TICKETS/) → IN_PROGRESS (Claude Code) →
IN_REVIEW (PR open) → MERGED (Vivek merges) → SHIPPED (in main, ticket file deleted or archived)
```

### A ticket file looks like this

```markdown
# TICKET-XXX — Short title

**Status:** READY | IN_PROGRESS | IN_REVIEW | MERGED
**Priority:** P0 | P1 | P2
**Estimated session length:** 30 min | 1 hr | 2 hr
**Drafted by:** Vivek + Claude (chat session YYYY-MM-DD)
**Implemented by:** Claude Code (session YYYY-MM-DD)

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
Any context Claude Code needs that isn't in the architecture docs.
```

---

## Ticket-drafting checklist (Claude Chat)

Before a ticket moves from DRAFT → READY, walk this list. Each item is a real lesson from a session that went sideways.

- [ ] **Bench-test the spec against the real workflow.** Open the actual application or service the user will use, and trace the spec against what they actually see and have. *Lesson from TICKET-009 (2026-05-04):* the original form spec was internally consistent and demanded fields (native price, FX rate) that Scalable Capital's confirmations don't surface. The user couldn't fill those fields without inventing data, and the form happily accepted invented data. Three silent-corruption bugs followed. A 5-minute thought experiment of "what would I actually type into this form when looking at a Scalable confirmation?" would have caught the mismatch before any code was written.
- [ ] **No "documented approximation" placeholders.** If the spec says "use X as approximation; Y not supported in v1" that is a future bug. Approximations marked TODO have a way of staying. Either properly support what is needed, or leave it out entirely with no half-implementation. *Lesson from TICKET-008c (2026-05-04):* the seed CSV's `5631.T,...,USD,...,Japan Steel Works (use USD as approximation; KRW/JPY not supported in v1)` produced €4,000 of fake gain on Live Overview that the user only caught months later because the absolute number happened to be implausible.
- [ ] **No module names that collide with Python stdlib.** `html`, `email`, `string`, `io`, `time`, `json`, `logging`, `csv`, `tokenize`, `code` — any of these as a filename in your package will shadow the stdlib in unpredictable contexts. *Lesson from TICKET-008b (2026-05-04):* `app/ui/html.py` shadowed `html` in Streamlit's import context, breaking the bs4 → yfinance import chain on app startup.
- [ ] **No silent fallback to a default value without surfacing it.** If the form's "FX rate auto-fill" can quietly fall back to `1.0` when yfinance is offline, that is silent corruption waiting to happen. Every fallback path either (a) surfaces a banner the user must acknowledge, or (b) refuses to submit. *Lesson from TICKET-009 (2026-05-04).*
- [ ] **Test cases include at least one that would catch the real-world failure mode.** "Tests pass" is necessary, not sufficient — a test that asserts the form *constructs a Transaction* says nothing about whether the form *records the right values*. Aim for one acceptance test per spec rule that would observably fail if the rule were violated.

The first two items are about the *spec*; the last three are about the *implementation*. Both can be checked at draft time. None of them require running code.

---

## Reviewing PRs

When Claude Code opens a PR, Vivek's review walks four checks:

1. **Read the ticket file.** Re-anchor on what the spec asked for. If memory of the spec disagrees with what the file says, the file wins — Claude Code worked from the file.
2. **Read the diff.** Map each acceptance-criterion checkbox to a concrete change. Unchecked criteria → request changes.
3. **Run the app.** Not just `pytest`. Open Streamlit, click through the relevant page, observe the working state. *"Verification" means observed working behavior in the running app, not just tests passing.* Tests catching what they were written to catch is necessary, not sufficient. *Lesson from TICKET-008b (2026-05-04):* the positions table HTML leak passed every existing test — there was no test for "does the rendered output start with `<` instead of literal HTML text" because nobody thought to write one.
4. **Screenshot before/after when the change is user-visible.** Drop the screenshots in the PR description. This is the cheapest possible "I observed it working" record. For a future AI session opening the PR weeks later, the screenshot is worth more than a paragraph of description.

If all four pass, merge. If any fail, comment on the PR with the specific finding and let Claude Code address it in the next session.

---

## Vivek's role in the implementation loop

Vivek does **not** write code. Vivek does:

1. **Picks the next ticket** from `BACKLOG.md`.
2. **Tells Claude Code:** "Implement TICKET-XXX." That's the entire instruction.
3. **Reviews the PR** when Claude Code opens it. Reads the diff, reads the ticket, reads the test results.
4. **Merges or requests changes.** If changes needed, comments on the PR — Claude Code picks up the comments in the next session.
5. **Drafts ADRs and tickets in Claude Chat** before implementation.

If Vivek finds himself running `pytest` or editing code directly, that's a signal something is wrong with the workflow — fix the workflow, don't take over from Claude Code.

---

## The session-end ritual (Claude Code does this every time)

The complete ritual is in the root `CLAUDE.md`. Summary:

1. Run `pytest && ruff check . && mypy app/ && lint-imports`. If any fail, **stop**.
2. Commit with conventional commits.
3. Append to `docs/SESSION_LOG.md` (template below).
4. Update `docs/PROJECT_STATE.md` if any ticket status changed.
5. Update the ticket file's `Status:` line.
6. Push branch.
7. Open PR with `gh pr create --fill --base main`.
8. Print PR URL for Vivek.
9. Stop.

### SESSION_LOG.md entry template

```markdown
## YYYY-MM-DD HH:MM — TICKET-XXX

**Surface:** Claude Code
**Model:** sonnet-4.6 | opus-4.7 | haiku-4.5
**Duration:** ~XX min
**Branch:** ticket-XXX-short-name
**PR:** https://github.com/<user>/<repo>/pull/N
**Status at session end:** IN_REVIEW

### What got done
- Bullet of concrete change 1
- Bullet of concrete change 2

### Files touched
- `app/domain/fifo.py` — added replay-on-edit logic
- `tests/unit/test_fifo.py` — added 4 new test cases

### Tests
48 passing → 52 passing (4 new)

### Decisions made during the session
- Chose to raise `LotEditConflict` instead of silent recompute — see ADR-XXX
- (Or: "no architectural decisions made")

### Out-of-scope items noticed
- Open ticket: TICKET-YYY (noticed but didn't fix)

### Tokens used (rough)
~XXk
```

---

## Starting a new Claude Chat (the handoff)

Paste this into the new chat:

```
I'm continuing work on my investment dashboard. Here is the current state:

[paste contents of docs/PROJECT_STATE.md]

And the last 3 session log entries:

[paste last 3 entries from docs/SESSION_LOG.md]

[Then your actual question/request]
```

That's it. The new Claude chat now has full context.

---

## When something architectural changes

If a Claude Chat session produces a real architectural decision (e.g. "we're switching from JSON to SQLite"), the chat ends with three deliverables:

1. **Updated `PROJECT_STATE.md`** (in a code block ready to copy)
2. **A new ADR file** in `docs/DECISIONS/` (in a code block)
3. **A new or updated ticket** if implementation work follows

Vivek commits all three in one commit: `docs: ADR-XXX <title>`. Or — better — Vivek opens a Claude Code session and says "create ADR-XXX from the chat output below" and pastes the ADR. Claude Code commits and opens a PR.

---

## Anti-patterns we've banned

- ❌ "While I'm here, let me also fix..." → New ticket.
- ❌ "Let me try a few approaches and see what works." → Design first in chat, then implement.
- ❌ "I'll add a quick test later." → No test, no commit.
- ❌ "This file is fine, just trust me." → Run the linter.
- ❌ Loading the whole repo into Claude Code's context → Per-module `CLAUDE.md`.
- ❌ Editing `docs/ARCHITECTURE.md` mid-implementation → Architecture changes are their own ticket.
- ❌ Vivek writing code directly → Fix the workflow instead.
- ❌ Claude Code merging its own PRs → Vivek merges.
- ❌ Claude Code pushing to main → Branch protection rejects this; if it doesn't, branch protection is broken.
- ❌ Open-ended fix instructions like "reconcile X and Y" or "consolidate the implementation" → Scope-expansion verbs license agents to rewrite far beyond the actual bug. Bug-fix tickets get explicit "Files NOT to modify" sections. *Lesson from TICKET-008b debugging (2026-05-04):* "fix the problem" produced a sprawling consolidated diff; the targeted fix was 30 lines.
- ❌ Documented approximations in seed data ("use X as proxy; Y not supported v1") → File a real ticket or omit. The TODO will not get done before it bites.
- ❌ Silent fallbacks to default values when an upstream lookup fails → Either show the user, or refuse to proceed. Never both fail and continue.
