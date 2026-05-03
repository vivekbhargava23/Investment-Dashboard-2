# CLAUDE.md — Investment Dashboard

> **You are Claude Code working on Vivek's investment dashboard.**
> Vivek **does not write code, run tests, commit, push, or open PRs**. You do all of that.
> Vivek **reviews PRs and merges them**. That is his only role in the implementation loop.
> Before doing anything, read the four files listed under "Required reading" below.

---

## Required reading (every session, in this order)

1. `docs/PROJECT_STATE.md` — current status of the project
2. `docs/METHODOLOGY.md` — how we work
3. `docs/ARCHITECTURE.md` — the architecture rules (non-negotiable)
4. `docs/SESSION_LOG.md` — last 3 entries, for recent context

If the work touches a specific module, also read that module's `CLAUDE.md`
(e.g. `app/domain/fifo/CLAUDE.md`).

---

## The division of labor (do not violate this)

| Vivek does | Claude Code does |
|---|---|
| Picks the next ticket | Implements the ticket |
| Reviews the PR | Writes the code |
| Merges the PR | Writes the tests |
| Drafts ADRs in chat | Runs the tests |
| Approves architectural changes | Runs the linters |
| | Commits with conventional commit messages |
| | Pushes the branch |
| | Opens the PR via `gh pr create` |
| | Updates `docs/SESSION_LOG.md` |
| | Updates `docs/PROJECT_STATE.md` |
| | Updates the ticket's `Status:` field |

If Vivek says "implement TICKET-001," that is a complete instruction. You execute the entire flow end-to-end. You do not stop and ask "should I commit?" — yes, always commit. You do not ask "should I push?" — yes, always push. You do not ask "should I open a PR?" — yes, always open the PR. The only thing you stop for is **failing tests or failing linters** — see "Stop conditions" below.

---

## Non-negotiable rules

1. **One ticket = one branch = one PR.** Never combine tickets in one branch.
2. **Tests must stay green.** If they fail, see "Stop conditions" — do not commit a broken state.
3. **Domain layer has zero I/O imports.** No `requests`, no file I/O, no `streamlit` in `app/domain/`. If you think you need one, open a discussion ticket — do not add the import.
4. **Conventional commits only.** `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`. One logical change per commit. A single PR may contain multiple commits, but each commit must be logically coherent on its own.
5. **You never push to `main` directly.** `main` is branch-protected. If you find yourself wanting to push to main, stop — you have made a mistake.
6. **You never merge your own PRs.** Vivek merges. You open them.

---

## Session-start ritual (always run this in order)

```bash
# 1. Confirm clean working tree on main
git status
git checkout main && git pull

# 2. Confirm tests on main are green BEFORE you start
pytest -q

# 3. Read required files (listed above)

# 4. Read the ticket file
cat docs/TICKETS/TICKET-XXX-*.md

# 5. Branch from main using ticket-XXX-short-name
git checkout -b ticket-XXX-short-name

# 6. Update ticket status: change `Status: READY` to `Status: IN_PROGRESS` in the ticket file
```

If `pytest` on main is not green, **stop**. Tell Vivek: "main is broken before I started — this is a bug in a previously merged PR. I will not start TICKET-XXX until main is green." Open a hotfix ticket if needed.

---

## Session-end ritual (always run this in order, no exceptions)

```bash
# 1. Run the full check
pytest && ruff check . && mypy app/ && lint-imports

# 2. If any check fails: STOP. See "Stop conditions" below.

# 3. Stage and commit using conventional commits
git add -A
git commit -m "feat: <one-line summary in imperative mood>"
# (Multiple commits OK if there were multiple logical changes)

# 4. Update docs/SESSION_LOG.md (append new entry — see template in METHODOLOGY.md)
# 5. Update docs/PROJECT_STATE.md (move ticket from "In progress" to "In review")
# 6. Update the ticket file's Status: line to IN_REVIEW
git add -A
git commit -m "docs: update session log and project state for TICKET-XXX"

# 7. Push the branch
git push -u origin ticket-XXX-short-name

# 8. Open the PR — the PR template will be auto-loaded from .github/PULL_REQUEST_TEMPLATE.md
gh pr create --fill --base main

# 9. Print the PR URL for Vivek
```

After step 9, **the session is done**. Print a short summary for Vivek:

```
✅ TICKET-XXX implemented and PR opened.
PR: https://github.com/<user>/<repo>/pull/N
Tests: X passing → Y passing
Files changed: <count>
Ready for your review.
```

Then stop. Do not start the next ticket. Do not "while I'm here." Stop.

---

## Stop conditions

You **must stop and report** (not commit, not push) if:

1. `pytest` fails — even one test, even a "flaky" one
2. `ruff check .` fails — including warnings if configured as errors
3. `mypy app/` fails
4. `lint-imports` fails (architecture violation)
5. The acceptance criteria in the ticket cannot be met as written
6. You discover the ticket requires an architectural change not covered by an ADR
7. You discover a bug in `main` unrelated to your ticket
8. You discover the ticket conflicts with a recently merged change

When you stop, tell Vivek precisely:
- Which check failed and the exact error message
- What you tried (if anything)
- What you recommend (continue with a workaround? open a new ticket? roll back?)

Do not attempt heroic recovery. Stopping early is cheap; a bad merge is expensive.

---

## What you do NOT do

- ❌ "While I'm here, let me also fix..." → Open a new ticket file in `docs/TICKETS/`. Do not fix.
- ❌ Refactor outside the ticket's stated scope.
- ❌ Edit `docs/ARCHITECTURE.md` or `docs/METHODOLOGY.md` without an explicit ticket for it.
- ❌ Skip writing tests because "it's a small change." There are no small changes.
- ❌ Merge your own PR.
- ❌ Push to `main` directly. (Branch protection should reject it; if it doesn't, stop and tell Vivek branch protection is misconfigured.)
- ❌ Use Opus for typing work. Default is Sonnet 4.6. Vivek will switch you to Opus when needed.
- ❌ Disable a failing test to make CI pass. If a test is wrong, fix the test in a separate commit with explanation. If it's flaky, open a ticket.
- ❌ `git push --force` on a branch with an open PR without saying so explicitly in your next message to Vivek.

---

## When Vivek says "implement TICKET-XXX"

That is your complete instruction. Execute end-to-end:
1. Session-start ritual
2. Implement
3. Session-end ritual
4. Print PR URL
5. Stop

You do not need to confirm intermediate steps. Just go.
