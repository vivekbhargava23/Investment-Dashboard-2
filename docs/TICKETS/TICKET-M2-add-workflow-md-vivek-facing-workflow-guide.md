# TICKET-M2 — Add WORKFLOW.md (Vivek-facing workflow guide)

**Status:** IN_PROGRESS
**Priority:** HIGH
**Estimated session length:** 45 – 60 min
**Drafted by:** Vivek + Claude (chat 2026-05-10, immediately post-M1 merge)
**Implemented by:** <agent name> (session YYYY-MM-DD)

## Problem

TICKET-M1 just landed: vocabulary unified (QUEUED/IN_PROGRESS/IN_REVIEW/MERGED, CRITICAL/HIGH/MEDIUM/LOW, Milestone, Step), GitHub Issues integration live, helper scripts in `tools/`, the chat handoff protocol documented in METHODOLOGY.md.

What's still missing: a **single document Vivek can read to know exactly what he does end-to-end**. Today's docs answer adjacent questions:

- `AGENTS.md` — what the implementation agent does (not Vivek's job)
- `METHODOLOGY.md` — why we do it this way + conventions (reference, not procedure)
- `ARCHITECTURE.md` — code rules (irrelevant to Vivek's daily flow)
- `PROJECT_STATE.md` — current state (paste material, not instructions)

There is no document that, in one read, tells Vivek (or future-Vivek on a new laptop, or any new chat surface helping Vivek) *what his four touchpoints are and what each one looks like*. The chat handoff protocol section in METHODOLOGY.md is close but written from the chat surface's perspective, not Vivek's.

This ticket adds `docs/WORKFLOW.md`: a Vivek-facing, second-person, recipe-style guide.

## Acceptance criteria

### A. New file: `docs/WORKFLOW.md`

The file contains these sections, in this order:

- [ ] **Top-of-file orientation** — one paragraph stating that this file is *for Vivek*, written in second person, and answers "what do I do day-to-day on this project." Other docs (AGENTS.md, METHODOLOGY.md, ARCHITECTURE.md) referenced briefly as the right targets for adjacent questions.

- [ ] **Section 1 — The four touchpoints**
  Headline summary of Vivek's involvement, in this exact form:
  1. Chat with Claude (or another chat surface) to draft a ticket
  2. Paste one shell block into a terminal
  3. Open Claude Code (or another implementation agent) and say `next`
  4. Review the PR and merge
  Followed by a one-line statement: "Everything else is automated."

- [ ] **Section 2 — Vocabulary cheatsheet**
  Single table covering: lifecycle states (QUEUED/IN_PROGRESS/IN_REVIEW/MERGED + edge cases CLOSED/SUPERSEDED), priorities (CRITICAL/HIGH/MEDIUM/LOW with one-line definitions), Milestone (what it means + current list mirrored from BACKLOG.md), Step (1–9, in AGENTS.md, not Vivek's concern but defined so the term doesn't surprise). Cross-references METHODOLOGY.md for the canonical definitions.

- [ ] **Section 3 — Drafting a ticket (the chat session)**
  What Vivek does: open chat surface, paste current `PROJECT_STATE.md` + last 3 entries of `SESSION_LOG.md`, describe the change. What Vivek receives at the end: (a) a downloadable `.md` ticket file, (b) one shell block. Notes that the chat surface follows the chat handoff protocol in METHODOLOGY.md — Vivek doesn't need to police this, just expect it.

- [ ] **Section 4 — Filing a ticket (the paste)**
  Step-by-step: download the `.md`, place it where the shell block expects (or trust the script to write it), paste the shell block, hit enter. One paragraph explaining what `tools/draft_ticket.sh` does internally (writes ticket file, updates BACKLOG.md row, creates GitHub issue with `queued` + priority labels, commits, pushes). One sentence noting that if the script fails, Vivek pastes the error into the chat — he doesn't debug.

- [ ] **Section 5 — Implementing a ticket**
  Vivek's prompt is literally `next` (or `implement TICKET-XXX` if he wants to override the queue). Notes that Claude Code reads `gh issue list --label next-up --state open` to resolve `next`. What Vivek sees during the session: file edits, test runs, lint runs, commits, push, PR URL printed. What Vivek does during the session: nothing. Stop conditions covered: if the agent says "stopping — `pytest` failed," Vivek does not coach it through a fix; he opens a new chat to discuss.

- [ ] **Section 6 — Reviewing the PR**
  The four-check review condensed for Vivek's daily use:
  1. Re-read the ticket file (anchor on what was asked)
  2. Read the diff against the acceptance criteria
  3. Run the Streamlit app and click through the affected page
  4. Screenshot before/after if user-visible; paste in PR description
  Cross-reference: full version in METHODOLOGY.md "Reviewing PRs" section.
  Merge if all pass. Comment if not — the agent picks up review comments in the next session.

- [ ] **Section 7 — Edge cases**
  Brief recipes (1–3 lines each):
  - **Agent stops mid-ritual**: read the stop reason; if it's a real bug in main, file a hotfix ticket
  - **`pytest` fails on the agent's branch**: agent will not commit; it stops and reports. Vivek does not touch the branch
  - **PR needs changes**: comment on the PR, then say `address PR review comments on TICKET-XXX` in a new Claude Code session
  - **You find a bug after merge**: file a new ticket with `Files NOT to modify` if it's a tight fix
  - **Stale state in PROJECT_STATE.md**: ignore — Step 2 of the next session cleans it up
  - **You want to start a new chat session**: paste current `PROJECT_STATE.md` + last 3 entries of `SESSION_LOG.md` + your question

- [ ] **Section 8 — What changed in TICKET-M1 (transitional)**
  Short section noting: vocabulary migration done, GitHub Issues integrated, helper scripts available, chat handoff protocol formalized. One sentence: "This section can be deleted in 30–60 days once the new flow is fully internalized — see TICKET-MXX-cleanup-workflow when filing." Acts as a self-cleaning footnote.

- [ ] **Footer cross-reference table** — links to AGENTS.md, METHODOLOGY.md, ARCHITECTURE.md, PROJECT_STATE.md, BACKLOG.md with one-line descriptions of what each covers, so Vivek knows where to go for adjacent questions.

### B. README.md update

- [ ] Repo `README.md` gets a new section near the top: **"Working on this project"** with one paragraph and a link: *"If you're Vivek (or any future maintainer), start with `docs/WORKFLOW.md`. It walks through the four touchpoints end-to-end."*
- [ ] If README.md does not exist or is sparse, the agent does NOT expand it beyond this addition. README polish is out of scope.

### C. METHODOLOGY.md cross-link

- [ ] Add one line at the top of METHODOLOGY.md: *"For the day-to-day Vivek-facing workflow, see `docs/WORKFLOW.md`. This file documents the why and the conventions."*

### D. AGENTS.md cross-link

- [ ] Add one line near the top of AGENTS.md (right after the `Required reading` section): *"This file is for the implementation agent. Vivek's day-to-day workflow lives in `docs/WORKFLOW.md` and is not your concern."*
  Reasoning: prevents an agent from "helpfully" reading and acting on Vivek's workflow doc.

### E. Verification

- [ ] `pytest && ruff check . && mypy app/ && lint-imports` — all pass (this is a docs-only ticket, all checks should be untouched).
- [ ] Open `docs/WORKFLOW.md` in a markdown previewer; visually confirm all 8 sections are present and render cleanly (no broken table syntax, no dangling cross-references).
- [ ] Click every cross-reference link (`AGENTS.md`, `METHODOLOGY.md`, `ARCHITECTURE.md`, `PROJECT_STATE.md`, `BACKLOG.md`, `SESSION_LOG.md`) — all must resolve to existing files in the repo.
- [ ] Confirm the vocabulary cheatsheet matches METHODOLOGY.md exactly. Specifically: lifecycle states, priority words, Milestone definition. Any drift between the two files is a bug.

## Files likely touched

### New files
- `docs/WORKFLOW.md`

### Edited
- `README.md` (one paragraph + link)
- `docs/METHODOLOGY.md` (one cross-link line at top)
- `docs/AGENTS.md` (one cross-link line near top)

### NOT touched
- `app/**`
- `tests/**`
- `docs/TICKETS/**` (no historical ticket migration)
- `docs/ARCHITECTURE.md`
- `docs/PROJECT_STATE.md` (the `Last updated` line will tick over via Step 8b — that's normal, not part of this ticket's scope)
- `docs/DECISIONS/**`

## Out of scope

- Rewriting METHODOLOGY.md or AGENTS.md beyond the single cross-link line each.
- Creating a CONTRIBUTING.md or similar — this is a single-developer project.
- Diagrams, flowcharts, GIF screencasts. Plain markdown only.
- Translating WORKFLOW.md into a tutorial / first-time-setup guide. It assumes the repo is cloned, dependencies are installed, `gh` is authenticated. If any of those are wrong, that's a separate ticket.
- Adding a "What changed in M2" section to WORKFLOW.md itself — Section 8 covers M1 changes only, because M2's only change is *adding this file*.
- Editing the chat handoff protocol in METHODOLOGY.md. M1 already established it.

## Test cases

This is a documentation ticket; "tests" are content-level verifications.

1. **Read-through test**: A reader who has never seen the project before should be able to read `docs/WORKFLOW.md` start to finish in under 10 minutes and understand exactly what Vivek does. The agent does this read-through itself before opening the PR; if any section feels confusing on re-read, fix it.
2. **Vocabulary consistency**: `grep -n "READY\|DRAFT\|P0\|P1\|P2\|P3\|Phase [0-9]" docs/WORKFLOW.md` — output must be empty. Any leak from old vocabulary is a bug.
3. **Cross-reference validity**: every `\`docs/...md\`` reference in WORKFLOW.md must point to a file that exists in the repo. Verify with `grep -oE 'docs/[A-Za-z_/-]+\.md' docs/WORKFLOW.md | sort -u | xargs -I{} test -f {} && echo OK || echo MISSING:{}`.
4. **Mirror-check with METHODOLOGY.md**: open WORKFLOW.md and METHODOLOGY.md side by side. The lifecycle diagram, priority levels, and Milestone definitions must match. Differences are bugs.

## Notes

### Why this is HIGH priority

It's the missing piece that makes M1's work legible to Vivek. Without it, the new system works but Vivek has to remember it from chat conversations. With it, the system is self-documenting.

### Tone guide for the agent

Write WORKFLOW.md in clear second person ("You paste the shell block. The script writes the ticket file..."). Avoid:
- Passive voice ("the shell block is pasted")
- Aspirational framing ("ideally you should...")
- Marketing language ("our streamlined workflow")
- Excessive hedging ("you might want to consider perhaps...")

Concrete, declarative, recipe-style. Closer to a Unix man page than a blog post.

### A possible failure mode to avoid

When writing Section 7 (edge cases), do NOT invent edge cases that haven't actually happened. Stick to the ones listed in acceptance criterion A. Speculative edge cases bloat the file and make it harder to read. If a real edge case emerges later, it gets added in a follow-up ticket.

### Section 8 lifespan

Section 8 ("What changed in TICKET-M1") is intentionally transitional. It exists for the first 30–60 days while M1 is fresh, then gets removed by a future cleanup ticket. The agent does NOT need to file that cleanup ticket as part of M2 — just leave the section with the self-deletion note included.

### First ticket via `tools/draft_ticket.sh`

This ticket is the first one Vivek will file via the new `tools/draft_ticket.sh` script. If the script has any rough edges that surface during filing, those are fixed in a follow-up ticket (TICKET-M3 or similar), NOT during M2 implementation. M2 stays scoped to writing WORKFLOW.md.
