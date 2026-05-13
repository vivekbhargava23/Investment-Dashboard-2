# VIVEK.md — Vivek's quick reference

> If you're Vivek (or future maintainer): this is your single-page cheat sheet. Anything in more detail lives in `AGENTS.md` or `METHODOLOGY.md`, but you should rarely need them. This file describes the entire workflow from your side.

---

## Section 1 — Drafting a ticket (in chat)

1. Open a chat in the Projects folder.
2. `docs/CONTEXT.md` is already there — auto-synced from main on every merge. Chat reads it. You don't need to paste anything else most of the time.
3. Describe what you want.
4. For UI changes, share a screenshot or page description when chat asks. (Chat will require this per the verification protocol.)
5. Chat verifies its assumptions, asks clarifying questions if needed, then outputs a `.md` ticket file and a shell block.

---

## Section 2 — Filing a ticket (terminal)

1. Save the `.md` file to `docs/TICKETS/` (chat tells you the filename).
2. Paste the shell block into your terminal. Hit enter.
3. Script writes the ticket file, creates the GitHub issue, appends to `STATE.md` "Up next," commits, pushes.
4. If the script errors, paste the error back into chat. You don't debug it.

---

## Section 3 — Implementing a ticket (Claude Code)

1. Say `next`.
2. Agent reads `docs/STATE.md` "Up next" and shows you a numbered menu:

   ```
   Up next (N tickets queued):

   1. TICKET-XXX — Short title [HIGH]
   2. TICKET-YYY — Another title [MEDIUM]

   Reply with:
     <number>           pick a ticket and start implementing
     reorder N,M,K      rearrange the list (I'll re-present)
     drop N             close that ticket (marks issue "not planned", removes from list)
     cancel             do nothing
   ```

3. Reply with a number. Agent does the rest: branch, code, tests, commits, push, PR.
4. Alternative: say `implement TICKET-XXX` to skip the menu.

---

## Section 4 — Reviewing the PR

1. Open the PR URL the agent printed.
2. Re-read the ticket file. Read the diff. Run the Streamlit app if the change is user-visible. Screenshot if relevant.
3. Merge if good. Comment on the PR if not — agent picks up review comments next session via `address PR review comments on TICKET-XXX`.

---

## Section 5 — After merge

GitHub Action handles housekeeping: ticket file status → MERGED, STATE.md "Recent activity" updated, CONTEXT.md regenerated. You do nothing. Next session is ready.

---

## Section 6 — Edge-case cheat sheet

- **Agent stops mid-ritual** → read the stop reason, file a hotfix ticket in a new chat if needed.
- **PR needs changes** → comment on GitHub, then say `address PR review comments on TICKET-XXX` in a new Claude Code session.
- **You find a bug after merge** → file a new ticket in chat.
- **STATE.md looks stale** → re-read it; Action updates it on every merge. If still stale, it's a tooling bug — file a ticket.
- **You want to do tickets out of order** → say `next`, then use `reorder N,M,K` in the menu.
- **You want to drop a ticket entirely** → say `next`, then `drop N`. Agent confirms, closes issue, removes from list.

---

## Section 7 — What you NEVER do

- Edit `STATE.md`, ticket files, or `Status:` lines by hand.
- Run `pytest`, push branches, or open PRs yourself.
- Coach the agent through code edits in the same session.

---

## Cross-reference

`AGENTS.md` is the agent's rulebook. `METHODOLOGY.md` is the why. `ARCHITECTURE.md` is the code layer rules. `CONTEXT.md` is the auto-generated repo snapshot. `STATE.md` is what's next, what's recent, and what the project is.
