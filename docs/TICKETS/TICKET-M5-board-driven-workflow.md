# TICKET-M5 — Replace ticket-filing tooling with GitHub Projects board as source of truth

**Status:** IN_PROGRESS
**Priority:** HIGH
**Estimated session length:** 3 – 4 hr
**Drafted by:** Vivek + Claude (chat 2026-05-14)
**Implemented by:** Claude Code (session TBD)
**Milestone:** Workflow & tooling
**Depends on:** TICKET-M4a merged, TICKET-M4b merged

---

## Problem

The current ticket-filing workflow has accumulated three sources of truth (STATE.md "Next up", GitHub issues, ticket files) kept in sync by fragile scripts. Filing a single ticket touches four artifacts (ticket file, STATE.md, GitHub issue, git push) with six failure modes between them. During the M4a/M4b/026/027 filing session, the workflow broke six distinct times in three hours.

Concrete failures observed:

1. **`X.` prefix bug silently dropped tickets from STATE.md.** When `draft_ticket.sh` received a `POSITION` field, the inline Python inserted `X. TICKET-XXX — ...` then ran a renumbering regex `^\d+\.` that didn't match `X.`. The ticket vanished. TICKET-026 and TICKET-027 created valid GitHub issues but never appeared in STATE.md "Next up" — Vivek had to manually `gh issue reopen 64` to recover.

2. **Clean-tree guard rejected the ticket file you were about to file.** Saving the `.md` to `docs/TICKETS/` made the tree dirty, so the script refused to run. Workaround was saving to `~/Downloads/` and `cat`-ing it in via heredoc.

3. **Branch guard assumed you were already on main.** After merging a PR on GitHub, local was still on the feature branch. Script aborted.

4. **Empty body created issue + commit + push.** When `cat ~/Downloads/file.md` failed because the file didn't exist, the pipeline still ran. Result: empty ticket file, real GitHub issue, real commit, real push.

5. **No batch filing.** Chat drafts 2-6 tickets per session. Each required separate shell block, separate commit, separate push.

6. **Half-successful states.** GitHub issue creation happened before push. If push failed, you had orphan issues and had to rerun manually.

The root cause is not any individual bug. **The root cause is having STATE.md and GitHub issues as two sources of truth for the same data.** Every script that keeps them in sync is a place where they can drift.

## The fix

**Eliminate the sync entirely. GitHub Issues + GitHub Projects board become the only source of truth for ticket state and ordering. STATE.md is deleted. CONTEXT.md (auto-generated) is the only state doc.**

State derivation:
- "Drafted, waiting to start" → issue on the board in `Backlog` or `Ready` column
- "In progress" → issue on the board in `In progress` column (set by the agent when it picks the ticket)
- "In review" → issue on the board in `In review` column (set when PR opens)
- "Done" → issue on the board in `Done` column (set by post-merge action)

Ordering: by position within each column on the GitHub Projects board. Vivek drags to reorder in the GitHub web UI. No `queue.txt`, no `POSITION` field, no STATE.md "Next up" mutation logic.

Filing workflow (Vivek's side):
1. Save one or more ticket `.md` files to `docs/TICKETS/`
2. Run `bash tools/file.sh`
3. Done

`file.sh` finds every untracked `docs/TICKETS/TICKET-*.md`, parses each, creates a GitHub issue, adds the issue to the board in `Backlog` column, commits all the ticket files, pushes. One command, any number of tickets, no STATE.md write.

Implementation workflow (agent's side):
1. `next` reads the board's `Ready` column, then `Backlog` column, presents a numbered menu
2. On pick: agent moves the issue card to `In progress` on the board, branches, implements
3. On PR open: agent moves the card to `In review`
4. On merge: post-merge action moves the card to `Done`

---

## Project board details (already exists, confirmed working)

- **Board:** `@vivekbhargava23's Investment dashboard 2 test1`, number `2`, ID `PVT_kwHOA9Rkqc4BW2VV`
- **Owner:** `@me` (i.e. `vivekbhargava23`)
- **Status field** (the column field): `PVTSSF_lAHOA9Rkqc4BW2VVzhSHWXM`
- **Status options:**
  - `Backlog` → option ID `f75ad846` — default for newly filed tickets
  - `Ready` → option ID `61e4505c` — tickets vetted and ready to pick (Vivek can drag from Backlog to here)
  - `In progress` → option ID `47fc9ee4` — agent sets this in Step 5
  - `In review` → option ID `df73e18b` — agent sets this in Step 9 (when PR opens)
  - `Done` → option ID `98236657` — post-merge action sets this

These IDs must be referenced by name lookup, not hardcoded, in case the board is recreated. The agent should query the board on startup and resolve names → IDs each session.

---

## Acceptance criteria

### A. New script: `tools/file.sh`

- [ ] Single executable bash script. No POSITION field. No clean-tree guard. No batch separator syntax — supports any number of files natively by finding untracked `TICKET-*.md` files.
- [ ] **Step 1: Branch handling.** If not on `main`, attempt `git checkout main`. If that fails because of uncommitted changes on the current branch, print a clear error naming the dirty files and exit 1 without touching anything. Do not stash. If on `main` already, proceed.
- [ ] **Step 2: Pull.** Run `git pull --ff-only origin main`. If it fails (divergence, conflicts), print the error and exit 1.
- [ ] **Step 3: Find new tickets.** Use `git ls-files --others --exclude-standard docs/TICKETS/TICKET-*.md` to list untracked ticket files. If empty, print "No new ticket files in docs/TICKETS/. Save .md files there and rerun." and exit 0 (not an error).
- [ ] **Step 4: Validate every ticket file before any side effects.** For each file:
  - Filename matches `TICKET-[A-Z0-9-]+-[a-z0-9-]+\.md` (e.g. `TICKET-M5-board-driven-workflow.md`). Reject otherwise.
  - First non-blank line matches `# TICKET-([A-Z0-9-]+) — (.+)` — extract `ID` and `TITLE` from this.
  - Body contains `**Priority:** (CRITICAL|HIGH|MEDIUM|LOW)`. Extract priority.
  - Body contains `**Milestone:** (.+)`. Extract milestone.
  - Body is at least 500 non-whitespace characters (catches truncation/empty bodies; the M5 ticket itself is ~5000+ chars, so 500 is a generous lower bound).
  - The `ID` from the heading matches the filename's `TICKET-XXX` prefix.
- [ ] **If any file fails validation, abort the entire run before any GitHub or git side effect.** Print a numbered list of every failure with filename and reason. Exit 1.
- [ ] **Step 5: Create one GitHub issue per file.** For each validated file:
  - `gh issue create --title "<ID> — <TITLE>" --body-file <path> --label <priority-lowercased> --milestone <milestone>` if the milestone exists and is open. If milestone is missing or closed, create the issue without milestone and print a warning (do not abort).
  - Capture the issue URL and number.
- [ ] **Step 6: Add each new issue to the project board.** For each issue:
  - `gh project item-add 2 --owner @me --url <issue-url>` → returns the item ID
  - `gh project item-edit --project-id PVT_kwHOA9Rkqc4BW2VV --id <item-id> --field-id PVTSSF_lAHOA9Rkqc4BW2VVzhSHWXM --single-select-option-id f75ad846` → sets Status to `Backlog`
  - The board IDs must be resolved via name lookup at script start, not hardcoded. Use:
    ```bash
    PROJECT_ID=$(gh project list --owner @me --format json | jq -r '.projects[] | select(.number==2) | .id')
    STATUS_FIELD_ID=$(gh project field-list 2 --owner @me --format json | jq -r '.fields[] | select(.name=="Status") | .id')
    BACKLOG_OPTION_ID=$(gh project field-list 2 --owner @me --format json | jq -r '.fields[] | select(.name=="Status") | .options[] | select(.name=="Backlog") | .id')
    ```
  - Project number `2` is hardcoded as a script constant `PROJECT_NUMBER=2`. If it ever changes, edit the script.
- [ ] **Step 7: Commit and push.** `git add docs/TICKETS/TICKET-*.md`, commit with message `docs: file TICKET-XXX[, TICKET-YYY, ...]` (list all IDs), `git push origin main`.
- [ ] **Step 8: Print summary.**
  ```
  Filed 2 tickets:
    TICKET-M5    — Replace ticket-filing tooling... → issue #67, added to Backlog
    TICKET-028   — ... → issue #68, added to Backlog
  Commit pushed: <sha>
  ```
- [ ] **Error handling between issue creation and board placement:** if `item-add` fails for an issue that was created, print the issue URL and instructions to add it to the board manually. Continue with remaining issues. Do not roll back.
- [ ] **Error handling for push failure after commit:** print recovery instructions (`git pull --rebase origin main && git push origin main`). Do NOT roll back issue creation. The issues are real; the commit lands eventually.

### B. Delete obsolete tooling

- [ ] Delete `tools/draft_ticket.sh`.
- [ ] Delete `tools/update_state.py`.
- [ ] Delete `tools/sync_state.py`.
- [ ] Delete `tools/_next_up.py`.
- [ ] Delete `docs/STATE.md`.
- [ ] Remove `queued` and `in-progress` labels from the repo: `gh label delete queued --yes` and `gh label delete in-progress --yes`. Before deleting, remove the labels from any open issue that still has them.
- [ ] If any other tool under `tools/` references the deleted modules, update or delete it.

### C. Rewrite `.github/workflows/post-merge-housekeeping.yml`

- [ ] On every PR merge to `main`:
  1. Parse the merged PR body for `Closes #N` (and `Fixes #N`, `Resolves #N`). For each linked issue:
     - Resolve `PROJECT_ID`, `STATUS_FIELD_ID`, `DONE_OPTION_ID` via `gh project` queries.
     - Find the project item for the issue (query the project items, filter by `content.number == N`).
     - Move it to `Done` via `gh project item-edit`.
  2. Trigger CONTEXT.md regeneration (already handled by `update-context.yml` on push; verify the chain still works).
- [ ] Remove all STATE.md update logic from this workflow. No "Recent activity", no "In review → Done", no "Last updated:" stamp.
- [ ] Remove the ticket file `Status:` line update logic. Status is now derived from the board column, not from the ticket file. The `Status:` line in ticket files becomes purely informational and decorative (the agent may write `QUEUED` / `IN_PROGRESS` / etc. but no automation reads it).
- [ ] Keep the recursion guard (`if: github.actor != 'github-actions[bot]'`).
- [ ] Commit message convention: `chore: post-merge housekeeping for TICKET-XXX (#N) [skip ci]`. (Unchanged.)

### D. Rewrite `tools/regen_context.py` (from TICKET-M4a)

- [ ] Remove the section that inlines STATE.md "State driver". STATE.md no longer exists.
- [ ] Add a new section `## Up next` that queries the project board:
  - List items in `Ready` column first (in board order, top-to-bottom), then `Backlog` column (in board order).
  - For each item: `<ID> — <title> [<priority>] (issue #N)`.
  - Use `gh project item-list 2 --owner @me --format json --limit 100` and parse the JSON.
- [ ] Add `## In progress` section: items in `In progress` column. Same format.
- [ ] Add `## In review` section: items in `In review` column. Same format.
- [ ] Add `## Recently done` section: items in `Done` column, last 10 by `updatedAt`. Same format.
- [ ] Keep all other existing sections (ADRs, File tree, Public interfaces, UI surface, Data file shape, Open issues, Open PRs, Recent merges, Tests inventory).
- [ ] If `gh project` queries fail (auth issue, rate limit), gracefully degrade: emit the section header with `<project board unavailable at generation time — section skipped>`. Do not crash the whole regeneration.
- [ ] Update the file header paragraph to mention "Up next, In progress, In review, Recently done are sourced from the GitHub Projects board (project #2)."

### E. Rewrite Step 0 of `docs/AGENTS.md` — execution-time menu

The current Step 0 reads STATE.md "Up next". It now reads the project board.

- [ ] On `next` (or `implement next ticket`):
  - Query the board: `Ready` column first, then `Backlog`, in board order.
  - Filter out items whose linked issue is closed (defensive — shouldn't happen, but skip if so).
  - Show a numbered menu:
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
- [ ] **On `<number>`:** agent proceeds to Step 1 (clean main). Step 5 now moves the board item to `In progress` instead of editing STATE.md.
- [ ] **On `reorder`:** print `https://github.com/users/vivekbhargava23/projects/2` and tell Vivek to drag-reorder in the browser, then re-run `next`. The agent does not attempt programmatic reordering — that's a complex GraphQL mutation and the browser UI is faster.
- [ ] **On `drop N`:** confirm with Vivek, then `gh issue close <issue-number> --reason "not planned"`. The post-merge action does not fire for issue close (only for PR merge), so the agent also moves the board item to `Done` directly. Print a summary.
- [ ] **On `cancel`:** stop the session.
- [ ] **Edge case: no items in `Ready` or `Backlog`.** Print: "Board is empty. File tickets via `bash tools/file.sh` after saving them to `docs/TICKETS/`."
- [ ] **Override:** `implement TICKET-XXX` skips the menu, goes straight to Step 1 with that ticket. Step 5 moves the board item to `In progress` regardless of its current column.

### F. Rewrite Step 5 of `docs/AGENTS.md`

- [ ] Remove all STATE.md mutation logic. No more "edit STATE.md to remove from Up next, commit to main, push."
- [ ] Instead: after branching and before implementation, the agent moves the picked ticket's board item to `In progress`:
  ```bash
  ITEM_ID=$(gh project item-list 2 --owner @me --format json --limit 100 | jq -r '.items[] | select(.content.number==<issue-num>) | .id')
  gh project item-edit --project-id PVT_kwHOA9Rkqc4BW2VV --id "$ITEM_ID" \
    --field-id PVTSSF_lAHOA9Rkqc4BW2VVzhSHWXM \
    --single-select-option-id 47fc9ee4
  ```
- [ ] Project ID and option IDs resolved via name lookup, not hardcoded (same pattern as `file.sh`).
- [ ] No commit to main from the agent. The board update is API-only. No file changes.
- [ ] Remove the `gh issue edit --add-label in-progress` line — that label no longer exists.

### G. Rewrite Step 8b of `docs/AGENTS.md`

- [ ] Remove "move ticket from In progress 🚧 to In review 👀 in STATE.md" — STATE.md doesn't exist.
- [ ] Remove "Status: IN_PROGRESS → Status: IN_REVIEW" in the ticket file edit. The Status line in ticket files is decorative; nothing reads it.
- [ ] Step 8b is now: nothing. Skip it. Step 8 collapses to: 8a commit code, 8b push.
- [ ] **New Step 8c:** after push, move the board item to `In review`:
  ```bash
  ITEM_ID=$(gh project item-list 2 --owner @me --format json --limit 100 | jq -r '.items[] | select(.content.number==<issue-num>) | .id')
  gh project item-edit --project-id PVT_kwHOA9Rkqc4BW2VV --id "$ITEM_ID" \
    --field-id PVTSSF_lAHOA9Rkqc4BW2VVzhSHWXM \
    --single-select-option-id df73e18b
  ```

### H. Rewrite Step 2 of `docs/AGENTS.md`

- [ ] Remove all STATE.md reconciliation logic (no `sync_state.py`, no manual STATE.md edits).
- [ ] New Step 2: query the board. For each item in `In review` column, check if its linked issue is closed. If so, move the item to `Done`. This is defense-in-depth — the post-merge action should already have done this.
- [ ] If everything in `In review` is still open, no action needed.

### I. Update `docs/AGENTS.md` Required Reading

- [ ] Remove `docs/STATE.md` from the required reading list. CONTEXT.md (which now sources from the board) replaces it.
- [ ] Required reading is now: CONTEXT.md, METHODOLOGY.md, ARCHITECTURE.md, plus the ticket file and any module-specific instruction files.

### J. Update `docs/METHODOLOGY.md`

- [ ] **The ticket lifecycle section:** rewrite to reference board columns, not Status text:
  ```
  Backlog → Ready → In progress → In review → Done
  ```
- [ ] Remove the table showing who sets each Status transition. Replace with: "All transitions are managed by the agent or by the post-merge GitHub Action. Vivek's only direct touchpoint is dragging cards between Backlog and Ready on the project board."
- [ ] **The chat handoff protocol section:** rewrite the Standard Handoff Bundle:
  - Chat outputs one `.md` file per ticket (or multiple `.md` files if drafting a batch).
  - Vivek saves each file to `docs/TICKETS/`.
  - Vivek runs `bash tools/file.sh` once. Done.
  - Remove the heredoc + `cat | bash tools/draft_ticket.sh` pattern entirely.
  - Remove the `POSITION:` field documentation.
  - Remove the `tools/draft_ticket.sh` spec format (`ID: ... TITLE: ...` headers). All metadata is now inside the ticket body via the existing `# TICKET-XXX — Title` heading and `**Priority:**` / `**Milestone:**` lines.
- [ ] **The ticket file format example:** confirm it shows `# TICKET-XXX — Title` heading and `**Priority:**`, `**Milestone:**` lines. Add `**Milestone:**` to the example if it's not already there.
- [ ] **Anti-patterns:** add: "Editing STATE.md by hand — STATE.md does not exist. Edit the project board instead." (Remove the existing STATE.md hand-edit anti-pattern; it's now obsolete.)
- [ ] **Anti-patterns:** add: "Writing scripts that mutate the project board outside `file.sh` and the agent's Step 5/8c/Step 0 drop handler. Board state is touched by these three places only."

### K. Update `docs/VIVEK.md`

Rewrite the whole file for the new workflow. Keep it under 200 lines.

- [ ] **Section 1 — Drafting a ticket (in chat):** unchanged in spirit, but: chat now outputs `.md` files only. No heredoc shell blocks.
- [ ] **Section 2 — Filing a ticket(s) (terminal):**
  ```
  1. Save the .md file(s) chat gave you to docs/TICKETS/
  2. Run: bash tools/file.sh
  3. Done. Issues created, board updated, commit pushed.
  ```
- [ ] **Section 3 — Implementing a ticket (Claude Code):** update menu format to match the new Step 0 (Ready/Backlog grouped, `reorder` opens browser).
- [ ] **Section 4 — Reviewing the PR:** unchanged.
- [ ] **Section 5 — After merge:** "GitHub Action moves the card to Done and regenerates CONTEXT.md. You do nothing."
- [ ] **Section 6 — Reordering:** new section. "To reorder tickets, drag cards on https://github.com/users/vivekbhargava23/projects/2. The agent's `next` menu reflects board order. No script needed."
- [ ] **Section 7 — Edge-case cheat sheet:** update for new tooling.
- [ ] **Section 8 — What you NEVER do:**
  - Edit STATE.md (it doesn't exist).
  - Edit ticket files after filing (use a follow-up ticket).
  - Run pytest, push branches, open PRs.
- [ ] **Footer cross-reference:** remove the STATE.md mention.

### L. Update `docs/ARCHITECTURE.md`

- [ ] Remove the `STATE.md` line from the `docs/` file layout listing.
- [ ] No other architecture changes.

### M. Update `README.md`

- [ ] Replace any `docs/STATE.md` reference with `docs/CONTEXT.md`.
- [ ] Add to the "Working on this project" section: "Ticket workflow is documented in `docs/VIVEK.md`. The GitHub Projects board at https://github.com/users/vivekbhargava23/projects/2 is the source of truth for ticket state and ordering."

### N. Migrate existing open issues onto the board

- [ ] For every currently open issue that is not already on the project board, add it via `gh project item-add 2 --owner @me --url <issue-url>` and set its Status:
  - If the issue has a linked open PR → `In review`
  - Otherwise → `Backlog`
- [ ] This is a one-time migration. Implement as a script `tools/migrate_to_board.sh` that the agent runs once during this ticket's implementation, then deletes (do not commit the migration script).
- [ ] For TICKET-026 (issue #64, reopened by Vivek earlier today) and TICKET-027 (issue #65): both go to `Backlog`. TICKET-026 first (lower issue number → top of Backlog by default), TICKET-027 below.

### O. Verification

- [ ] `pytest && ruff check . && mypy app/ && lint-imports` — all pass.
- [ ] **File one dummy ticket end-to-end.** Save a `docs/TICKETS/TICKET-DUMMY-test.md` with a valid body (>500 chars). Run `bash tools/file.sh`. Verify:
  - GitHub issue created
  - Issue appears on the board in `Backlog` column
  - Commit pushed to main with message `docs: file TICKET-DUMMY`
  - No errors, no STATE.md mutations
- [ ] **File two dummy tickets in one run.** Save two `.md` files, run `file.sh` once. Verify both are filed in one commit.
- [ ] **Empty body rejection.** Save a `.md` with only a heading. Run `file.sh`. Verify abort before any GitHub or git side effect.
- [ ] **Invalid filename rejection.** Save `docs/TICKETS/foo.md`. Verify rejection.
- [ ] **Branch switch.** From a feature branch, run `file.sh`. Verify it switches to main and pulls before doing anything.
- [ ] **Dirty tree rejection.** Modify a Python file (not a ticket file), run `file.sh`. Verify it refuses with a clear message naming the dirty file.
- [ ] **Menu test in Claude Code.** Open Claude Code, say `next`. Verify the menu reads from the board, shows Ready/Backlog grouped, supports `<number>` / `reorder` / `drop` / `cancel`.
- [ ] **End-to-end implementation test.** Pick a dummy ticket via the menu. Verify the agent moves its board item to `In progress`, branches, runs through to push and PR, moves the item to `In review` after PR opens. Then merge the PR and verify the post-merge action moves the item to `Done`. Clean up the dummy.
- [ ] **CONTEXT.md regeneration.** After the dummy ticket flow, verify CONTEXT.md has accurate `Up next`, `In progress`, `In review`, `Recently done` sections sourced from the board.
- [ ] **Confirm STATE.md is gone, scripts are gone.** `ls docs/STATE.md tools/draft_ticket.sh tools/update_state.py tools/sync_state.py tools/_next_up.py 2>&1` should print only "No such file" errors.
- [ ] **Grep for stale references.** `grep -rE 'STATE\.md|draft_ticket\.sh|update_state|sync_state|_next_up' docs/ tools/ .github/ README.md` — output empty except for historical ticket files in `docs/TICKETS/`.

---

## Files created

```
tools/file.sh
```

## Files modified

```
tools/regen_context.py                  (board-sourced sections, drop STATE.md inline)
.github/workflows/post-merge-housekeeping.yml   (board-only, no STATE.md)
docs/AGENTS.md                          (Step 0, Step 2, Step 5, Step 8b/8c rewrite, Required Reading)
docs/METHODOLOGY.md                     (lifecycle, handoff protocol, anti-patterns)
docs/VIVEK.md                           (full rewrite for new workflow)
docs/ARCHITECTURE.md                    (drop STATE.md from layout)
README.md                               (STATE.md → CONTEXT.md, mention board)
```

## Files deleted

```
docs/STATE.md
tools/draft_ticket.sh
tools/update_state.py
tools/sync_state.py
tools/_next_up.py
```

## Files NOT to modify

```
app/**                                  (no application changes)
tests/**                                (no test changes)
data/**                                 (no data changes)
docs/DECISIONS/**                       (no ADR changes)
docs/CONTEXT.md                         (regenerated by regen_context.py, do not hand-edit)
docs/TICKETS/**                         (historical ticket files are immutable history; only this ticket's own file may be edited)
.importlinter                           (no architecture rule changes)
pyproject.toml, environment.yml         (no new dependencies — uses gh CLI and jq, both already required)
```

---

## Out of scope

- Building a TUI or interactive picker for filing.
- Auto-generating ticket IDs (Vivek picks the ID, e.g. TICKET-028).
- Programmatic board column reordering from the agent (`reorder` opens the browser).
- Migrating closed/historical issues onto the board (only open issues are migrated in criterion N).
- Validating ticket body markdown structure beyond size + heading + Priority/Milestone fields.
- Auto-creating GitHub milestones if one is missing — script just files the issue without a milestone and warns.
- Building any abstraction over `gh` (no `gh-helpers.sh`, no Python wrapper). Direct `gh` calls only.
- Adding new tests under `tests/` for `file.sh` or the workflow tools. Tooling verification is manual (criterion O).
- Removing the post-merge action entirely. It still has a job (moving cards to Done).
- Changing branch protection rules.

---

## Implementation notes

### Why the board instead of `queue.txt` or labels

- Labels can only express category, not order. Sorting "by `high` then `medium` then `low`" doesn't let Vivek say "this `high` ticket goes before that `high` ticket."
- A `queue.txt` works but is yet another file that needs syncing with reality. The board already exists, has a UI, and is visible on Vivek's phone.
- The board is read-only from the agent's perspective for ordering. The agent only writes the Status column (which corresponds to lifecycle state). Vivek owns ordering via the drag UI.

### Why two columns for pre-implementation (`Backlog` and `Ready`)

`Backlog` is "drafted but maybe not what I want to do next." `Ready` is "I've vetted this and it's next." This matches how Vivek already uses the board — there's no point fighting the existing column structure. The agent's `next` menu shows `Ready` first, then `Backlog`, so the distinction translates naturally to picking order.

If Vivek wants to skip the distinction, he just leaves everything in Backlog. The script defaults new tickets to `Backlog`. Manual promotion to `Ready` is a drag in the browser.

### Why `file.sh` doesn't use `--milestone` if missing

Auto-creating a missing milestone would be useful but adds complexity (when do we create vs warn? what if the milestone name has a typo?). For now: warn and file without milestone. Vivek can fix the milestone later via the GitHub UI. A future ticket can add auto-create if the pain is real.

### Why `Status:` line in ticket files becomes decorative

The previous design made the agent edit the `Status:` line in the ticket file at multiple points in the ritual. This was load-bearing — `sync_state.py` and the post-merge action grepped for it. With the board as source of truth, no automation reads it. Keeping it for human readability is fine, but it's no longer part of the protocol. The decorative line should still be present in new ticket files for habit consistency, but nothing breaks if it's missing or stale.

### Why no programmatic reorder

`gh project item-edit` can set field values but not move items within a column. Column ordering is set via GraphQL mutations on the project's `items` connection, with complex `position` arguments. The browser UI does this trivially. Building a CLI wrapper is 2-3 hours of GraphQL pain for marginal value — Vivek opens the board, drags, refreshes the menu. Five seconds.

### Why migrate existing issues in criterion N (not a separate ticket)

The board needs to be the source of truth on Day 1. If there are open issues not on the board, the agent's `next` menu can't see them. Migrating in a separate ticket means there's a window where the workflow is partially broken. Doing it inline as a one-time script keeps the cutover atomic.

### Why post-merge action keeps existing despite shrinking

It still moves cards to `Done` (issue close from PR merge doesn't auto-move the card). It still triggers CONTEXT.md regen. Removing the action would leave those gaps. Shrinking it is fine.

### Why the agent doesn't manage `Ready` column

`Ready` is Vivek's curated "what I actually want to do next." Letting the agent put things in `Ready` defeats the purpose. The agent files new tickets to `Backlog` (via `file.sh`) and moves picked tickets out of `Ready`/`Backlog` to `In progress`. Promotion `Backlog` → `Ready` is Vivek's manual judgment.

### Why `gh` and `jq`, no Python

`tools/file.sh` is bash because the operations are sequential `gh` calls with simple JSON extraction. Python would buy nothing. The deleted `tools/*.py` files were Python because they did complex state mutation on STATE.md — that's gone. `jq` is already required by the GitHub Actions workflows; it's available on macOS via brew and on Ubuntu by default.

### What if `gh project` rate-limits during `file.sh`

Filing 5 tickets is ~15 `gh` calls. GitHub's rate limit for authenticated API calls is 5000/hour. Rate limit is not a realistic concern. If it happens, the script exits with the `gh` error and Vivek waits an hour or runs again with the remaining tickets.

### Why this is HIGH priority

The current workflow is unusable. Three hours lost in one filing session. Two tickets silently corrupted. The next time Vivek tries to file a ticket, the same bugs are still there. Until M5 is merged, every filing attempt risks the same failures.

### Risk: this ticket touches a lot

Yes. The blast radius is intentional. The current pain is a tangle of tooling that all has to come out together — partial removal would leave inconsistencies that produce *new* failure modes. The agent should resist any temptation to land partial progress. Either the whole thing works end-to-end, or the PR is not ready.

### Recovery if this ticket fails mid-implementation

If the agent gets stuck and can't complete the ticket, `git reset --hard origin/main` undoes everything. The current (broken) workflow continues to limp along. No data loss — GitHub issues, the board, and CONTEXT.md are all untouched by a failed local implementation.

### Confirm before starting

The agent's first action in this ticket's session should be to verify:
1. `gh project list --owner @me` returns project #2 with ID `PVT_kwHOA9Rkqc4BW2VV`
2. `gh project field-list 2 --owner @me` shows the Status field with ID `PVTSSF_lAHOA9Rkqc4BW2VVzhSHWXM`
3. The five Status options exist with the IDs documented above

If any of these don't match, stop and report. The board may have been edited between ticket drafting and implementation.
