# VIVEK.md — Vivek's quick reference

> If you're Vivek (or future maintainer): this is your single-page cheat sheet. Anything in more detail lives in `AGENTS.md` or `METHODOLOGY.md`, but you should rarely need them. This file describes the entire workflow from your side.

---

## Section 1 — Drafting a ticket (in chat)

1. Open a chat in the Projects folder.
2. `docs/CONTEXT.md` is already there — auto-synced from main on every merge. Chat reads it. You don't need to paste anything else most of the time.
3. Describe what you want.
4. For UI changes, share a screenshot or page description when chat asks. (Chat will require this per the verification protocol.)
5. Chat verifies its assumptions, asks clarifying questions if needed, then outputs one `.md` file per ticket. No shell blocks. No heredocs. Just the file.

---

## Section 2 — Filing a ticket (terminal)

1. Save the `.md` file(s) chat gave you to `docs/TICKETS/`.
2. Run: `bash tools/file.sh`
3. Done. Issues created, board updated, commit pushed.

If the script errors, paste the error back into chat. You don't debug it.

---

## Section 3 — Implementing a ticket (Claude Code)

1. `cd ~/Desktop/Apps/Investment-Dashboard-2`  (or any existing ticket worktree)
2. `claude` (or `codex`, `aider`, `gemini`)
3. Say `next` to see the menu, or `implement TICKET-XXX` to jump in.
4. PR shows up. Review and merge.

You no longer create worktrees or activate conda by hand — the agent does both. To clean up local worktrees of merged tickets: `bash tools/cleanup-worktrees.sh` (safe to run any time; safe to run never).

All worktrees share the main checkout's `data/` directory automatically (per ADR-011). Upload the CSV once in main; every worktree sees it. The agent handles the symlinking.

To start three tickets in parallel: open three terminals, run steps 1–3 in each, pick different ticket IDs in each. Three PRs come back.

---

## Section 4 — Reviewing the PR

1. Open the PR URL the agent printed.
2. Re-read the ticket file. Read the diff. Run the Streamlit app if the change is user-visible. Screenshot if relevant.
3. Merge if good. Comment on the PR if not — agent picks up review comments next session via `address PR review comments on TICKET-XXX`.

---

## Section 5 — After merge

GitHub Action handles housekeeping: the board card moves to Done and CONTEXT.md regenerates. You do nothing. Next session is ready.

---

## Section 6 — Reordering tickets

To change the order tickets appear in the `next` menu:

1. Go to: https://github.com/users/vivekbhargava23/projects/2
2. Drag cards within the `Ready` or `Backlog` columns.
3. Re-run `next` in Claude Code — the menu reflects the new order.

To promote a ticket from Backlog to Ready (so it appears first in the menu): drag it to the `Ready` column.

No script needed. The agent never reorders cards programmatically.

---

## Section 7 — Edge-case cheat sheet

- **Agent stops mid-ritual** → read the stop reason, file a hotfix ticket in a new chat if needed.
- **PR needs changes** → comment on GitHub, then say `address PR review comments on TICKET-XXX` in a new Claude Code session.
- **You find a bug after merge** → file a new ticket in chat.
- **Board looks stale** → Action updates it on every merge. If still stale, it's a tooling bug — file a ticket.
- **You want to drop a ticket entirely** → say `next`, then `drop N`. Agent confirms, closes issue, moves card to Done.
- **You want to pick a specific ticket** → say `implement TICKET-XXX` directly.

---

## Section 8 — What you NEVER do

- Edit ticket files after filing (use a follow-up ticket if the spec needs changing).
- Edit STATE.md — it doesn't exist. The board is the source of truth.
- Run `pytest`, push branches, or open PRs yourself.
- Coach the agent through code edits in the same session.

---

## Cross-reference

`AGENTS.md` is the agent's rulebook. `METHODOLOGY.md` is the why. `ARCHITECTURE.md` is the code layer rules. `CONTEXT.md` is the auto-generated repo snapshot sourced from the board and GitHub.
