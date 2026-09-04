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

## Hard Rules — Read These Even If You Read Nothing Else

1. **Vivek picks the tickets.** Never file, create, or start a ticket he did not ask for.
   Recommending one in prose is correct; running `tools/file.sh` for it is not.
2. **Stopping is a successful outcome.** When a workflow script fails, report the exact
   error and your recommendation, then stop. A blocked session that changed nothing is a
   good session. Do not invent recovery work to avoid stopping.
3. **A script failure authorises nothing.** After a failed script you may not file a
   ticket, create a branch, commit, push, or mutate the board in response.
4. **Do not re-run a script that mutates GitHub state** after a failure unless the error
   text says the rerun is safe. Board mutations cost API budget; blind retries are what
   exhaust the rate limit.
5. **Never push to `main` directly. Never merge your own PRs.**

The rest of this file expands on these. If a later section ever seems to license an
exception, the rule above wins.

## Session Preflight

Before step 1 of the ritual, run `git status -sb`.

- On `main` with a clean tree: proceed.
- Not on `main`: `bash tools/start_ticket.sh` now handles this itself. It refuses on a
  dirty tree, refuses if the current branch's PR is open, closed-unmerged, or missing,
  and only when the branch's PR is **merged** does it check out `main`, fast-forward, and
  create the next ticket branch.
- Dirty tree: stop and report the dirty files. Never stash, reset, or discard Vivek's
  working changes to unblock yourself.

This is the only recovery you may perform without asking. Anything beyond it — switching
branches by hand, deleting branches, force-pushing, filing a ticket about the blockage —
is out of bounds.

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
| Drags cards when he wants to override | Pushes the branch |
| | Keeps board order ranked via `tools/reorder.sh` |
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

- `bash tools/next.sh` — prints the ranked Ready/Backlog menu in two sections,
  **Startable now** and **Blocked**, with model, priority, dependency blockers, and
  transitive unblock score. Ranking keys, in order: startable before blocked, `Ready`
  before `Backlog`, priority, how much the ticket unblocks transitively, board position.
  See "How ticket order is decided" in `docs/METHODOLOGY.md`.
- `bash tools/start_ticket.sh TICKET-XXX` — reconciles closed `In review` items to
  `Done`, gets onto an up-to-date `main`, creates/reuses the feature branch, marks the
  ticket file `IN_PROGRESS`, and moves the board item to `In progress`. If a blocked
  ticket is explicitly requested, it warns and continues. It is safe to run while still
  checked out on the previous ticket's branch: with a clean tree and a merged PR it
  returns to `main` automatically, and it refuses (changing nothing) on a dirty tree or
  an unmerged branch. It is idempotent — rerunning it on the branch it just created only
  redoes the board move, which is the documented recovery when GitHub rate-limits the
  board update.
- `bash tools/gate.sh` — activates `investment-dashboard` and runs `pytest`,
  `ruff check .`, `mypy app/`, and `lint-imports`, stopping at the first failure.
- `bash tools/finish_ticket.sh TICKET-XXX` — reruns the gate, pushes the current branch,
  moves the board item to `In review`, and opens the PR with `Closes #N` in the body.
- `bash tools/reorder.sh` — moves the Ready/Backlog board cards into the order
  `next.sh` ranks, so the board and the menu never tell different stories. `--dry-run`
  prints the target order without touching anything. `tools/file.sh` calls it after
  filing, so newly filed tickets land in the right place.
- `bash tools/archive.sh` — moves ticket specs the board marks `Done` from
  `docs/TICKETS/` into `docs/TICKETS/DONE/`. `--dry-run` prints the moves without touching
  anything. It stages the moves with `git mv` and leaves the commit to you
  (`docs: archive done tickets`). **Ticket lookup is directory-agnostic** — every lookup
  globs `docs/TICKETS` recursively, so an archived ticket is still found by ID. New
  tickets are always filed at the top level of `docs/TICKETS/`; only archiving moves them.
- `bash tools/doctor.sh` — non-mutating preflight diagnostics for local state, retired
  files, board sanity, and dependency blockers.

Do not inline the old `gh`/`jq` board-management blocks. If a script fails, report the
exact failure instead of hand-editing the board.

## Complete Ticket Ritual

When Vivek says "implement TICKET-XXX" (or "do", "work on", "start"), that is a
complete instruction. Do not ask for confirmation between steps.

1. **Resolve the ticket.** If Vivek said `next` or `implement next ticket`, run
   `bash tools/next.sh` and present its menu. Present means **reproduce the table** in
   your reply as a markdown table — the script's stdout is not reliably visible to Vivek,
   and a prose summary of it is not a menu. Keep the two sections separate and in rank
   order; the startable section is the only one he can pick from. Show at least the top
   8 startable rows plus any blocked row needed to make a dependency chain legible, and
   put your one-line recommendation *after* the table, never instead of it. If Vivek gave
   an explicit ticket ID, skip the menu.
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

For `reorder`, run `bash tools/reorder.sh`. It drags the Ready/Backlog card stack into
the same order `next.sh` ranks, and leaves In progress / In review / Done cards alone.
Use `--dry-run` first if you want to show Vivek the target order before moving anything.
This replaces the old "ask Vivek to drag cards in the browser" step — he asked for the
board to be organised automatically on 2026-09-04. He can still drag freely afterwards;
the next `reorder` run simply re-derives the ranked order.

For `archive`, run `bash tools/archive.sh --dry-run`, show Vivek the moves, then run
`bash tools/archive.sh` and commit with `docs: archive done tickets`. It must be its own
commit — archiving is housekeeping and must never be mixed into an implementation commit.
Only the board decides what is Done; ticket-file status is still not
authoritative. `bash tools/doctor.sh` reports how many Done tickets are waiting to be
archived, so you never have to guess.

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

Ending the session on the feature branch is correct and expected. Do not check out `main`
"to tidy up" — the next `start_ticket.sh` handles the handoff itself.

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
9. Any workflow script fails for any reason, including GitHub API rate limits.
10. `start_ticket.sh` refuses to leave the current branch.

When stopping, tell Vivek which check failed, the exact error, what you tried, and what
you recommend next. Do not attempt heroic recovery.

## What You Do Not Do

- Do not file, create, or start a ticket Vivek did not ask for, including tickets that
  would fix a workflow problem you just hit. Write the recommendation in your reply and
  let Vivek decide.
- Do not re-run a board-mutating script after a failure unless the error says it is safe.
  `start_ticket.sh` is the one exception: its rate-limit message names itself as the
  resumable rerun.
- Do not move ticket files by hand. `bash tools/archive.sh` is the only way tickets change
  directory.
- Do not refactor outside ticket scope.
- Do not edit `docs/ARCHITECTURE.md` or `docs/METHODOLOGY.md` without a ticket for it.
- Do not skip tests because the change is small.
- Do not disable failing tests to make CI pass.
- Do not push forcefully to a branch with an open PR unless you explicitly say so.
- Do not treat ticket-file status as authoritative. Board state is authoritative.
- Do not file a ticket without a `**Depends on:**` line. `none` is a valid answer; a
  missing line silently corrupts the ordering of every ticket downstream of it.
- Do not write scripts that mutate board state outside the approved workflow scripts.
  `tools/reorder.sh` is one of the approved scripts; card ordering goes through it, never
  through ad-hoc `gh api graphql` calls.
