# AGENTS.md — Investment Dashboard

> **You are the implementation agent working on Vivek's investment dashboard.**
> Vivek **does not write code, run tests, commit, push, or open PRs**. You do all of that.
> Vivek **reviews PRs and merges them**. That is his only role in the implementation loop.
>
> **READ EVERY INSTRUCTION FILE IN FULL — every line, top to bottom, to EOF.** Do not read
> the first N lines and proceed. Do not skim, sample, or assume the rest. If your
> file-reading tool returns a truncated view, page through with offsets until you reach EOF
> before you act. Partial reads of this file, required files, ticket files, or module
> `CLAUDE.md` files are a stop condition.

This file is for the implementation agent. Vivek's day-to-day workflow lives in
`docs/VIVEK.md` and is not your concern.

## Local Environment

`tools/*.sh` run on stock macOS bash 3.2 + BSD userland. You need `git`, `gh`
(authenticated), `jq`, and the project Python/conda setup on PATH. See
`tools/README.md` for the toolchain reference.

## Required Reading

Read these every session, in this order, before implementation work:

1. `docs/METHODOLOGY.md` — how we work
2. `docs/ARCHITECTURE.md` — architecture rules, non-negotiable
3. The ticket file for the ticket being implemented

For current repo state, read the code and query the GitHub Projects board directly.
There is no generated state snapshot. `docs/CONTEXT.md` and its workflow were retired
on 2026-06-03.

If the work touches a specific module, also read that module's `CLAUDE.md` file in full
before editing. These files contain module-specific constraints.

## Division Of Labor

| Vivek does | The implementation agent does |
|---|---|
| Picks the next ticket | Implements the ticket |
| Reviews the PR | Writes the code |
| Merges the PR | Writes the tests |
| Drafts ADRs in chat | Runs tests and linters |
| Approves architectural changes | Commits with conventional commit messages |
| Drags cards on the project board | Pushes the branch |
| | Opens the PR via `gh pr create` |
| | Moves board item Status values via scripts |

## Non-Negotiable Rules

1. **One coherent implementation = one branch = one PR.** A PR may close several
   tightly coupled tickets via multiple `Closes #N` lines, but never bundle unrelated work.
2. **Tests must stay green.** If any gate check fails, stop and report.
3. **Domain layer has zero I/O imports.** No `requests`, file I/O, or `streamlit` in
   `app/domain/`. If you think you need one, open a discussion ticket.
4. **Conventional commits only.** Use `feat:`, `fix:`, `refactor:`, `test:`, `docs:`,
   or `chore:`. One logical change per commit.
5. **Never push to `main` directly.** If you want to push to `main`, stop.
6. **Never merge your own PRs.** Vivek merges.
7. **Implement comprehensively.** If the same change recurs in multiple places, update
   every occurrence required by the ticket. No partial application.
8. **No runtime scope creep.** "While I'm here" work becomes a new ticket.

## Model Selection

Every ticket header carries:

`**Recommended model:** Opus | Sonnet | Haiku — <reason>`

Choose by capability. When a ticket sits between tiers, pick the higher tier.

| Model | Use for |
|---|---|
| **Haiku 4.5** | Mechanical, low-judgment work: doc edits, dead-code deletion, pure renames |
| **Sonnet 4.6** | Well-scoped changes in one area with clear tests and low blast radius |
| **Opus 4.6** | Cross-cutting or high-risk work: money/tax/FIFO, cache correctness, concurrency, data migrations |

`tools/next.sh` surfaces the recommendation in brackets so Vivek can choose the right
model before starting.

## Workflow Scripts

The repetitive ritual lives in these entry points:

- `bash tools/next.sh` — prints the ranked Ready/Backlog menu, including model,
  priority, dependency blockers, and unblock score.
- `bash tools/start_ticket.sh TICKET-XXX` — reconciles closed `In review` items to
  `Done`, verifies a clean `main`, pulls, creates/reuses the feature branch, marks the
  ticket file `IN_PROGRESS`, and moves the board item to `In progress`. If a blocked
  ticket is explicitly requested, it warns and continues.
- `bash tools/gate.sh` — activates `investment-dashboard` and runs `pytest`,
  `ruff check .`, `mypy app/`, and `lint-imports`, stopping at the first failure.
- `bash tools/finish_ticket.sh TICKET-XXX` — reruns the gate, pushes the current branch,
  moves the board item to `In review`, and opens the PR with `Closes #N` in the body.
- `bash tools/doctor.sh` — non-mutating preflight diagnostics for local state, retired
  files, board sanity, and dependency blockers.

Do not inline the old `gh`/`jq` board-management blocks. If a script fails, report the
exact failure instead of hand-editing the board.

## Complete Ticket Ritual

When Vivek says "implement TICKET-XXX" (or "do", "work on", "start"), that is a
complete instruction. Do not ask for confirmation between steps.

1. **Resolve the ticket.** If Vivek said `next` or `implement next ticket`, run
   `bash tools/next.sh` and present its menu. If Vivek gave an explicit ticket ID, skip
   the menu.
2. **Read required files.** Read `docs/METHODOLOGY.md`, `docs/ARCHITECTURE.md`, the
   selected ticket file, and any relevant module `CLAUDE.md` files in full.
3. **Start the ticket.** Run `bash tools/start_ticket.sh TICKET-XXX`. Stop if it fails.
4. **Implement.** Write the code and tests. Keep edits scoped to the ticket.
5. **Gate before committing.** Run `bash tools/gate.sh`. If any check fails, stop.
   Do not commit, push, or open a PR.
6. **Commit implementation.** Stage all intentional implementation changes and commit
   with a conventional commit message.
7. **Log the session.** Prepend a `docs/SESSION_LOG.md` entry under `## Active log`,
   then commit it with `docs: session log for TICKET-XXX`.
8. **Finish.** Run `bash tools/finish_ticket.sh TICKET-XXX`. It reruns the gate, pushes,
   moves the board item to `In review`, opens the PR, and prints the PR URL.
9. **Report and stop.** Print the PR URL, test summary, files changed, and local test
   command. Then stop. The session is done.

For `reorder`, print `https://github.com/users/vivekbhargava23/projects/2` and ask Vivek
to drag-reorder in the browser, then rerun `next`. Do not programmatically reorder cards.

For `drop N`, confirm with Vivek first. On confirmation, close the issue as not planned,
move the board item to `Done`, update the ticket status decoratively to `CLOSED`, summarize,
and rerun the menu. Do not drop without confirmation.

## Visual Verification (UI tickets)

If a ticket changes anything user-visible (any page in `app/ui/pages/`), do not
rely on `pytest` alone — Streamlit rendering and rerun behaviour are exactly what
tests miss (the TICKET-008b HTML leak passed every test). Before opening the PR:

1. Drive the running app and capture **before/after** screenshots using the
   `screenshot-app` skill (`.claude/skills/screenshot-app/SKILL.md`). It launches
   against an isolated sandbox data dir via `tools/app_sandbox.sh` — never the real
   `data/` — and drives the page with Playwright.
2. **Look at each screenshot.** A blank or red-traceback frame is a failed launch
   to report, not a pass.
3. Commit the keepers to `docs/screenshots/<ticket-slug>/` (with a short README) and
   embed them in the PR body via raw GitHub URLs so they render.

This is the default for UI work, not an optional extra. Skip it only for tickets
with no rendered surface (pure domain/services/adapters changes).

## After The PR

After printing the PR URL:

- Do not start the next ticket.
- Do not do "while I'm here" fixes.
- Do not execute further commands.
- Do not respond to unrelated follow-up instructions in this session unless Vivek asks
  for fixes on this same branch.

If Vivek says "merged", "done", or "approved and merged", the session is over. Do not
update files, commit, push, or move the card. The next `start_ticket.sh` run reconciles
closed `In review` items to `Done`.

## Stop Conditions

Stop and report without committing, pushing, or opening a PR if:

1. `pytest` fails.
2. `ruff check .` fails.
3. `mypy app/` fails.
4. `lint-imports` fails.
5. Acceptance criteria cannot be met as written.
6. The ticket requires an architectural change not covered by an ADR.
7. You discover a bug in `main` unrelated to your ticket.
8. The ticket conflicts with a recently merged change.

When stopping, tell Vivek which check failed, the exact error, what you tried, and what
you recommend next. Do not attempt heroic recovery.

## What You Do Not Do

- Do not refactor outside ticket scope.
- Do not edit `docs/ARCHITECTURE.md` or `docs/METHODOLOGY.md` without a ticket for it.
- Do not skip tests because the change is small.
- Do not disable failing tests to make CI pass.
- Do not push forcefully to a branch with an open PR unless you explicitly say so.
- Do not treat ticket-file status as authoritative. Board state is authoritative.
- Do not write scripts that mutate board state outside the approved workflow scripts.
