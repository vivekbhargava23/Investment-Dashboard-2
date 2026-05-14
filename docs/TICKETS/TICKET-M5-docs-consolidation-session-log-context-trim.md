# TICKET-M5 — Consolidate AGENTS.md, restore SESSION_LOG.md, trim CONTEXT.md

**Status:** QUEUED
**Priority:** HIGH
**Estimated session length:** 1.5 hr
**Drafted by:** Vivek + Claude Chat (2026-05-14)
**Milestone:** Tooling / Workflow

---

## Problem

Three workflow issues to fix in one pass:

1. **Two `AGENTS.md` files exist** — `/AGENTS.md` (stale, references the deleted `STATE.md`) and `/docs/AGENTS.md` (current, board-driven). Other CLIs (Codex, Gemini CLI, Cursor) look for `AGENTS.md` at repo root by convention. The stale root copy is the one they find. Drift will keep happening as long as both exist.

2. **No session log.** `docs/SESSION_LOG.md` was deleted in commit `3f6d520f` along with `BACKLOG.md` and `WORKFLOW.md`. Its history-preserving value (what changed in each session, decisions, deviations) was thrown out with the genuinely stale state-tracking files. Reintroduce it as a branch-committed, append-only file — no bot involvement, lands on `main` via merge alongside the implementation.

3. **`docs/CONTEXT.md` is 2410 lines.** ~810 lines are a flat dump of every test function name. ~120 lines are a `tests/` file tree. ~150 lines are an embedded STATE.md preamble that's obsolete (board is source of truth now). None of this helps ticket drafting. Trim to ~700 lines.

---

## Acceptance criteria

### A. AGENTS.md consolidation
- [ ] `/AGENTS.md` (root) is the canonical, board-driven version. Its content is the current content of `/docs/AGENTS.md` (the board-driven ritual that does NOT reference STATE.md).
- [ ] `/docs/AGENTS.md` is deleted.
- [ ] `/CLAUDE.md` (root) is updated to point at `/AGENTS.md` (relative, one-line pointer).
- [ ] `/AGENTS.md`'s "Required reading" list correctly references `docs/CONTEXT.md`, `docs/METHODOLOGY.md`, `docs/ARCHITECTURE.md`. No reference to `docs/STATE.md` anywhere in the file.
- [ ] No file in the repo references `/docs/AGENTS.md` after this ticket (grep check below).

### B. SESSION_LOG.md restoration
- [ ] `docs/SESSION_LOG.md` exists.
- [ ] The historical content from before deletion (commit `3f6d520f`'s parent) is restored at the top of the file under a heading `## Historical entries (pre-deletion)`. Recovery command: see "Implementation notes" below.
- [ ] A new heading `## Active log` separates historical from new entries.
- [ ] A template entry (commented out, or under a `## Template` heading) shows the format below.
- [ ] `AGENTS.md` Step 8 is updated: a new sub-step 8b appends a session entry to `docs/SESSION_LOG.md` on the branch, commits with `docs: session log for TICKET-XXX`, then pushes (renumber existing 8b→8c, 8c→8d).
- [ ] `METHODOLOGY.md` "Session-end ritual" summary mentions the session log step.
- [ ] No GitHub Action touches `SESSION_LOG.md`. It is purely branch-committed.

### C. CONTEXT.md trim
- [ ] `tools/regen_context.py` no longer emits the "Tests inventory" section.
- [ ] `tools/regen_context.py` no longer includes the `tests/` subtree in the "File tree" section. Only `app/` and `docs/` subtrees appear.
- [ ] `tools/regen_context.py` no longer embeds the old STATE.md preamble (the leading project-overview text that duplicates README content — lines 9–150 of the current generated output, sourced from the now-deleted state driver).
- [ ] A new section `## Recent sessions` is emitted, containing the last 10 entries from `docs/SESSION_LOG.md` (parsed by the `## YYYY-MM-DD HH:MM — TICKET-XXX` heading pattern). If `SESSION_LOG.md` is missing or has no entries, emit `<no entries>`.
- [ ] After regeneration, `wc -l docs/CONTEXT.md` is between 500 and 900 lines. (Sanity bound — the spec is "drop bloat," not "hit a number.")
- [ ] The regenerated `CONTEXT.md` is committed in this PR (so the trim takes effect on merge, not just on the next merge).

### D. Test/lint gate
- [ ] `pytest -q` passes.
- [ ] `ruff check .` passes.
- [ ] `mypy app/` passes.
- [ ] `lint-imports` passes.
- [ ] Existing tests in `tests/unit/tools/test_regen_context.py` are updated to reflect the new section set. Remove assertions for `tests_inventory` if any exist. Add assertion that `Recent sessions` section is present.

---

## Files likely touched

- `AGENTS.md` (root) — replaced wholesale with content of `docs/AGENTS.md`, plus Step 8b update for session log
- `docs/AGENTS.md` — deleted
- `CLAUDE.md` (root) — updated pointer
- `docs/SESSION_LOG.md` — created, history-restored, template added
- `docs/METHODOLOGY.md` — one-line update under "Session-end ritual"
- `tools/regen_context.py` — remove three sections, add one section
- `tests/unit/tools/test_regen_context.py` — update assertions
- `docs/CONTEXT.md` — regenerated and committed

---

## Out of scope

- Any change to `docs/ARCHITECTURE.md`. It stays where it is. No root duplicate is created.
- Any change to the GitHub Actions workflows (`post-merge-housekeeping.yml`, `update-context.yml`). The session log is branch-committed, never touched by bots.
- Any change to `tools/file.sh` or the board API logic.
- Adding any new automation around session log parsing beyond the regen_context.py "Recent sessions" emitter.
- Re-classifying historical SESSION_LOG.md entries or rewriting their format. Restore verbatim under "Historical entries" heading.

---

## Implementation notes

### Session log template (use this exact format for new entries)

```markdown
## YYYY-MM-DD HH:MM — TICKET-XXX
**Surface:** Claude Code
**Model:** sonnet-4.6 | opus-4.7 | haiku-4.5
**Duration:** ~XX min
**Branch:** ticket-XXX-short-name
**PR:** https://github.com/<user>/<repo>/pull/N
**Status at session end:** IN_REVIEW

### What got done
- Bullet of concrete change 1
- Bullet of concrete change 2

### Files touched
- `app/domain/fifo.py` — added replay-on-edit logic
- `tests/unit/test_fifo.py` — added 4 new test cases

### Tests
48 passing → 52 passing (4 new)

### Decisions made during the session
- Chose to raise `LotEditConflict` instead of silent recompute — see ADR-XXX
- (Or: "no architectural decisions made")

### Out-of-scope items noticed
- Open ticket: TICKET-YYY (noticed but didn't fix)

### Tokens used (rough)
~XXk
```

### Recovering pre-deletion SESSION_LOG.md content

The file was deleted in commit `3f6d520f1bca5cbea78e097625b61db9efc4994`. Get the last version before deletion:

```bash
git show 3f6d520f^:docs/SESSION_LOG.md > /tmp/session_log_historical.md
```

Open `/tmp/session_log_historical.md` and copy its full content under the new `## Historical entries (pre-deletion)` heading in the new `docs/SESSION_LOG.md`. Do not edit the historical entries — preserve verbatim.

### CLAUDE.md content (write exactly this)

```markdown
# CLAUDE.md

Read and follow `AGENTS.md` in this directory. It contains all project rules,
rituals, and constraints. Treat it as your system instructions for this repo.

Everything in `AGENTS.md` applies to you. "The implementation agent" means you.
```

(No content change — the existing CLAUDE.md is already correct since it points at `AGENTS.md` at root. Verify it doesn't reference `docs/AGENTS.md` and leave alone if clean.)

### AGENTS.md Step 8 — new ordering

Current Step 8 in `docs/AGENTS.md` is:
- 8a: commit the implementation
- 8b: push the branch
- 8c: move board item to In review

New Step 8 (after this ticket):
- 8a: commit the implementation
- 8b: append session log entry to `docs/SESSION_LOG.md`, commit with `docs: session log for TICKET-XXX`
- 8c: push the branch
- 8d: move board item to In review

Order matters: session log is committed **on the branch before the push**, so it lands on `main` when Vivek merges. There is no post-merge session-log update.

### regen_context.py changes — concrete

1. **Remove** the function that emits the "Tests inventory" section and its call site.
2. **Modify** the file-tree emitter: walk only `app/` and `docs/`, skip `tests/`. (If the current implementation walks the repo root and includes `tests/`, scope it.)
3. **Remove** the embedded STATE.md preamble emitter. The current output's lines 1–150 (project overview, stack, workflow, current status, key decisions, open questions, ADRs-titles) — figure out which of these come from the regen script vs. from a deleted `STATE.md` and remove the latter. The board-sourced sections (Up next, In progress, In review, Recently done) **stay**.
4. **Add** a `_emit_recent_sessions()` function that:
   - Reads `docs/SESSION_LOG.md`
   - Parses headings matching `^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) — (TICKET-\S+)`
   - Takes the most recent 10 (top of file = most recent; entries are appended at top of "Active log" section)
   - Emits each as: `- YYYY-MM-DD HH:MM — TICKET-XXX (PR #N)` — extract PR from the `**PR:**` line
   - If file missing or no entries: emit `<no entries>`

### Grep checks (run before opening PR)

```bash
# Should return 0 matches
grep -rn "docs/AGENTS.md" .
grep -rn "STATE\.md\|STATE.md" docs/ AGENTS.md CLAUDE.md tools/
# Should return matches only in SESSION_LOG.md historical content and DECISIONS/
```

If either of the first two greps returns matches outside of historical/archival content, fix them in the same PR.

---

## Test cases

1. **AGENTS.md location:** `test -f AGENTS.md && ! test -f docs/AGENTS.md` succeeds.
2. **CLAUDE.md points to root AGENTS.md:** `grep -q "AGENTS.md" CLAUDE.md && ! grep -q "docs/AGENTS.md" CLAUDE.md` succeeds.
3. **SESSION_LOG.md exists with both sections:** `grep -q "## Historical entries (pre-deletion)" docs/SESSION_LOG.md && grep -q "## Active log" docs/SESSION_LOG.md` succeeds.
4. **regen_context output sanity:** run `python3 tools/regen_context.py`, then assert `wc -l docs/CONTEXT.md` is between 500 and 900, and `grep -q "## Recent sessions" docs/CONTEXT.md` succeeds, and `grep -q "## Tests inventory" docs/CONTEXT.md` fails.
5. **Existing regen tests still pass** after assertions are updated.
6. **Step 8 reordering documented:** `grep -q "8b\. \*\*Append session log entry\*\*" AGENTS.md || grep -q "8b" AGENTS.md` shows the new step exists and references the session log.

---

## Notes

- **Assumption (verify before implementing):** `docs/AGENTS.md` is the newer, board-driven version that should win. The root `/AGENTS.md` references `docs/STATE.md` (which no longer exists) and is stale. If on inspection the root file turns out to have newer content than `docs/AGENTS.md`, stop and report — do not pick blindly.
- **Assumption:** `tools/regen_context.py` is the only producer of `docs/CONTEXT.md`. If a second script also writes to CONTEXT.md, the agent will discover this during implementation and should stop and report rather than dual-source.
- **Assumption:** The CLAUDE.md at root (per `/mnt/project/CLAUDE.md`) already correctly points at `AGENTS.md` (5 lines, no STATE reference). Leave it alone if so.
- **Why session log lives in `docs/` and not at root:** other CLIs don't need to auto-load it — it's a write-target, not a read-target. The agent is instructed to append to it via `AGENTS.md` Step 8b. Putting it in `docs/` keeps the root tidy.
- **Why no bot updates SESSION_LOG.md:** every existing bot (post-merge housekeeping, update-context) fires after merge. Session entries describe the implementation session, must land in the PR itself, and must not require a post-merge edit on `main`. Branch-commit → merge → done.
- **The "Recent sessions" section in CONTEXT.md** gives chat a fast scroll of the last 10 implementation sessions without reading the full log. Full log is available on disk if needed.
- The `git log` recovery for SESSION_LOG.md preserves the prior history without re-running any old sessions. It's a one-time paste, not an ongoing reconciliation.
