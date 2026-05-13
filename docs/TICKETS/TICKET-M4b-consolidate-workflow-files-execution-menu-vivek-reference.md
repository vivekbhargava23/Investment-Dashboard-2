# TICKET-M4b — Consolidate workflow files, execution-time menu, Vivek quick-reference

**Status:** MERGED
**Priority:** HIGH
**Estimated session length:** 3 – 3.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-13)
**Implemented by:** Claude Code (session TBD)
**Depends on:** TICKET-M4a merged (CONTEXT.md auto-generation must exist before this ticket reshuffles state files)

## Problem

The current doc layout has grown to seven workflow-related files (PROJECT_STATE, BACKLOG, SESSION_LOG, WORKFLOW, METHODOLOGY, AGENTS, ARCHITECTURE), several of which contain overlapping or duplicated state:

- BACKLOG.md duplicates ticket file status + PROJECT_STATE's "Done" + "Next up"
- SESSION_LOG.md duplicates information already in PR descriptions and git log
- WORKFLOW.md exists because METHODOLOGY.md grew dense; it duplicates the chat handoff protocol and the agent ritual at a higher level

The duplication causes drift. M3 mostly solved post-merge drift via GitHub Actions, but the underlying problem — too many files holding the same state — remains. Vivek currently cannot answer "what do I do next?" from a single file.

A second pain point: execution-time inflexibility. Today, `next` resolves via the `next-up` GitHub label, which is set at draft time. If Vivek drafts A1, A2, A3 in that order but on the day wants to do A1 → A3 → A2, he has to manually edit PROJECT_STATE and flip labels. The natural moment to choose what to work on is when sitting down to work, not when drafting.

A third pain point: Vivek genuinely cannot keep up with the workflow churn. Each ticket has introduced small changes. There is no single Vivek-facing reference he can consult to know "what do I paste / say / do, end to end." WORKFLOW.md was supposed to be that, but it's now stale relative to M1 / M2 / M3 / and what this ticket is about to do.

This ticket:

1. **Consolidates state files.** Renames PROJECT_STATE.md → STATE.md and folds in BACKLOG-equivalent visibility (via auto-generated CONTEXT.md from M4a). Deletes BACKLOG.md, SESSION_LOG.md, WORKFLOW.md.
2. **Replaces the `next-up` label with an execution-time numbered menu.** Agent reads STATE.md "Up next" and presents options. Vivek picks by number. Out-of-order execution becomes natural. Reorder and drop become single commands.
3. **Auto-maintains STATE.md "Up next".** `draft_ticket.sh` appends on creation. Agent removes on pick. Action removes on merge if still present.
4. **Adds `VIVEK.md`** — a single short reference Vivek consults to know what he does, end to end. Stable across future workflow changes (those go in AGENTS.md / METHODOLOGY.md, not here).

## Acceptance criteria

### A. Rename and consolidate state files

- [ ] Rename `docs/PROJECT_STATE.md` → `docs/STATE.md`.
- [ ] Update all references to `PROJECT_STATE.md` across the repo to `STATE.md`. Use `grep -r 'PROJECT_STATE' .` to find them all. Common locations:
  - `docs/AGENTS.md` (Required reading, Step 2, Step 8b)
  - `docs/METHODOLOGY.md` (multiple places)
  - `docs/ARCHITECTURE.md` (if any)
  - `tools/sync_state.py` (regex section headers, file path)
  - `tools/draft_ticket.sh` (paths)
  - `.github/workflows/post-merge-housekeeping.yml` (paths)
  - `tools/regen_context.py` (from M4a — currently reads STATE.md or falls back to PROJECT_STATE.md; the fallback can now be removed)
  - `README.md`
  - Any ticket file that references PROJECT_STATE by name (don't rewrite historical ticket files; only edit current docs and tooling)
- [ ] STATE.md gains a "Recent activity" section (positioned between "Up next" and "Context"). The Action will append to this on merge (see criterion E). For now, seed it with the last 5 merges from BACKLOG.md before deleting BACKLOG.
- [ ] STATE.md "Up next" section becomes the **single authoritative list**. Remove "Next up" from BACKLOG.md before deleting BACKLOG.md (no-op since BACKLOG is being deleted).
- [ ] Delete `docs/BACKLOG.md`. Equivalent visibility is provided by CONTEXT.md (open issues + recent merges) + STATE.md (up next + recent activity) + `docs/TICKETS/*.md` (per-ticket specs).
- [ ] Delete `docs/SESSION_LOG.md`. Equivalent visibility is provided by git log + PR descriptions + STATE.md "Recent activity".
- [ ] Delete `docs/WORKFLOW.md`. Replaced by `docs/VIVEK.md` (see criterion F).
- [ ] In `docs/METHODOLOGY.md`, **delete** the SESSION_LOG.md entry template. **Update** any reference to BACKLOG.md to point to either STATE.md (for next-up steering) or CONTEXT.md (for full ticket list).
- [ ] In `docs/METHODOLOGY.md`, delete the "Starting a new chat session (the handoff)" section. CONTEXT.md replaces this entirely — chat just reads CONTEXT.md, no paste required.

### B. Remove the `next-up` GitHub label

- [ ] Delete the `next-up` label from the repo: `gh label delete next-up --yes`. (If the label has any open issues attached, remove it from them first via `gh issue edit --remove-label next-up` per issue.)
- [ ] Remove all references to `next-up` label in tooling:
  - `tools/draft_ticket.sh` — remove the `NEXT_UP=true` handling and the `gh issue edit --add-label next-up` call.
  - `docs/AGENTS.md` Step 0 — rewrite (see criterion C).
  - `docs/AGENTS.md` Step 5 — remove `--remove-label next-up` from the `gh issue edit` call.
  - `docs/METHODOLOGY.md` chat handoff protocol — remove the `NEXT_UP=true/false` field from the spec format.
- [ ] Document the deletion in the ticket's PR description.

### C. New execution-time menu (rewrite AGENTS.md Step 0)

Rewrite Step 0 of the agent ritual in `docs/AGENTS.md`. The new Step 0:

- [ ] **Trigger:** Vivek says `next` (or `implement next ticket`).
- [ ] **Action:** Agent reads `docs/STATE.md` "Up next" section, parses the ordered list, and presents to Vivek as a numbered menu. Each entry shows ticket ID, one-line title, and priority label.
- [ ] **Menu format example:**

  ```
  Up next (3 tickets queued):
  
  1. TICKET-C2 — Company Deep Dive page and Snapshot tab [HIGH]
  2. TICKET-XYZ — Panel framework brainstorm scaffolding [MEDIUM]
  3. TICKET-ABC — Performance page timeframe toggle [LOW]
  
  Reply with:
    <number>           pick a ticket and start implementing
    reorder N,M,K      rearrange the list (then I'll re-present)
    drop N             close ticket #N (marks issue "not planned", removes from list)
    cancel             do nothing
  ```

- [ ] **On `<number>`:** agent proceeds to Step 1 (clean main) with that ticket. Step 5 will remove the ticket from STATE.md "Up next" as part of the standard label-flip commit (see criterion D).
- [ ] **On `reorder N,M,K`:** agent rewrites STATE.md "Up next" in the new order, commits directly to main with message `chore: reorder up-next per Vivek`, pushes, re-presents the menu.
- [ ] **On `drop N`:** agent confirms with Vivek ("Drop TICKET-XXX? This closes the issue and removes it from Up next."), and on confirmation:
  1. `gh issue close <N> --reason "not planned"`
  2. Removes from STATE.md "Up next"
  3. Updates the ticket file's `Status:` line to `CLOSED`
  4. Commits to main with `chore: drop TICKET-XXX per Vivek`
  5. Pushes
  6. Re-presents the menu.
- [ ] **On `cancel`:** agent stops the session. No state changes.
- [ ] **Edge case: STATE.md "Up next" is empty.** Agent shows: "No tickets in Up next. Run `gh issue list --label queued --state open` to see queued tickets not in the suggested order, or draft a new ticket in chat." Agent stops.
- [ ] **Edge case: STATE.md "Up next" references an issue that's already CLOSED or doesn't exist.** Agent flags the entry as `[INVALID — issue closed/missing]` in the menu but still allows other selections. After the picked ticket completes, the invalid entry remains for Vivek to clean up via `drop`.
- [ ] **Override:** If Vivek says `implement TICKET-XXX` instead of `next`, skip the menu entirely. Proceed to Step 1 with that ticket. Step 5 still removes the ticket from STATE.md "Up next" if present.

### D. Agent Step 5 update — remove picked ticket from "Up next"

- [ ] In `docs/AGENTS.md` Step 5, after the branch creation and `gh issue edit --remove-label queued --add-label in-progress`, add: "Edit `docs/STATE.md` to remove this ticket from `Up next`. Commit to main as `chore: pick TICKET-XXX, remove from Up next`, push. Then return to the working branch."
- [ ] Rationale: Step 5 already commits the in-progress label flip to GitHub. The STATE.md update is paired with it — if you pick a ticket, it leaves "Up next" immediately, so a parallel chat session won't see it as still available.
- [ ] The commit author is the agent (not the bot). This is one of the few places where the agent writes directly to main; branch protection must permit this. If branch protection rejects, the agent stops and reports.

### E. `tools/draft_ticket.sh` update — auto-append to "Up next"

- [ ] Remove the `NEXT_UP=true/false` field handling (per criterion B).
- [ ] Add: after creating the ticket file and the GitHub issue, append a line to `docs/STATE.md` "Up next" section at the end of the list. Line format: `N. TICKET-XXX — <title> [<priority>]` where N is the next sequential number.
- [ ] Optional: if the spec contains a `POSITION=N` field, insert at position N instead of appending. If `POSITION` is absent or invalid, default to append.
- [ ] After the ticket file is written, the issue is created, BACKLOG row is added (wait — BACKLOG is being deleted in this ticket, so the script's existing BACKLOG update step also gets removed), and STATE.md is updated, commit and push as usual.
- [ ] Update `tools/update_backlog.py` — either delete it (BACKLOG is gone) or repurpose into `tools/update_state.py` if it isn't already that. Check the current state of the tools/ directory and pick the right action.

### F. New file: `docs/VIVEK.md` — Vivek-facing quick reference

This is the single short reference Vivek consults to know what to do, end to end. Style: imperative, second-person, dense. No rationale. No anti-patterns. Just "what you do."

Content:

- [ ] Top-of-file note: "If you're Vivek (or future maintainer): this is your single-page cheat sheet. Anything in more detail lives in AGENTS.md or METHODOLOGY.md, but you should rarely need them. This file describes the entire workflow from your side."
- [ ] **Section 1 — Drafting a ticket (in chat)**
  - Open a chat in the Projects folder.
  - Note: `docs/CONTEXT.md` is already there (auto-synced from main). Chat reads it. You don't need to paste anything else most of the time.
  - Describe what you want.
  - For UI changes, share a screenshot or page description when chat asks. (Per verification protocol from M4a, chat will require this.)
  - Chat verifies its assumptions, asks clarifying questions if needed, then outputs a `.md` ticket file + one shell block.
- [ ] **Section 2 — Filing a ticket (terminal)**
  - Save the `.md` file (chat tells you where).
  - Paste the shell block into your terminal. Hit enter.
  - Script writes the ticket, creates the GitHub issue, appends to STATE.md "Up next," commits, pushes.
  - If the script errors, paste the error back into chat. You don't debug it.
- [ ] **Section 3 — Implementing a ticket (Claude Code)**
  - Say `next`.
  - Agent shows you a numbered menu from STATE.md "Up next" with these commands:
    - `<number>` — pick that ticket and implement it
    - `reorder N,M,K` — change the order, agent re-presents the menu
    - `drop N` — close that ticket without implementing
    - `cancel` — do nothing
  - Pick a number. Agent does the rest (branch, code, tests, commits, push, PR).
  - Alternative: say `implement TICKET-XXX` to skip the menu.
- [ ] **Section 4 — Reviewing the PR**
  - Open the PR URL the agent printed.
  - Re-read the ticket file. Read the diff. Run the Streamlit app. Screenshot if user-visible.
  - Merge if good. Comment on PR if not — agent picks up review comments in next session via `address PR review comments on TICKET-XXX`.
- [ ] **Section 5 — After merge**
  - GitHub Action handles housekeeping (ticket file status, STATE.md "Recent activity," CONTEXT.md regenerated).
  - You do nothing. Next session is ready to start.
- [ ] **Section 6 — Edge-case cheat sheet (5–10 lines)**
  - Agent stops mid-ritual → read the stop reason, file a hotfix ticket in a new chat if needed.
  - PR needs changes → comment on GitHub, then say `address PR review comments on TICKET-XXX` in a new Claude Code session.
  - You find a bug after merge → file a new ticket in chat.
  - STATE.md looks stale → re-read it; Action updates it on every merge. If still stale, it's a tooling bug — file a ticket.
- [ ] **Section 7 — What you NEVER do**
  - Edit STATE.md, BACKLOG.md, ticket files, or `Status:` lines by hand.
  - Run pytest, push branches, open PRs.
  - Coach the agent through code edits in the same session.
- [ ] **Footer:** one-paragraph cross-reference: "AGENTS.md is the agent's rulebook. METHODOLOGY.md is the why. ARCHITECTURE.md is the code layer rules. CONTEXT.md is the auto-generated repo snapshot. STATE.md is what's next, what's recent, and what the project is."

VIVEK.md should fit on one screen at default font (≤200 lines). If it doesn't, it's too long.

### G. Update `.github/workflows/post-merge-housekeeping.yml`

- [ ] Append to STATE.md "Recent activity" section on every merge. One line per merge: `- YYYY-MM-DD — TICKET-XXX merged (PR #N)`.
- [ ] Keep "Recent activity" to the most recent 10 entries (delete older lines on each run, or accept unbounded growth — your call, but bounded is cleaner). Recommendation: bounded.
- [ ] Remove the merged ticket from STATE.md "Up next" if it's still present there (defense in depth; Step 5 should already have removed it).
- [ ] All other existing housekeeping (ticket file status → MERGED, "In review" → "Done ✓" or now directly to "Recent activity," "Last updated" line) — keep.
- [ ] Update the workflow's commit message: `chore: post-merge housekeeping for TICKET-XXX (#N) [skip ci]` — same pattern as today.

### H. Update `.github/workflows/update-context.yml` (from M4a)

- [ ] Confirm it runs *after* `post-merge-housekeeping.yml` so CONTEXT.md regenerates against the final post-merge state. If currently configured by trigger only (`push: branches: main`), this happens naturally because housekeeping commits its update to main, which triggers update-context.yml. Verify this chain works.

### I. Update `README.md`

- [ ] "Working on this project" section: replace any reference to WORKFLOW.md with VIVEK.md. Keep it to one paragraph: *"If you're Vivek (or any future maintainer), start with `docs/VIVEK.md`. It's a one-page reference covering the entire workflow."*
- [ ] Confirm the M4a addition ("For chat sessions: CONTEXT.md is automatically available...") is still present.

### J. Verification

- [ ] `pytest && ruff check . && mypy app/ && lint-imports` — all pass.
- [ ] `grep -rE 'PROJECT_STATE|BACKLOG\.md|SESSION_LOG|WORKFLOW\.md|next-up' docs/ tools/ .github/ README.md` — output must be empty (modulo this ticket's own description in `docs/TICKETS/`). Any leftover reference is a bug.
- [ ] STATE.md "Up next" section parses correctly. Manually run a dry-run of the menu logic against the current STATE.md and confirm it produces a valid numbered list.
- [ ] Run `tools/draft_ticket.sh` with a dummy spec (e.g. `TICKET-DUMMY` with `MILESTONE=Workflow & tooling`, `PRIORITY=LOW`). Confirm:
  - The ticket file is created.
  - The GitHub issue is created.
  - STATE.md "Up next" gets a new appended line.
  - BACKLOG.md is NOT touched (because it doesn't exist anymore).
  - The script does NOT reference or set the `next-up` label.
  - Clean up the dummy ticket and issue after the test.
- [ ] Open a fresh Claude Code session in a sandbox branch. Say `next`. Verify the menu appears with at least the seed entries from STATE.md. Try `reorder` and `drop` against fake entries to confirm the flow works. Roll back any test changes before merging this ticket's PR.
- [ ] Confirm `gh label list` no longer shows `next-up`.
- [ ] Read `docs/VIVEK.md` end-to-end. Time yourself — it should take under 5 minutes. If longer, tighten it.

## Files likely touched

### New files
- `docs/STATE.md` (renamed from PROJECT_STATE.md)
- `docs/VIVEK.md` (new)

### Edited
- `docs/AGENTS.md` — Step 0 rewrite (menu), Step 5 addition (remove from Up next), Required Reading swap
- `docs/METHODOLOGY.md` — delete SESSION_LOG template, update BACKLOG refs, delete "starting new chat" section, drop NEXT_UP from handoff spec format
- `docs/ARCHITECTURE.md` — only if it references any of the deleted files; otherwise untouched
- `tools/draft_ticket.sh` — remove NEXT_UP handling, remove BACKLOG update, add STATE.md Up next append
- `tools/sync_state.py` (or `tools/update_backlog.py` or whatever current naming) — rename / update / delete as appropriate
- `.github/workflows/post-merge-housekeeping.yml` — append to Recent activity, remove from Up next
- `README.md` — VIVEK.md link, retain CONTEXT.md note

### Deleted
- `docs/PROJECT_STATE.md` (moved to STATE.md)
- `docs/BACKLOG.md`
- `docs/SESSION_LOG.md`
- `docs/WORKFLOW.md`

### NOT touched
- `app/**`
- `tests/**`
- `docs/TICKETS/**` (historical ticket files are immutable history)
- `docs/DECISIONS/**`
- `tools/regen_context.py` (from M4a — only the fallback-to-PROJECT_STATE branch should be removed; otherwise leave alone)

## Out of scope

- Migrating historical ticket files to update references to deleted docs (PROJECT_STATE / BACKLOG / SESSION_LOG / WORKFLOW). Old ticket files keep their original wording.
- Compressing or rewriting METHODOLOGY.md beyond the specific deletions called out. (METHODOLOGY trim is a separate ticket if Vivek wants it later.)
- Adding new GitHub labels beyond what already exists.
- Changing the chat handoff bundle structure beyond removing the `NEXT_UP` field.
- Building any MCP integration.
- Re-doing the post-merge housekeeping workflow from scratch. Edits only.

## Test cases

1. **End-to-end smoke test.** With CONTEXT.md from M4a in place: open a fresh chat in Projects. Without pasting anything, ask chat to draft a small ticket (e.g. "rename one helper function in app/ui/format.py to be more descriptive"). Chat should produce a viable Standard Handoff Bundle using CONTEXT.md alone. If chat asks for files it should already see in CONTEXT.md, the workflow has a gap.
2. **Menu interaction smoke test.** In a Claude Code sandbox, simulate STATE.md with 3 fake entries. Say `next`. Verify menu. Try `reorder 3,1,2`. Verify reorder. Try `drop 2`. Verify drop closes the (fake) issue and updates state. Try `cancel`. Verify session ends cleanly.
3. **Filing-new-ticket test.** Draft a real ticket in chat. File it via `draft_ticket.sh`. Confirm the ticket file lands in `docs/TICKETS/`, the issue is created, STATE.md "Up next" gets the new entry, no BACKLOG.md update is attempted, no `next-up` label is touched.
4. **VIVEK.md read-through test.** A new reader (not Vivek) reads VIVEK.md cold. They should be able to articulate the four touchpoints (draft → file → implement → review-and-merge) without re-reading. If they need to re-read or check AGENTS.md, VIVEK.md is unclear.
5. **No-stale-references test.** Grep for deleted file names across the whole repo. Should return only matches inside `docs/TICKETS/*.md` (historical specs) and `docs/SESSION_LOG.md` if it still exists for historical reasons — but it doesn't, so any match outside historical tickets is a bug.

## Notes

### Why this is HIGH priority

The workflow churn from M1 / M2 / M3 has solved real problems but accumulated complexity. Vivek has explicitly said he can't keep up with all the changes. VIVEK.md plus the consolidated layout closes that gap. The execution-time menu solves the "I want to do A3 before A2" friction directly.

### Implementation order within the session

The agent should do this in roughly the following order to keep each commit coherent:

1. Create VIVEK.md (it's a standalone new file; can be done first to set the target for the rest).
2. Rename PROJECT_STATE.md → STATE.md and update all internal references (one commit: `refactor: rename PROJECT_STATE.md to STATE.md`).
3. Delete BACKLOG.md, SESSION_LOG.md, WORKFLOW.md and update references (one commit: `refactor: delete consolidated state files`).
4. Update `tools/draft_ticket.sh` and related scripts (one commit: `feat: draft_ticket.sh updates STATE.md instead of BACKLOG`).
5. Update AGENTS.md (Step 0, Step 5) and METHODOLOGY.md (deletions, handoff format) (one commit: `docs: agent menu flow and methodology consolidation`).
6. Update `post-merge-housekeeping.yml` (one commit: `ci: post-merge appends to Recent activity`).
7. Update README.md and link VIVEK.md (one commit: `docs: link VIVEK.md from README`).
8. Run all verification steps from criterion J.
9. Open the PR.

### Branch-protection consideration

Step 5 of the agent ritual now writes to main (to remove a ticket from STATE.md "Up next" when picked). The `chore: reorder` and `chore: drop` commits also write to main. The current branch protection rule must permit the agent (not just `github-actions[bot]`) to push to main when these specific operations occur, OR these operations must go through tiny auto-merged PRs.

**Recommendation:** allow agent pushes to main for these specific commits (`chore: pick`, `chore: reorder`, `chore: drop`) by configuring branch protection with a bypass for the agent's authenticated user. If branch protection doesn't support per-author bypass cleanly, fall back to the tiny-PR pattern: agent opens a PR with the state change, the post-merge workflow auto-merges it (with a label like `auto-merge`). This is heavier but works with strict branch protection.

The agent should confirm with Vivek which approach is in place before starting. If unclear, default to the tiny-PR pattern — it's safer.

### What if M4a hasn't been merged yet?

This ticket depends on CONTEXT.md existing. Step 1 of the implementation session must verify `docs/CONTEXT.md` exists on main before proceeding. If not, stop and tell Vivek M4a needs to merge first.

### Files NOT to modify

To prevent scope creep:
- Any file under `app/`, `tests/`, `data/`, `docs/DECISIONS/`, `docs/TICKETS/` (historical files only — this ticket's own file is fine to edit)
- `tools/regen_context.py` beyond removing the PROJECT_STATE fallback
- Any ADR

If the agent feels it needs to edit any of these, stop and ask.

### One genuine open question for Vivek

The drop flow closes a GitHub issue with reason "not planned." This is essentially marking the ticket SUPERSEDED or CLOSED-WITHOUT-MERGING. The ticket file's `Status:` line gets updated to `CLOSED`. Question: should there be a separate option to mark as `SUPERSEDED` (with reference to the replacement ticket) vs `CLOSED` (no replacement)?

**Default if Vivek doesn't specify:** treat all drops as CLOSED. SUPERSEDED stays a manual operation (rare enough that it doesn't need a menu shortcut). The ticket can revisit this later if SUPERSEDED becomes frequent.
