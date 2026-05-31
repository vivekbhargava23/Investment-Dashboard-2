# AGENTS.md — Investment Dashboard

> **You are the implementation agent working on Vivek's investment dashboard.**
> Vivek **does not write code, run tests, commit, push, or open PRs**. You do all of that.
> Vivek **reviews PRs and merges them**. That is his only role in the implementation loop.
> Before doing anything, read the four files listed under "Required reading" below.

---

This file is for the implementation agent. Vivek's day-to-day workflow lives in `docs/VIVEK.md` and is not your concern.

## Local environment (macOS setup)

`tools/*.sh` are POSIX-portable and run on **stock macOS bash 3.2 + BSD grep** — no
`brew install bash` or GNU grep required. You only need `git`, `gh` (authenticated),
and `jq` on PATH. See `tools/README.md` for the full toolchain reference.

---

## Required reading (every session, in this order)

1. `docs/CONTEXT.md` — auto-generated repo snapshot: code interfaces, UI surface, GitHub state, and board status (Up next, In progress, In review, Recently done). Gives a complete picture without re-exploring the codebase every session.
2. `docs/METHODOLOGY.md` — how we work
3. `docs/ARCHITECTURE.md` — the architecture rules (non-negotiable)

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
| Drags cards on the project board | Commits with conventional commit messages |
| | Pushes the branch |
| | Opens the PR via `gh pr create` |
| | Moves board items via `gh project item-edit` |

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

**Trigger:** Vivek says `next` (or `implement next ticket`).

**Action:** Query the GitHub Projects board for items in `Ready` column first, then `Backlog`, in board order:

```bash
gh project item-list 2 --owner @me --format json --limit 100
```

Filter out items whose linked issue is closed. Present as a numbered menu:

```
Up next (N tickets):

Ready (vetted):
  1. TICKET-XXX — Title [HIGH] (issue #N)
  2. TICKET-YYY — Title [MEDIUM] (issue #M)
Backlog:
  3. TICKET-ZZZ — Title [LOW] (issue #P)

Reply with:
  <number>      pick a ticket and start implementing
  reorder       open the board in your browser to drag-reorder (then re-run `next`)
  drop N        close ticket #N and remove from the board
  cancel        do nothing
```

**On `<number>`:** proceed to Step 1 with that ticket. Step 5 moves the board item to `In progress`.

**On `reorder`:** print `https://github.com/users/vivekbhargava23/projects/2` and tell Vivek to drag-reorder in the browser, then re-run `next`. Do not attempt programmatic reordering.

**On `drop N`:** confirm with Vivek ("Drop TICKET-XXX? This closes the issue and removes it from the board."). On confirmation:
1. `gh issue close <issue-number> --reason "not planned"`
2. Move the board item to `Done` (the post-merge action won't fire for issue close):
   ```bash
   ITEM_ID=$(gh project item-list 2 --owner @me --format json --limit 100 | jq -r --argjson n <issue-num> '.items[] | select(.content.number==$n) | .id')
   DONE_OPTION_ID=$(gh project field-list 2 --owner @me --format json | jq -r '.fields[] | select(.name=="Status") | .options[] | select(.name=="Done") | .id')
   PROJECT_ID=$(gh project list --owner @me --format json | jq -r '.projects[] | select(.number==2) | .id')
   STATUS_FIELD_ID=$(gh project field-list 2 --owner @me --format json | jq -r '.fields[] | select(.name=="Status") | .id')
   gh project item-edit --project-id "$PROJECT_ID" --id "$ITEM_ID" --field-id "$STATUS_FIELD_ID" --single-select-option-id "$DONE_OPTION_ID"
   ```
3. Update the ticket file's `Status:` to `CLOSED` (decorative).
4. Print a summary.
5. Re-present the menu.

**On `cancel`:** stop. No state changes.

**Edge case — board is empty (`Ready` and `Backlog` both empty):**
> "Board is empty. File tickets via `bash tools/file.sh` after saving them to `docs/TICKETS/`."
Stop.

**Edge case — an item's linked issue is CLOSED:** skip it in the menu (defensive — shouldn't happen because `Done` items have closed issues).

**Override:** If Vivek says `implement TICKET-XXX` (explicit ID), skip this step entirely.

### Step 1 — Verify clean main

```bash
git status                       # must be clean
git checkout main && git pull    # sync with remote
```

### Step 2 — Verify housekeeping from previous ticket (if applicable)

GitHub Actions runs `post-merge-housekeeping.yml` within seconds of every merge.
By the time you start the next session, the board card should already be in `Done`.

Query the board for any items still in `In review`. For each one, check if its linked issue is closed:

```bash
gh project item-list 2 --owner @me --format json --limit 100 | \
  jq '.items[] | select(.status=="In review") | {id, number: .content.number, title: .content.title}'
```

For each `In review` item whose issue is CLOSED (i.e., `gh issue view <N> --json state -q .state` returns `"CLOSED"`):
- Move the board item to `Done`:
  ```bash
  ITEM_ID=<item-id>
  PROJECT_ID=$(gh project list --owner @me --format json | jq -r '.projects[] | select(.number==2) | .id')
  STATUS_FIELD_ID=$(gh project field-list 2 --owner @me --format json | jq -r '.fields[] | select(.name=="Status") | .id')
  DONE_OPTION_ID=$(gh project field-list 2 --owner @me --format json | jq -r '.fields[] | select(.name=="Status") | .options[] | select(.name=="Done") | .id')
  gh project item-edit --project-id "$PROJECT_ID" --id "$ITEM_ID" --field-id "$STATUS_FIELD_ID" --single-select-option-id "$DONE_OPTION_ID"
  ```
- This is defense-in-depth — the post-merge action should have already done this.

If all `In review` items have open issues, or if there are no `In review` items: no action needed.

### Step 3 — Confirm tests on main are green

```bash
pytest -q
```

If `pytest` fails, **stop the entire session**. Tell Vivek:
"main is broken before I started — this is a bug in a previously merged PR.
I will not start TICKET-XXX until main is green." Open a hotfix ticket if needed.

### Step 4 — Read required files

Read the three files listed under "Required reading" above, plus the ticket file:

```bash
cat docs/TICKETS/TICKET-XXX-*.md
```

If the ticket touches a specific module, also read that module's instruction file.

### Step 5 — Worktree, branch, and mark in-progress

If the current working directory is the **main checkout** (i.e. `git rev-parse --abbrev-ref HEAD` returns `main`):

```bash
# Prune any worktrees whose branch has already landed on main
bash tools/cleanup-worktrees.sh || true

slug="ticket-$(echo TICKET-XXX | tr '[:upper:]' '[:lower:]' | sed -E 's/ticket-//')-short-name"
worktree_path="../$(basename "$(git rev-parse --show-toplevel)")-$(echo TICKET-XXX | tr '[:upper:]' '[:lower:]' | sed -E 's/ticket-//')"
git worktree add "$worktree_path" -b "$slug"

# Share the main checkout's runtime data directory (and .env if present)
main_root="$(git rev-parse --show-toplevel)"
rm -rf "$worktree_path/data"
ln -s "$main_root/data" "$worktree_path/data"
[ -f "$main_root/.env" ] && ln -s "$main_root/.env" "$worktree_path/.env" || true

cd "$worktree_path"
```

If already inside a worktree (HEAD is not `main`): reuse it — confirm the branch name matches the ticket; no new worktree creation needed.

Update the ticket file: `Status: QUEUED` → `Status: IN_PROGRESS` (decorative — nothing reads this).

Move the picked ticket's board item to `In progress`:

```bash
PROJECT_ID=$(gh project list --owner @me --format json | jq -r '.projects[] | select(.number==2) | .id')
STATUS_FIELD_ID=$(gh project field-list 2 --owner @me --format json | jq -r '.fields[] | select(.name=="Status") | .id')
IN_PROGRESS_OPTION_ID=$(gh project field-list 2 --owner @me --format json | jq -r '.fields[] | select(.name=="Status") | .options[] | select(.name=="In progress") | .id')
ITEM_ID=$(gh project item-list 2 --owner @me --format json --limit 100 | jq -r --argjson n <issue-num> '.items[] | select(.content.number==$n) | .id')
gh project item-edit --project-id "$PROJECT_ID" --id "$ITEM_ID" \
  --field-id "$STATUS_FIELD_ID" \
  --single-select-option-id "$IN_PROGRESS_OPTION_ID"
```

No commit to main from the agent. The board update is API-only.

### Step 6 — Implement

Write the code. Write the tests. This is the only step where you create or edit
source files under `app/` and `tests/`.

### Step 7 — Gate check (must pass before ANY commit)

```bash
pytest && ruff check . && mypy app/ && lint-imports
```

If **any** check fails: **STOP**. See "Stop conditions" below.
Do not commit. Do not push. Do not open a PR. Report the failure to Vivek.

#### Conda env activation

All shell calls that require Python (`pytest`, `ruff`, `mypy`, `lint-imports`, `streamlit`) must prefix with:

```bash
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate investment-dashboard && <command>
```

On systems with `mamba`, substitute `mamba` for `conda`. The agent never relies on the outer shell having the conda env already activated.

### Step 8 — Commit, log, and push

```bash
# 8a. Commit the implementation
git add -A
git commit -m "feat: <one-line summary in imperative mood>"
# (Multiple commits OK if there were multiple logical changes)

# 8b. Append session log entry to docs/SESSION_LOG.md, then commit
# Prepend a new entry (matching the template in docs/SESSION_LOG.md) under ## Active log
git add docs/SESSION_LOG.md
git commit -m "docs: session log for TICKET-XXX"

# 8c. Push the branch
git push -u origin ticket-XXX-short-name

# 8d. Move the board item to In review
PROJECT_ID=$(gh project list --owner @me --format json | jq -r '.projects[] | select(.number==2) | .id')
STATUS_FIELD_ID=$(gh project field-list 2 --owner @me --format json | jq -r '.fields[] | select(.name=="Status") | .id')
IN_REVIEW_OPTION_ID=$(gh project field-list 2 --owner @me --format json | jq -r '.fields[] | select(.name=="Status") | .options[] | select(.name=="In review") | .id')
ITEM_ID=$(gh project item-list 2 --owner @me --format json --limit 100 | jq -r --argjson n <issue-num> '.items[] | select(.content.number==$n) | .id')
gh project item-edit --project-id "$PROJECT_ID" --id "$ITEM_ID" \
  --field-id "$STATUS_FIELD_ID" \
  --single-select-option-id "$IN_REVIEW_OPTION_ID"
```

There is no separate doc-update step. The ticket file's `Status:` line is decorative and is not updated here. State is on the board.

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
- Do NOT update the ticket status — the post-merge action moves the board card to `Done`.
- Do NOT write to `main`.

The merge itself landed all your branch commits onto `main`. GitHub Actions
(`post-merge-housekeeping.yml`) moves the board item to `Done` and
`update-context.yml` regenerates `CONTEXT.md` within seconds. Step 2 of the
next session verifies it landed; in the rare case the workflow failed, Step 2
reconciles manually by moving the board item directly.

Your session is over.

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
- ❌ Treat doc updates (STATE.md, ticket status) as post-PR housekeeping. Board state is managed via the API (Steps 5, 8c). Ticket `Status:` lines are decorative — update them in Step 5 if you like, but nothing reads them.
- ❌ Edit the project board order programmatically. Vivek drags cards; the agent only writes the Status column.
