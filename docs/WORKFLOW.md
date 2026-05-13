# WORKFLOW.md — Vivek's day-to-day guide

This file is for you, Vivek. It answers one question: what do you actually do on this project, day to day? It is written in second person and stays at the recipe level — what to do and what to expect, not why the system was designed this way.

For adjacent questions, the right docs are:
- **AGENTS.md** — what the implementation agent does (not your concern)
- **METHODOLOGY.md** — conventions, anti-patterns, the rationale behind the workflow
- **ARCHITECTURE.md** — code structure and layer rules
- **PROJECT_STATE.md** — current ticket status (paste this into a new chat to give context)

---

## Section 1 — The four touchpoints

Your involvement in each ticket is exactly four steps:

1. **Chat with Claude** (or another chat surface) to draft a ticket
2. **Paste one shell block** into a terminal to file the ticket
3. **Open Claude Code** (or another implementation agent) and say `next`
4. **Review the PR and merge**

Everything else is automated.

---

## Section 2 — Vocabulary cheatsheet

### Ticket lifecycle states

| State | Meaning | Who sets it |
|---|---|---|
| **QUEUED** | Spec is complete, ticket file committed, GitHub issue created with `queued` label. Waiting to be picked up. | You (via `tools/draft_ticket.sh`) |
| **IN_PROGRESS** | Branch open, agent is working. GitHub label `in-progress`. | Implementation agent (Step 5) |
| **IN_REVIEW** | PR open, waiting for your review. No extra label needed — the linked open PR is the signal. | Implementation agent (Step 8b) |
| **MERGED** | Landed on `main`. Issue auto-closes via `Closes #N` in PR body. | GitHub (on merge) |
| **CLOSED** | Abandoned without merging. Issue closed manually with reason "not planned". | You |
| **SUPERSEDED** | Replaced by a later ticket. Label `superseded`, issue closed. | You |

There is no intermediate draft state in the file system. Tickets are drafted in chat and only committed to `docs/TICKETS/` once they are QUEUED.

### Priority levels

| Priority | Meaning |
|---|---|
| **CRITICAL** | Data correctness, security, or blocks active work. Drop everything. |
| **HIGH** | Core feature for the current Milestone. |
| **MEDIUM** | Polish or quality-of-life on shipped work. |
| **LOW** | Speculative, or contingent on a design decision not yet made. |

### Milestones

A Milestone groups tickets by feature theme. It is "open" while it has unmerged tickets; "shipped" once all its tickets are MERGED. Milestones have no deadlines — they are organizing buckets.

Current Milestones (mirrored as GitHub Milestones):

| Milestone | Status |
|---|---|
| Foundation (data model, FIFO, repository) | shipped |
| UI core (shell, Live Overview, Manage Portfolio) | shipped |
| Tax engine (engine, dashboard, simulator) | shipped |
| Charts & research | shipped |
| Analytics & Risk | shipped |
| UI polish | shipped |
| Workflow & tooling | open |
| Investment Panel | pending design |

### Steps

"Step 1" through "Step 9" refer to the implementation ritual in AGENTS.md — what the agent does inside a single session. You do not need to know these steps in detail. If the agent says "stopping at Step 7," it means a gate check (tests or lints) failed.

The canonical definitions for all terms above live in `docs/METHODOLOGY.md`. If this cheatsheet and METHODOLOGY.md disagree, METHODOLOGY.md wins and this file has drifted — file a ticket.

---

## Section 3 — Drafting a ticket (the chat session)

**What you do:**

1. Open your chat surface (Claude.ai, etc.).
2. Paste the current `docs/PROJECT_STATE.md` and the last 3 entries of `docs/SESSION_LOG.md` into the chat. This is the full context the chat surface needs — no re-explaining required.
3. Describe the change you want: what problem it solves, what the end state looks like, any constraints.

**What you receive at the end of a good chat session:**

The chat surface follows the chat handoff protocol (documented in METHODOLOGY.md). You should receive a **Standard Handoff Bundle** containing:

1. A `.md` ticket file, ready to save to `docs/TICKETS/TICKET-<N>-<slug>.md`
2. A Milestone assignment (which Milestone the ticket belongs to)
3. A `next-up` flag (true or false)
4. An ADR file if an architectural decision was made
5. One shell block that invokes `tools/draft_ticket.sh` with the ticket spec on stdin

You do not need to police the format — just expect it. If the chat surface does not produce a shell block at the end, ask: "Please give me the Standard Handoff Bundle with the `tools/draft_ticket.sh` shell block."

---

## Section 4 — Filing a ticket (the paste)

**What you do:**

1. Download the `.md` ticket file the chat produced (or copy it out of the chat).
2. Save it where the shell block expects it — usually the script writes it for you, so you may only need the shell block itself.
3. Paste the shell block into your terminal and press Enter. If you're not on `main` or your working tree is dirty, the script will refuse to run with a clear error — fix and retry.

**What the script does (`tools/draft_ticket.sh`):**

- Reconciles the "Next up" lists in both `PROJECT_STATE.md` and `BACKLOG.md` against GitHub Issues (no more stale entries)
- Writes the ticket file to `docs/TICKETS/`
- Adds a row to the correct Milestone table in `docs/TICKETS/BACKLOG.md` (auto-creates the section if the Milestone is new)
- Updates `docs/PROJECT_STATE.md`'s "Next up" list (rebuilt from GitHub, not just prepended)
- Creates the GitHub issue with labels `queued` + the priority level (+ `next-up` if applicable)
- Commits with `docs: draft TICKET-<N> <title>`
- Pushes to `main`

After the script finishes, the ticket exists in the repo, GitHub Issues, and the BACKLOG. The implementation agent can now pick it up.

If the script fails, paste the error into the chat. You do not debug it.

---

## Section 5 — Implementing a ticket

**Your prompt:** `next`

That is the entire instruction. Optionally: `implement TICKET-XXX` if you want to override the queue order.

**What the agent does:** It reads `gh issue list --label next-up --state open` to find the correct ticket, then executes a 9-step ritual: reads the ticket, branches, implements, runs all checks, commits, updates docs, pushes, and opens a PR.

**What you do during the session:** Nothing. The agent does not need your input between steps. Housekeeping for the previous ticket happens automatically on merge via GitHub Actions; the agent's Step 2 verifies it landed.

**What you see:** File edits, test runs, lint runs, commit messages, a push, and finally a PR URL printed to the terminal.

**When the agent stops before opening a PR:** It will tell you exactly which check failed and the exact error message. The two most common stops:

- **`pytest` fails** — there is a bug in `main` or in the new code. The agent will not commit a broken state. Read the stop message; if it is a real bug in `main`, file a hotfix ticket in a new chat session. Do not coach the agent through a fix in the same session.
- **Acceptance criteria cannot be met as written** — the spec needs clarification. Open a new chat to update the ticket, then run a new implementation session.

---

## Section 6 — Reviewing the PR

The agent prints a PR URL at the end of every session. Open it. Your review is four checks:

1. **Re-read the ticket file.** Go to `docs/TICKETS/TICKET-<N>-<slug>.md` and re-read the acceptance criteria. This anchors your review on what was actually asked — memory of a chat conversation drifts.
2. **Read the diff against the acceptance criteria.** For each acceptance-criterion checkbox, find the change in the diff that satisfies it. Unchecked criteria that are not in scope → leave alone. Unchecked criteria that should have been met → request changes via a PR comment.
3. **Run the Streamlit app and click through the affected page.** Tests passing is necessary, not sufficient. Open the app, navigate to the relevant page, and observe the working behavior. If the ticket is purely docs or tooling, skip this step.
4. **Screenshot before/after if user-visible.** Paste in the PR description. This creates a record that is worth more than a paragraph of text for any future session that opens the PR.

If all four pass, merge. If any fail, comment on the PR with the specific finding. The agent picks up review comments in the next session — say `address PR review comments on TICKET-XXX` when starting that session.

Full version of the review protocol lives in `docs/METHODOLOGY.md` under "Reviewing PRs."

---

## Section 7 — Edge cases

**Agent stops mid-ritual:**
Read the stop reason in the terminal. If it names a failing test or a lint error in `main`, that is a real bug — file a hotfix ticket in a new chat session. If it is scoped to the new branch, the agent will report what it tried and what it recommends.

**`pytest` fails on the agent's branch:**
The agent will not commit. It stops and reports. You do not touch the branch. Open a new chat, paste the error, and get a recommendation.

**PR needs changes after your review:**
Comment on the PR on GitHub. Then open a new Claude Code session and say: `address PR review comments on TICKET-XXX`. The agent reads the PR comments and fixes them on the same branch.

**You find a bug after a ticket merges:**
File a new ticket. If it is a tight fix to specific files, include a `Files NOT to modify` section in the ticket spec so the agent does not scope-creep. The fix goes through the normal four-touchpoint flow.

**PROJECT_STATE.md looks stale:**
Ignore it. Step 2 of the next implementation session automatically queries GitHub and updates the state. You do not manually edit PROJECT_STATE.md.

**Starting a new chat session:**
Paste the current `docs/PROJECT_STATE.md` + the last 3 entries of `docs/SESSION_LOG.md` + your question. That is the complete context handoff.

---

## Section 8 — What changed in TICKET-M1 (transitional)

TICKET-M1 (merged 2026-05-10) made these changes to the workflow:

- **Vocabulary unified.** Lifecycle states are now QUEUED/IN_PROGRESS/IN_REVIEW/MERGED. Priority levels are CRITICAL/HIGH/MEDIUM/LOW. Ticket groupings are called Milestones. Agent ritual steps are numbered Step 1–9. Old vocabulary from before M1 is no longer used in active documents.
- **GitHub Issues integrated.** Every QUEUED ticket now has a corresponding GitHub issue with lifecycle and priority labels. `next-up` label marks exactly one issue as the next to implement. The agent resolves `next` by querying `gh issue list --label next-up`.
- **Helper scripts available.** `tools/draft_ticket.sh` + `tools/update_backlog.py` + `tools/update_state.py` automate the chat→repo handoff. `tools/setup_github.sh` created the initial label and milestone set on GitHub.
- **Chat handoff protocol formalized.** Chat surfaces always produce a Standard Handoff Bundle (ticket file + shell block). See METHODOLOGY.md.

This section can be deleted once the new flow is fully internalized (approximately 30–60 days after TICKET-M1 merged). File a cleanup ticket when ready — suggest naming it TICKET-MX-remove-m1-transitional-note.

---

## Section 9 — Tooling self-heal (added in TICKET-M3)

TICKET-M3 (merged 2026-05-13) made these changes to the tooling:

- **Branch guard in `draft_ticket.sh`.** The script refuses to run unless you are on `main` with a clean working tree. If you're on a feature branch, it prints an explicit error and exits before writing anything.
- **Auto-create Milestone sections.** `tools/update_backlog.py` no longer errors if the named Milestone section doesn't exist in BACKLOG.md — it creates the section automatically, then inserts the row with correct separator placement.
- **Next-up rebuild from GitHub (not prepend).** `tools/update_state.py` and `tools/update_backlog.py` now fully rebuild the "Next up" lists by querying GitHub Issues on every run. This eliminates the stale `1.`, `1.`, `1.` duplicate entries that appeared when multiple tickets were filed between sessions.
- **`tools/sync_state.py` standalone reconciliation.** Run `python3 tools/sync_state.py` at any time to reconcile both Next-up lists, In-review, and In-progress sections against GitHub ground truth. It does not commit.
- **GitHub Actions post-merge housekeeping.** When a PR merges to `main`, the `post-merge-housekeeping` workflow automatically updates the ticket file (`IN_REVIEW → MERGED`), moves the ticket from "In review 👀" to "Done ✓" in `PROJECT_STATE.md`, updates the BACKLOG.md row to `MERGED`, and reconciles the Next-up lists — all within seconds of the merge. The agent's Step 2 verifies this landed; if the workflow failed for any reason, Step 2 reconciles with `tools/sync_state.py --mark-merged`.

**One manual step required:** for the GitHub Actions workflow to push directly to the branch-protected `main`, Vivek must add `github-actions[bot]` to the "Allow specified actors to bypass required pull requests" list in GitHub → Settings → Branches → main.

---

## Cross-reference table

| File | What it covers |
|---|---|
| `AGENTS.md` | The implementation agent's ritual — 9 steps, stop conditions, hard rules. Not your concern day-to-day, but the authoritative spec for what the agent does. |
| `docs/METHODOLOGY.md` | Why the system works this way: anti-patterns, lessons learned, canonical lifecycle and priority definitions, the session-end ritual template. |
| `docs/ARCHITECTURE.md` | Code structure and layer boundary rules. Relevant only if you are reviewing a PR that touches the domain or adapters. |
| `docs/PROJECT_STATE.md` | Current status: which ticket is in review, which is next, what Milestones are done. Paste this at the start of any new chat session. |
| `docs/TICKETS/BACKLOG.md` | Full ticket list organized by Milestone. The exhaustive record. |
| `docs/SESSION_LOG.md` | Append-only log of every session. Paste the last 3 entries into a new chat for recent context. |
