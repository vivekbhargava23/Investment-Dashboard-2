# TICKET-M1 — Workflow vocabulary cleanup + GitHub Issues integration

**Status:** IN_PROGRESS
**Priority:** HIGH
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-10)
**Implemented by:** <agent name> (session YYYY-MM-DD)

## Problem

The project's vocabulary has accumulated three forms of overloading and ambiguity that confuse low-end models and create manual maintenance work for Vivek:

1. **"Phase" means two unrelated things.** AGENTS.md uses "Phase 1–9" for steps within one implementation session; PROJECT_STATE.md and BACKLOG.md use "Phase 0–6" for ticket groupings. A model reading "Phase 4" cannot tell which is meant from local context.

2. **"READY" is ambiguous.** Intended to mean "spec is complete," it reads as "go implement this now." DRAFT is similarly redundant — tickets are drafted in chat and only land in the repo once complete; no ticket file is ever genuinely DRAFT.

3. **Priority labels P0/P1/P2/P3 are jargon** without a definition document. New contributors (or models) cannot tell what P1 means without inferring from examples.

Additionally, the workflow has manual touchpoints that drift:

4. **Vivek manually edits BACKLOG.md and PROJECT_STATE.md** every time a ticket is created, with the format guessed each time from chat output.
5. **Ticket file `Status:` fields drift** — TICKET-000 still says IN_REVIEW months after merging; TICKET-008b uses "TODO" which is not in the defined lifecycle at all.
6. **"Next up" pointer lives in two files** (PROJECT_STATE.md and BACKLOG.md) and has gone stale before (lesson: 2026-05-09).
7. **MERGED housekeeping** depends on Vivek saying "I merged it" — fragile signal.

This ticket fixes all seven issues in one cleanup pass. The repo is at a clean point (TICKET-U1 just merged, no in-flight work) — the cheapest possible time.

## Acceptance criteria

### A. Vocabulary migration — active documents

- [ ] AGENTS.md: every occurrence of "Phase 1" through "Phase 9" (referring to the ritual) renamed to "Step 1" through "Step 9". Headers and prose both.
- [ ] AGENTS.md: lifecycle table updated — DRAFT removed, READY → QUEUED. P0/P1/P2 → CRITICAL/HIGH/MEDIUM/LOW where they appear.
- [ ] METHODOLOGY.md: every reference to "Phase X" (for ticket grouping) renamed to "Milestone". Lifecycle table updated. Priority definitions table added (see Notes).
- [ ] METHODOLOGY.md: "ticket lifecycle" diagram updated to `QUEUED → IN_PROGRESS → IN_REVIEW → MERGED`. DRAFT removed.
- [ ] PROJECT_STATE.md: "Phase: 0 — Foundation" line replaced with "Milestone: <current>". "Sprint:" line removed entirely (dead concept, never updated).
- [ ] PROJECT_STATE.md: "Next up 📋" section keeps only the next 1–2 items (mirror of BACKLOG's queue). "Done ✓" section trimmed to last 5 merged tickets; older history lives in BACKLOG.
- [ ] BACKLOG.md: "Phase 0 — Foundation" through "Phase 6 — Investment Panel framework" headers all renamed to "Milestone — <name>" (no number prefix).
- [ ] BACKLOG.md: status column values P0/P1/P2/P3 → CRITICAL/HIGH/MEDIUM/LOW throughout. READY → QUEUED throughout (none currently exist but the legend must be updated).
- [ ] BACKLOG.md: status legend at top updated. DRAFT removed from the list of valid statuses.
- [ ] ARCHITECTURE.md: stale page list under `app/ui/pages/` updated to reflect actual current pages (drop `02_performance.py`, `04_decision_gates.py`, `05_behavioural_ledger.py`; add Analytics tabs and Research page per current repo state). Verify against actual `app/ui/pages/` directory listing before editing.
- [ ] ADR-005: `**Status:** Proposed` → `**Status:** Accepted`. Add a line: `**Accepted:** 2026-05-04 (TICKET-009-revised, TICKET-008c, TICKET-020 all merged).`

### B. Vocabulary migration — historical ticket files

- [ ] **Out of scope.** Ticket files in `docs/TICKETS/` for already-merged or closed tickets are NOT migrated. They remain as historical record with their original P0/P1/READY/MERGED vocabulary. This is a deliberate decision documented in the Notes section of this ticket.

### C. GitHub Issues integration — labels and milestones

- [ ] One-time label setup script `tools/setup_github.sh` created. Idempotent (uses `gh label create ... || true`). Creates these labels:
  - Lifecycle: `queued`, `in-progress` (no others — IN_REVIEW is implicit when an issue has a linked open PR; MERGED is implicit when the issue is closed)
  - Priority: `critical`, `high`, `medium`, `low`
  - Coordination: `next-up` (exactly one issue carries this at a time)
  - Special: `blocked`, `superseded`
- [ ] `tools/setup_github.sh` also creates GitHub Milestones for each current Milestone in BACKLOG.md, by name (Foundation, UI core, Tax engine, Charts & research, Analytics & Risk, UI polish, Investment Panel). Closed Milestones (Foundation through UI polish) are created and immediately closed; Investment Panel stays open.
- [ ] Run the script once as part of this PR's verification. Confirm via `gh label list` and `gh api repos/:owner/:repo/milestones?state=all` that all expected labels and milestones exist.

### D. AGENTS.md ritual updates for `gh` integration

- [ ] **New Step 0** added before existing Step 1: support invocation "implement next ticket" or just "next". Resolve via `gh issue list --label next-up --state open --json number,title --limit 1`. If exactly one issue is found, use it. If zero, stop and ask Vivek. If multiple (shouldn't happen), stop and report the inconsistency.
- [ ] Step 5 (branch + mark in-progress) updated: in addition to setting the ticket file Status, run:
  ```bash
  gh issue edit <N> --remove-label queued,next-up --add-label in-progress
  ```
- [ ] Step 9 (open PR) updated: PR body must include `Closes #<N>` so the issue auto-closes on merge.
- [ ] Step 2 (next-session housekeeping) updated: detect the previous ticket's merge state via:
  ```bash
  gh issue view <N> --json state -q .state
  ```
  If `CLOSED`, perform housekeeping. If `OPEN`, skip housekeeping. The "Vivek told me he merged it" signal is replaced by the `gh` query.
- [ ] AGENTS.md "When Vivek says 'I merged it'" section updated to note that the housekeeping signal is now the issue state, not the message — but the principle (do nothing in the current session after merge) is preserved.

### E. Helper scripts for chat→repo handoff

- [ ] `tools/draft_ticket.sh` created. Reads a ticket spec from stdin in a defined format (see Notes), and:
  1. Writes the ticket file to `docs/TICKETS/TICKET-<N>-<slug>.md`
  2. Updates BACKLOG.md by appending the row to the correct Milestone table
  3. Updates BACKLOG.md "Next up" section if the ticket is marked `next-up`
  4. Creates the GitHub issue with body referencing the ticket file and labels matching priority + `queued` (+ optionally `next-up`)
  5. Commits with `docs: draft TICKET-<N> <title>`
  6. Pushes to main
- [ ] `tools/update_backlog.py` — Python helper invoked by `draft_ticket.sh`. Adds a row to a named Milestone table. Updates "Next up" section. ~50 lines.
- [ ] `tools/update_state.py` — Python helper for updating PROJECT_STATE.md "Next up" pointer. ~30 lines.
- [ ] All three scripts tested manually as part of PR verification — agent runs them with a synthetic test ticket (TICKET-MTEST), confirms files are correctly updated, then `git reset --hard` to undo before the real M1 commit.

### F. Standard Handoff Bundle protocol — METHODOLOGY.md

- [ ] New section in METHODOLOGY.md titled "The chat handoff protocol" specifying that when Claude Chat (or any chat surface) drafts a ticket, the final response is **always** structured as:
  1. Ticket file content (delivered as a `.md` file, not pasted in chat)
  2. Milestone assignment (which Milestone in BACKLOG.md it goes into)
  3. Whether it should be marked `next-up`
  4. ADR file content if any (also as a `.md` file)
  5. One shell block invoking `tools/draft_ticket.sh` with the spec on stdin
- [ ] Section explicitly notes: "If Vivek runs the shell block, the entire repo state update is one paste. He never edits BACKLOG.md or PROJECT_STATE.md by hand."

### G. Verification

- [ ] `pytest && ruff check . && mypy app/ && lint-imports` — all pass.
- [ ] `gh label list` shows all expected labels.
- [ ] `gh api repos/:owner/:repo/milestones?state=all` shows all expected milestones.
- [ ] Open AGENTS.md, METHODOLOGY.md, PROJECT_STATE.md, BACKLOG.md, ARCHITECTURE.md, ADR-005 — visually scan for any remaining occurrences of "Phase" (in the ticket-grouping sense), "DRAFT", "READY", "P0", "P1", "P2", "P3", "Sprint". Use `grep -n` to be sure:
  ```bash
  grep -n "Phase [0-9]" docs/PROJECT_STATE.md docs/TICKETS/BACKLOG.md docs/METHODOLOGY.md docs/ARCHITECTURE.md
  grep -n -E "\b(DRAFT|READY|P[0-3]|Sprint)\b" docs/AGENTS.md docs/METHODOLOGY.md docs/PROJECT_STATE.md docs/TICKETS/BACKLOG.md docs/ARCHITECTURE.md docs/DECISIONS/ADR-005-eur-native-input.md
  ```
  Any matches in active documents (excluding historical ticket files in `docs/TICKETS/TICKET-*.md`) must be intentional and justified in commit message, or fixed.
- [ ] Manually run `tools/draft_ticket.sh` with a synthetic spec and confirm: ticket file appears, BACKLOG row appears in the right Milestone, GitHub issue is created with correct labels, commit is made, push happens. Then revert.

## Files likely touched

### Active documentation (full vocabulary migration)
- `docs/AGENTS.md`
- `docs/METHODOLOGY.md`
- `docs/PROJECT_STATE.md`
- `docs/ARCHITECTURE.md`
- `docs/TICKETS/BACKLOG.md`
- `docs/DECISIONS/ADR-005-eur-native-input.md`

### New files
- `tools/setup_github.sh`
- `tools/draft_ticket.sh`
- `tools/update_backlog.py`
- `tools/update_state.py`

### NOT touched
- `docs/TICKETS/TICKET-*.md` (historical ticket files — see Notes)
- `app/**` (no code changes)
- `tests/**` (no test changes)

## Out of scope

- Migrating historical ticket files (TICKET-000 through TICKET-A5, U1) to new vocabulary. Deliberately preserved as historical record.
- Migrating closed/merged GitHub issues retroactively. Going forward only.
- A web dashboard / GitHub Project board on top of issues. Optional future addition.
- Replacing markdown ticket files with GitHub-issues-only. Hybrid model is the chosen design (per chat 2026-05-10).
- Auto-generating BACKLOG.md from `gh issue list`. Possible future optimization; not now.

## Test cases

This ticket is documentation + tooling, not code, so "tests" are verification steps:

1. **Vocabulary scrub**: After all edits, run the two `grep` commands in acceptance criterion G. Output should be empty (or match only deliberately preserved references in historical files).
2. **`tools/draft_ticket.sh` end-to-end**: Pipe a synthetic ticket spec for "TICKET-MTEST — verify draft script works" with priority MEDIUM, milestone "UI polish", `next-up=false`. Confirm:
   - File `docs/TICKETS/TICKET-MTEST-verify-draft-script.md` exists with correct content
   - BACKLOG.md "UI polish" Milestone table has a new row
   - `gh issue list --label medium --search "MTEST"` returns the new issue
   - Issue body references the ticket file path
   - Issue has labels `queued` and `medium`
   - Issue does NOT have label `next-up`
   - A commit was made on main with message starting `docs: draft TICKET-MTEST`
   - Run `git reset --hard HEAD~1 && gh issue close <N> --reason 'not planned'` to revert before the real M1 commit
3. **Step 0 resolution**: After the ticket script has set up labels, manually create a fake `next-up`-labeled issue, run `gh issue list --label next-up --state open --json number,title --limit 1`, confirm exactly one result. Delete the fake.
4. **Step 2 housekeeping check**: Pick a recently-merged ticket's number; run `gh issue view <N> --json state -q .state` (this requires that issue to exist in GitHub — it won't for old merged tickets, so test with a new closed test issue instead). Output should be `"CLOSED"`.

## Notes

### Why historical ticket files are excluded

Historical ticket files in `docs/TICKETS/` for merged or closed tickets are read-only artifacts. They serve as a record of what was specified and built. Migrating their `Status:` and `Priority:` fields would touch 20+ files for purely cosmetic effect, with non-zero risk of accidentally changing semantic content during a global find/replace. The active documents (AGENTS, METHODOLOGY, BACKLOG, PROJECT_STATE, ARCHITECTURE, ADRs) are what get read every session — those are migrated. Historical files keep their original vocabulary as a snapshot of how the project worked at the time. New tickets going forward use the new vocabulary.

The cost of mixing vocabulary in historical vs. new is low because no one reads historical ticket files looking for *current* status — they read them looking for "what did this ticket originally specify."

### Priority definitions (to add to METHODOLOGY.md)

```markdown
## Priority levels

- **CRITICAL** — data correctness, security, or blocks active work. Drop everything.
- **HIGH** — core feature for the current Milestone.
- **MEDIUM** — polish or quality-of-life on shipped work.
- **LOW** — speculative, or contingent on a design decision not yet made.
```

### Lifecycle definitions (to add to METHODOLOGY.md)

```markdown
## Ticket lifecycle

QUEUED → IN_PROGRESS → IN_REVIEW → MERGED

- **QUEUED** — spec is complete and committed to `docs/TICKETS/`. GitHub issue exists with label `queued`. Waiting to be picked up. (Note: "queued" intentionally avoids "ready" because "ready" reads as an instruction; "queued" is a state.)
- **IN_PROGRESS** — branch open, work happening. Issue label `in-progress`.
- **IN_REVIEW** — PR open, awaiting Vivek's merge. Implicit (no label needed) when issue has a linked open PR.
- **MERGED** — landed on main. Implicit (issue is closed by `Closes #N` in PR body).

Edge cases:
- **CLOSED** — abandoned without merging. Issue closed manually with reason "not planned".
- **SUPERSEDED** — replaced by a later ticket. Label `superseded`, issue closed.

There is no DRAFT status. Tickets are drafted in chat; they only land in `docs/TICKETS/` once they are QUEUED.
```

### Milestone definitions (to add to METHODOLOGY.md)

```markdown
## Milestones

Milestones group tickets by feature theme. A Milestone is "open" while it has unmerged tickets in it; "shipped" once all its tickets are MERGED. Milestones don't have deadlines — they're organizing buckets, not deliverable targets.

Current Milestones (mirrored as GitHub Milestones):
- Foundation (data model, FIFO, repository) — shipped
- UI core (shell, Live Overview, Manage Portfolio) — shipped
- Tax engine (engine, dashboard, simulator) — shipped
- Charts & research — shipped
- Analytics & Risk — shipped
- UI polish — shipped
- Investment Panel — pending design

Each ticket is assigned to exactly one Milestone via the GitHub issue's `milestone` field, mirroring the BACKLOG.md grouping.
```

### Stdin format for `tools/draft_ticket.sh`

```
ID: TICKET-<NNN>
TITLE: <one-line title>
MILESTONE: <name, must match an existing Milestone>
PRIORITY: CRITICAL | HIGH | MEDIUM | LOW
ESTIMATE: <free text, e.g. "1 – 1.5 hr">
NEXT_UP: true | false
---
<full markdown ticket body, including the Status/Priority/etc. header lines>
```

The script parses the header (everything before `---`), uses it for filename, label, milestone, and commit message, and writes everything after `---` as the ticket file content.

### A note on "Step" vs "Phase" in AGENTS.md

The ritual currently uses "Phase 1" through "Phase 9". After this ticket, these become "Step 1" through "Step 9". The word "Phase" is freed up for cross-references in PROJECT_STATE — but in practice we use "Milestone" for that, so "Phase" exits the vocabulary entirely. If "Phase" appears anywhere after this ticket in active docs, it is either a bug (should have been migrated) or a quote from a historical document.

### Why not auto-update PROJECT_STATE.md "Done" list

Tempting to have Claude Code auto-append the merged ticket title to PROJECT_STATE's Done list in Step 8b. Decided against: PROJECT_STATE's Done list is intentionally a curated "last 5" view, not an exhaustive log. BACKLOG.md is the exhaustive log (and after this ticket, GitHub issues are too — `gh issue list --state closed`). Keep PROJECT_STATE.md hand-curated to the small recent set.

### Verification: ARCHITECTURE.md page list audit

Before editing ARCHITECTURE.md's `app/ui/pages/` listing, the agent must run `ls app/ui/pages/` and use the actual file list as the source of truth. Do not infer from PROJECT_STATE.md or memory.

### Order of operations during implementation

The agent should perform edits in this order to minimize the chance of partial state:

1. AGENTS.md (Phase → Step, lifecycle, priority)
2. METHODOLOGY.md (full vocabulary migration + new sections)
3. ARCHITECTURE.md (page list + any vocabulary)
4. ADR-005 status update
5. BACKLOG.md (Phase → Milestone, P0–P3 → CRITICAL–LOW, READY → QUEUED, drop DRAFT)
6. PROJECT_STATE.md (Milestone field, drop Sprint, slim Done list, slim Next up)
7. Create `tools/setup_github.sh`, run it, verify labels and milestones in GitHub
8. Create `tools/update_backlog.py`, `tools/update_state.py`, `tools/draft_ticket.sh`
9. Test `tools/draft_ticket.sh` with synthetic ticket, then revert
10. Run all `grep` verification commands from criterion G
11. Standard Step 7+ ritual (gate check → commit → docs commit → push → PR)

This is a documentation-heavy ticket — there is no risk of test failure mid-way, but there is real risk of leaving partial vocabulary migrations. The grep verification is the safety net.
