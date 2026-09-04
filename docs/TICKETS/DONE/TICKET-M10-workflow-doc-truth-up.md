# TICKET-M10 — Truth-up the workflow docs and resolve the ghost housekeeping action

**Status:** IN_PROGRESS
**Priority:** MEDIUM
**Milestone:** Workflow Tooling
**Recommended model:** Sonnet — well-scoped, but touches `file.sh` logic and a CI workflow, not just prose.
**Estimated session length:** 1 – 1.5 hr
**Drafted by:** Vivek + Claude (chat 2026-06-04)
**Depends on:** —

> **After this ticket merges, the repo describes itself honestly.** No file references the retired `CONTEXT.md` pipeline, the post-merge action either does real work or is gone, and the decorative `**Status:**` line can no longer contradict the methodology.

---

## Problem

`docs/CONTEXT.md` and its `regen_context.py` / `update-context.yml` generator were retired on 2026-06-03 (`AGENTS.md` line 33 correctly reflects this), but several files still claim the pipeline exists:

- `README.md` line 11 (prose) **and** line 73 (a live link to `docs/CONTEXT.md` — now a dead link).
- `docs/VIVEK.md` line 10.
- `docs/METHODOLOGY.md` lines 36 and 191–193.
- `tools/README.md` lines 31–39 (documents both `regen_context.py` and the `update-context.yml` action — neither exists).

Separately, `.github/workflows/post-merge-housekeeping.yml` is a no-op: it runs `gh --version` and echoes `"Board updated. CONTEXT.md will regenerate via update-context.yml"` — referencing a workflow that does not exist — while never touching the board. The "Done" board transition that `AGENTS.md` Step 2 describes as automated is therefore not happening in this action.

Finally, all eight newly filed RD tickets carry `**Status:** DRAFT`, a state `docs/METHODOLOGY.md` line 85 explicitly says is invalid after filing. Nothing reads the field, so it is pure confusion.

## Acceptance criteria

- [ ] No file in the repo references `CONTEXT.md`, `regen_context.py`, or `update-context.yml` except as historical notes that explicitly say "retired" (e.g. the existing `AGENTS.md` note). Fix `README.md` (lines 11 + 73, including the dead link), `docs/VIVEK.md` (line 10), `docs/METHODOLOGY.md` (lines 36, 191–193), and `tools/README.md` (lines 31–39).
- [ ] `grep -ri "context.md\|regen_context\|update-context" --include='*.md' --include='*.yml' .` returns only intentional "retired" mentions.
- [ ] **Resolve the ghost workflow robustly.** Rewrite `post-merge-housekeeping.yml` so it actually moves the merged PR's linked issue's board item to **Done** (idempotent — a no-op if GitHub Projects' built-in automation already moved it). Remove the dead `update-context.yml` reference from its echo. If, after inspection, the maintainer confirms built-in Projects automation reliably handles Done, the alternative is to delete the workflow entirely and update `AGENTS.md` Step 2 to stop describing it. Pick one and make the docs match.
- [ ] `tools/file.sh` strips the decorative `**Status:**` line from each ticket file before committing it, so filed tickets cannot contradict the methodology. Existing RD tickets' `**Status:** DRAFT` lines are removed in this ticket as a one-time cleanup.

## Files likely touched

- `README.md`, `docs/VIVEK.md`, `docs/METHODOLOGY.md`, `tools/README.md`
- `.github/workflows/post-merge-housekeeping.yml`, `AGENTS.md` (only if the delete-the-workflow path is chosen)
- `tools/file.sh`, `docs/TICKETS/TICKET-RD*.md` (strip Status lines)

## Out of scope

- ❌ Restoring the `CONTEXT.md` generator — the project moved to "read the repo + query the board" deliberately; removal is the chosen direction.
- ❌ Any change to the ritual scripts or permission allowlist — that is TICKET-M9.

## Tests

- [ ] The grep guard above passes.
- [ ] `bash tools/file.sh` on a sample new ticket containing a `**Status:**` line commits the file with that line removed.
- [ ] `shellcheck` passes on `tools/file.sh`; the rewritten workflow is valid YAML.
- [ ] `pytest && ruff check . && mypy app/ && lint-imports` all pass.

## Notes

- This and TICKET-M9 are independent but both touch `docs/METHODOLOGY.md` and `tools/`; do this one first if both are queued, to keep M9's larger rewrite conflict-free.
