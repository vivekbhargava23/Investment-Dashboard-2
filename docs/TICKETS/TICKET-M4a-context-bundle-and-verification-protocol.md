# TICKET-M4a — Auto-generated CONTEXT.md + chat verification protocol

**Status:** IN_REVIEW
**Priority:** HIGH
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-13)
**Implemented by:** Claude Code (session 2026-05-13)

## Problem

When Vivek opens a new chat to draft a ticket, the chat surface has access to whatever is in the Projects folder (currently: ARCHITECTURE.md, METHODOLOGY.md, WORKFLOW.md, AGENTS.md, CLAUDE.md) plus whatever Vivek pastes mid-conversation. It does **not** have access to:

- The actual codebase (function signatures, Pydantic models, port definitions)
- The current Streamlit UI surface (which pages exist, what's on them)
- Open issues, open PRs, recent merges on GitHub
- The current shape of `data/portfolio.json`

This forces chat to either ask Vivek for everything every session, or worse, **hallucinate**. Recent evidence of hallucination cost:

- TICKET-009 (original spec, closed without merging) — invented FX-rate and native-price fields that Scalable Capital confirmations don't surface
- TICKET-008c — silent currency-correctness bug from a "use USD as approximation" placeholder that survived to production data
- Recurring pattern: tickets reference function names or UI elements that no longer exist after a recent refactor

The fix has two parts:

1. **Auto-generate `docs/CONTEXT.md` on every merge to main.** This file inlines STATE.md, ADR titles, the file tree, public Python interfaces (extracted via `ast`), Streamlit page list, JSON data shape, open issues, open PRs, recent merges, and the test inventory. It is committed to main by GitHub Actions. Because the Projects folder mirrors main, the file is always in chat's context.

2. **Adopt a chat-side verification protocol.** Before drafting any ticket that touches existing code, chat must locate the affected code in CONTEXT.md, confirm signatures, ask Vivek for screenshots on UI tickets, write assumptions explicitly into the ticket's Notes section, and scan for conflicts with open issues / recent merges.

This ticket delivers both halves. It does **not** consolidate other docs (BACKLOG, SESSION_LOG, WORKFLOW) — that's TICKET-M4b.

## Acceptance criteria

### A. New script: `tools/regen_context.py`

- [ ] Python 3.11+ script, no external dependencies beyond what's already in `pyproject.toml` (stdlib `ast`, `subprocess`, `json`, `pathlib`, `datetime` are sufficient).
- [ ] Reads STATE.md (or, until TICKET-M4b lands, falls back to PROJECT_STATE.md) and inlines its full contents into a section titled `## State driver`.
- [ ] Walks `docs/DECISIONS/` and extracts the first `# ADR-NNN — title` line from each file. Emits as `## ADRs (titles only)`. Sorted by ADR number.
- [ ] Runs `tree app/ tests/ docs/ -I '__pycache__|*.pyc'` (or a Python-native equivalent using `pathlib` if `tree` isn't available) and emits as `## File tree`.
- [ ] Walks `app/` recursively. For each `.py` file:
  - Parses with `ast`.
  - Extracts top-level `def` and `async def` signatures (name, args with type annotations, return annotation).
  - Extracts every `class` definition, including its base classes and any class-level field annotations (for Pydantic models, dataclasses, and Protocol definitions).
  - Skips private functions (leading underscore) unless they're inside a Protocol class.
  - Groups output by file path. Emits as `## Public interfaces (extracted from app/)`.
- [ ] Lists every `.py` file in `app/ui/pages/` and emits the module docstring (first triple-quoted block) or the first non-import line if no docstring. Emits as `## UI surface (Streamlit pages)`.
- [ ] Reads `data/portfolio.json`, walks the top two levels of structure, emits the keys and the type of each value (with a single sample value where the type is a primitive). Does NOT emit the full file. Emits as `## Data file shape (data/portfolio.json)`.
- [ ] Calls `gh issue list --state open --json number,title,labels --limit 50` and emits as `## Open issues`.
- [ ] Calls `gh pr list --state open --json number,title --limit 20` and emits as `## Open PRs`.
- [ ] Calls `gh pr list --state merged --limit 10 --json number,title,mergedAt` and emits as `## Recent merges (last 10)`.
- [ ] Walks `tests/` recursively, extracts test function names (`def test_*` and `async def test_*`) per file, emits as `## Tests inventory` grouped by file.
- [ ] Top of the file: a header `# CONTEXT — auto-generated YYYY-MM-DD HH:MM:SS UTC` and one paragraph explaining the file is auto-generated and not hand-edited.
- [ ] Writes output to `docs/CONTEXT.md`.
- [ ] Idempotent: running twice in a row produces the same file (modulo the timestamp). The timestamp is the only line that should differ on a no-op run.
- [ ] Run locally during implementation; commit the first generated `docs/CONTEXT.md` in the same PR.

### B. New GitHub Action: `.github/workflows/update-context.yml`

- [ ] Triggers on `push` to `main`.
- [ ] Does NOT trigger on commits authored by `github-actions[bot]` (use the `if: github.actor != 'github-actions[bot]'` guard) to prevent recursion with the post-merge-housekeeping workflow.
- [ ] Checks out main with full history.
- [ ] Sets up Python 3.11.
- [ ] Installs minimal dependencies (likely just `gh` — pre-installed on `ubuntu-latest`).
- [ ] Runs `python tools/regen_context.py`.
- [ ] If `docs/CONTEXT.md` changed, commits with author `github-actions[bot]` and message `chore: regenerate CONTEXT.md [skip ci]`, pushes to main.
- [ ] If `docs/CONTEXT.md` did not change, exits 0 without committing.
- [ ] Documented at the top of the workflow file: trigger, what it does, why the bot-author guard exists.

### C. Update `docs/METHODOLOGY.md` — new section "Ticket drafting in chat — the verification protocol"

Insert this section immediately after the existing "The chat handoff protocol" section. Content:

- [ ] **Required reads.** Before drafting any ticket, chat must have access to `docs/CONTEXT.md` (auto-generated, current with main). STATE.md (or PROJECT_STATE.md until M4b lands) alone is insufficient — it does not contain code signatures or UI surface.
- [ ] **Mandatory verification before drafting.** Chat must perform these four checks:
  1. **Locate the affected code in CONTEXT.md.** If the ticket touches `function_name` or `ClassName`, chat must find it in the `Public interfaces` section and confirm its current signature / field set. If chat cannot find what it's about to modify, it asks Vivek before drafting.
  2. **For UI tickets, require a screenshot or page description from Vivek.** CONTEXT.md's `UI surface` section lists page filenames and docstrings, not what the rendered page actually looks like. Chat must say: "Please share a screenshot or describe what's currently on the [page] page before I draft this."
  3. **State assumptions explicitly in the ticket's Notes section.** Every assumption that wasn't verified from CONTEXT.md gets written down. Example: *"Assumes `OpenLot.split()` does not exist and will be created. Confirm before implementing."* This gives the agent a chance to catch a wrong assumption before writing code.
  4. **Check for conflicts.** Scan `Open issues` and `Recent merges` in CONTEXT.md. If something equivalent is already in flight or just merged, flag it to Vivek before drafting.
- [ ] **The agent's recourse.** Add a paragraph noting that if the agent encounters an assumption from the Notes section that turns out to be wrong (e.g. the function chat assumed didn't exist actually does, with a different signature), it stops at Step 7 and reports — per the existing Stop Conditions rule.

### D. Update `docs/AGENTS.md` — Required reading list

- [ ] Add `docs/CONTEXT.md` to the Required Reading section, between PROJECT_STATE.md and METHODOLOGY.md (i.e. position 2). Note that CONTEXT.md is auto-generated and gives a complete repo snapshot.

### E. Update `README.md`

- [ ] Add a short "For chat sessions" subsection under "Working on this project": *"Chat surfaces in the Projects folder have `docs/CONTEXT.md` automatically available. It contains the current state, code interfaces, UI surface, and GitHub state. No manual paste required."*

### F. Verification

- [ ] `pytest && ruff check . && mypy app/ && lint-imports` — all pass.
- [ ] Run `python tools/regen_context.py` locally. Verify:
  - The generated file exists at `docs/CONTEXT.md`.
  - All 10 sections are present (State driver, ADRs, File tree, Public interfaces, UI surface, Data file shape, Open issues, Open PRs, Recent merges, Tests inventory).
  - The file is under 1500 lines for the current codebase. (Soft limit — if it's larger, that's information about code growth, not a bug. Just confirm it's not absurd.)
  - Public interfaces section contains at least: `Money`, `Lot`, `Transaction`, `Position` (from `app/domain/models.py`); `compute_positions` (from `app/domain/fifo.py`); `PriceFeed`, `FxFeed`, `Repository` Protocols (from `app/ports/`).
- [ ] Run the script a second time without making changes. Diff the two outputs — only the timestamp line should differ.
- [ ] Push to a branch. Confirm the Action runs on the next merge to main (this will happen when the PR for this ticket itself merges). Verify it commits `docs/CONTEXT.md` and the commit message is `chore: regenerate CONTEXT.md [skip ci]`.
- [ ] Verify the Action does NOT re-trigger itself (the bot-author guard works).

## Files likely touched

### New files
- `tools/regen_context.py`
- `.github/workflows/update-context.yml`
- `docs/CONTEXT.md` (first auto-generated version committed in this PR)

### Edited
- `docs/METHODOLOGY.md` — new "Ticket drafting in chat — the verification protocol" section
- `docs/AGENTS.md` — Required reading list adds CONTEXT.md
- `README.md` — one new subsection

### NOT touched
- `app/**`
- `tests/**` (unless adding a smoke test for `regen_context.py` — see Notes)
- `docs/ARCHITECTURE.md`
- `docs/BACKLOG.md`
- `docs/SESSION_LOG.md`
- `docs/PROJECT_STATE.md`
- `docs/WORKFLOW.md`
- `docs/DECISIONS/**`
- Any existing GitHub Action

## Out of scope

- File consolidation (deleting BACKLOG.md, SESSION_LOG.md, WORKFLOW.md, renaming PROJECT_STATE → STATE) — that's M4b.
- The menu-driven "next" execution flow (numbered menu, reorder, drop) — that's M4b.
- Removing the `next-up` GitHub label — that's M4b.
- MCP server for live repo access — not building, mentioned only in chat discussion.
- Editing any ADR.
- Migrating historical tickets or backfilling CONTEXT.md content beyond the first auto-generated version.

## Test cases

This ticket is mostly tooling and docs; "tests" are content-level verifications plus one optional smoke test.

1. **Run `regen_context.py` against the current repo.** Inspect output. Every section listed in acceptance criterion A must be present and non-empty (except possibly `Open issues` and `Open PRs` if the repo happens to be at a quiet moment).
2. **Hallucination resistance check.** Open the generated `docs/CONTEXT.md`. Pick one function from `Public interfaces`. Open the actual source file. Verify the signature in CONTEXT.md matches the source. Repeat for one Pydantic model. If any mismatch, the AST extraction is wrong.
3. **Idempotency check.** Run the script twice in a row. The only diff between the two outputs is the timestamp on line 1.
4. **Action no-recursion check.** When the Action runs and commits `docs/CONTEXT.md`, the next push event (from the bot's own commit) must NOT trigger the Action again. Verify by watching the Actions tab after the first run.
5. **Optional smoke test in `tests/unit/test_regen_context.py`** — a single test that imports the script's main parsing functions and asserts they return non-empty results for `app/domain/models.py`. Not strictly required (the script is tooling, not domain code), but a 30-line smoke test catches AST regressions cheaply. The agent decides whether to add this; if added, it must pass.

## Notes

### Why this is HIGH priority

Every ticket Vivek drafts in chat depends on chat having accurate code knowledge. Without CONTEXT.md, the cost is recurring tickets with wrong assumptions, time spent in chat re-pasting code, and silent bugs from invented fields. With CONTEXT.md, the marginal cost of a precise ticket drops to near-zero.

### Why this comes before M4b

M4b consolidates the doc layout (deletes BACKLOG/SESSION_LOG/WORKFLOW, renames PROJECT_STATE, introduces the execution-time menu). It's a bigger change and benefits from CONTEXT.md being in place — the verification protocol gives chat the muscle memory to draft tickets correctly *before* the file layout reshuffles around it.

### Implementation order within the session

The agent should implement in this order to minimize the chance of being blocked:

1. Write `regen_context.py`. Run it locally. Iterate until output is good.
2. Update METHODOLOGY.md and AGENTS.md and README.md.
3. Write the GitHub Action.
4. Commit `docs/CONTEXT.md` as part of the PR (the first generated copy).
5. Push, open PR.

Do NOT try to test the Action's no-recursion behavior in the same PR — that can only be verified after merge, when the Action actually runs against main. If the Action misbehaves post-merge, fix-forward with a small follow-up ticket.

### Edge case: what if `gh` is rate-limited or unavailable in the Action?

The script should gracefully degrade. If `gh` calls fail, emit the section with a single line: `<gh CLI unavailable at generation time — section skipped>`. The rest of CONTEXT.md is still useful without GitHub state.

### Edge case: what if `data/portfolio.json` doesn't exist or is malformed?

Emit `## Data file shape` with `<portfolio.json not found or unparseable at generation time>` and continue. Do not crash the whole regeneration.

### Tone for the METHODOLOGY.md addition

Match the existing style of METHODOLOGY.md — second person at chat-surface level ("Chat must..."), concrete examples, anti-pattern callouts where useful. Do NOT make it a tutorial; it's a rules section.

### Files NOT to modify

To prevent scope creep, the agent must not edit:
- Any file under `app/`, `tests/`, `data/`, `docs/DECISIONS/`
- `docs/ARCHITECTURE.md`, `docs/BACKLOG.md`, `docs/SESSION_LOG.md`, `docs/PROJECT_STATE.md`, `docs/WORKFLOW.md`
- Any existing GitHub Action (`post-merge-housekeeping.yml`, CI, etc.)

If the agent feels it needs to edit one of these, stop and ask.
