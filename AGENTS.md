# AGENTS.md — Investment Dashboard

> **You are the implementation agent working on Vivek's investment dashboard.**
> Vivek **does not write code, run tests, commit, push, or open PRs**. You do all of that.
> Vivek **reviews PRs and merges them**. That is his only role in the implementation loop.
> Before doing anything, read the four files listed under "Required reading" below.

---

## Required reading (every session, in this order)

1. `docs/PROJECT_STATE.md` — current status of the project
2. `docs/METHODOLOGY.md` — how we work
3. `docs/ARCHITECTURE.md` — the architecture rules (non-negotiable)
4. `docs/SESSION_LOG.md` — last 3 entries, for recent context

If the work touches a specific module, also read that module's instruction file
(e.g. `app/domain/fifo/CLAUDE.md`). These per-module files contain module-specific
context and constraints. Read them even if your CLI does not auto-load them.

---

## The division of labor (do not violate this)

| Vivek does | The implementation agent does |
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

---

## Non-negotiable rules

1. **One ticket = one branch = one PR.** Never combine tickets in one branch.
2. **Tests must stay green.** If they fail, see "Stop conditions" — do not commit a broken state.
3. **Domain layer has zero I/O imports.** No `requests`, no file I/O, no `streamlit` in `app/domain/`. If you think you need one, open a discussion ticket — do not add the import.
4. **Conventional commits only.** `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`. One logical change per commit. A single PR may contain multiple commits, but each commit must be logically coherent on its own.
5. **You never push to `main` directly.** `main` is branch-protected. If you find yourself wanting to push to main, stop — you have made a mistake.
6. **You never merge your own PRs.** Vivek merges. You open them.

---

## What "implement TICKET-XXX" means (the complete ritual)

When Vivek says "implement TICKET-XXX" (or any variation like "do TICKET-XXX",
"work on TICKET-XXX", "start TICKET-XXX"), that is a **complete instruction**.
Execute all ten steps below, in this exact order, with no skips and no reordering.
Each step depends on the previous one. Do not ask for confirmation between steps.

When Vivek says **"implement next ticket"** or just **"next"**, resolve the ticket
via Step 0 below, then proceed from Step 1.

### Step 0 — Resolve "next ticket" (only when not given an explicit ticket ID)

```bash
gh issue list --label next-up --state open --json number,title --limit 1
```

- **Exactly one result:** use that ticket. Announce it to Vivek before proceeding.
- **Zero results:** stop and ask Vivek which ticket to pick up.
- **Multiple results:** stop and report the inconsistency — only one issue should carry `next-up` at a time.

If an explicit ticket ID was given (e.g. "implement TICKET-M1"), skip this step entirely.

### Step 1 — Verify clean main

```bash
git status                       # must be clean
git checkout main && git pull    # sync with remote
```

### Step 2 — Housekeeping from previous ticket (if applicable)

Detect whether the previous ticket's issue has been merged by querying GitHub:

```bash
gh issue view <N> --json state -q .state
```

Where `<N>` is the issue number of the ticket listed under "In review 👀" in
`docs/PROJECT_STATE.md`. If the output is `"CLOSED"`, the PR was merged — perform
housekeeping:

```bash
# Update the old ticket file: Status: IN_REVIEW → Status: MERGED
# Move the ticket from "In review 👀" to "Done ✓" in docs/PROJECT_STATE.md
git add -A
git commit -m "docs: mark TICKET-YYY as merged"
git push origin main
```

If the "In review 👀" section is empty, or if `gh issue view` returns `"OPEN"`,
skip this step.

**Note:** The housekeeping signal is the GitHub issue state, not a message from
Vivek. Do not rely on Vivek saying "I merged it" — query GitHub instead.

### Step 3 — Confirm tests on main are green

```bash
pytest -q
```

If `pytest` fails, **stop the entire session**. Tell Vivek:
"main is broken before I started — this is a bug in a previously merged PR.
I will not start TICKET-XXX until main is green." Open a hotfix ticket if needed.

### Step 4 — Read required files

Read the four files listed under "Required reading" above, plus the ticket file:

```bash
cat docs/TICKETS/TICKET-XXX-*.md
```

If the ticket touches a specific module, also read that module's instruction file.

### Step 5 — Branch and mark in-progress

```bash
git checkout -b ticket-XXX-short-name
```

Update the ticket file: `Status: QUEUED` → `Status: IN_PROGRESS`

Then update the GitHub issue labels:

```bash
gh issue edit <N> --remove-label queued,next-up --add-label in-progress
```

(Where `<N>` is the GitHub issue number for this ticket.)

### Step 6 — Implement

Write the code. Write the tests. This is the only step where you create or edit
source files under `app/` and `tests/`.

### Step 7 — Gate check (must pass before ANY commit)

```bash
pytest && ruff check . && mypy app/ && lint-imports
```

If **any** check fails: **STOP**. See "Stop conditions" below.
Do not commit. Do not push. Do not open a PR. Report the failure to Vivek.

### Step 8 — Commit, update docs, push (this exact order)

```bash
# 8a. Commit the implementation
git add -A
git commit -m "feat: <one-line summary in imperative mood>"
# (Multiple commits OK if there were multiple logical changes)

# 8b. Update docs — THIS HAPPENS HERE, BEFORE THE PUSH, ON THE BRANCH
#   - Append a new entry to docs/SESSION_LOG.md (see template in METHODOLOGY.md)
#   - In docs/PROJECT_STATE.md: move ticket from "In progress 🚧" to "In review 👀"
#   - In the ticket file: Status: IN_PROGRESS → Status: IN_REVIEW
git add -A
git commit -m "docs: update session log and project state for TICKET-XXX"

# 8c. Push the branch
git push -u origin ticket-XXX-short-name
```

**Why 8b is before 8c:** The doc updates are part of the branch's work product.
They land on `main` when Vivek merges. There is no separate "doc update" step
after the PR. If you push first and update docs later, they won't be in the PR.

### Step 9 — Open the PR and stop

The PR body **must** include `Closes #<N>` (where `<N>` is the GitHub issue number)
so the issue auto-closes when Vivek merges:

```bash
gh pr create --base main --title "<title>" --body "$(cat <<'EOF'
<description>

Closes #<N>
EOF
)"
```

Print a summary for Vivek:

```
✅ TICKET-XXX implemented and PR opened.
PR: <url>
Tests: X passing → Y passing
Files changed: <count>
Ready for your review.
```

**Then stop. The session is done.**

---

## Hard stop rules (after Step 9)

After printing the PR URL:

- **Do not start the next ticket.**
- **Do not "while I'm here" fix anything else.**
- **Do not execute any further commands.**
- **Do not respond to further instructions in this session** unless Vivek explicitly
  asks you to fix something on this specific branch (e.g. PR review feedback).

If Vivek says "looks good" or "I'll review it" — the session is still done.
You do not need to do anything else.

---

## When Vivek says "I merged it" (or "merged", "done", "approved and merged")

**This means the work is complete. There is nothing left for you to do.**

- Do NOT update any files.
- Do NOT commit or push.
- Do NOT update the ticket status to MERGED — that happens in Step 2 of the *next* session.
- Do NOT write to `main`.

The merge itself landed all your branch commits (including the doc updates from Step 8b)
onto `main`. The MERGED status bookkeeping happens automatically at the start of the next
session (Step 2) by querying `gh issue view <N> --json state`. Your session is over.

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
- ❌ Disable a failing test to make CI pass. If a test is wrong, fix the test in a separate commit with explanation. If it's flaky, open a ticket.
- ❌ `git push --force` on a branch with an open PR without saying so explicitly in your next message to Vivek.
- ❌ Write to `main` after Vivek says he merged the PR. The session is over. See "When Vivek says 'I merged it'" above.
- ❌ Treat doc updates (SESSION_LOG, PROJECT_STATE, ticket status) as post-PR housekeeping. They are Step 8b — before push, before PR. Always.
