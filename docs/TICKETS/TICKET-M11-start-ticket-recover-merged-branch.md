# TICKET-M11 — Workflow handoff hardening and Done-ticket archive

**Priority:** HIGH
**Status:** IN_PROGRESS
**Milestone:** Investment Panel
**Recommended model:** Sonnet — bounded workflow logic with subprocess-facing regression tests.
**Estimated session length:** 1 hr
**Drafted by:** Vivek + Codex (implementation session 2026-09-04)
**Depends on:** none

> **After this ticket merges:** a fresh implementation session can run
> `bash tools/start_ticket.sh TICKET-XXX` while still checked out on the clean,
> merged branch from the previous session. The starter safely returns to an updated
> `main` and creates the next ticket branch without manual intervention.

## Problem

The session ritual deliberately stops immediately after opening a PR, leaving the
workspace on that ticket's feature branch. After Vivek merges the PR, the next session
starts from the same branch. `start_ticket` currently rejects every non-matching feature
branch, even when its PR is already merged and its working tree is clean. This makes the
documented normal end state incompatible with starting the next ticket.

## Implementation

- In `tools/ticket_workflow.py`, preserve same-ticket branch reuse.
- When starting a different ticket from a non-`main` branch:
  - refuse a dirty working tree without stashing or changing branches;
  - verify through GitHub that the current branch has a merged PR;
  - refuse open, unmerged, or PR-less branches;
  - for a merged branch, check out `main`, fast-forward it from `origin/main`, and create
    the requested ticket branch.
- Keep failures explicit and safe. A GitHub lookup failure must stop rather than assume
  the branch is merged.
- Add unit coverage for same-ticket reuse, clean merged-branch recovery, dirty-tree
  refusal, and unmerged/PR-less branch refusal.
- Update `AGENTS.md`, `tools/README.md`, and `docs/VIVEK.md` so the automatic handoff and
  its refusal cases are documented consistently.
- Make GitHub rate limiting non-destructive: skip the `In review` -> `Done` reconcile with
  a warning, and turn a throttled `In progress` board move into an explicit resumable
  message rather than a half-started ticket.
- Add `tools/archive.sh` (`archive` subcommand) moving board-`Done` ticket specs into
  `docs/TICKETS/DONE/` with `git mv`, plus `--dry-run`. Make every ticket lookup glob
  `docs/TICKETS` recursively first, so archiving can never hide a ticket from the
  workflow. Surface pending archives in `doctor`.
- Close the instruction gaps that let the previous session improvise: hard rules and a
  session preflight at the top of `AGENTS.md`, stop conditions for script failure and
  branch refusal, and explicit bans on self-filed tickets and blind retries of
  board-mutating scripts.

## Acceptance criteria

- [ ] Starting from a clean branch whose PR is merged switches to updated `main` and
      creates the requested ticket branch.
- [ ] Starting from a dirty different-ticket branch changes nothing and reports the
      dirty files.
- [ ] Starting from an open, unmerged, or PR-less different-ticket branch changes
      nothing and explains why.
- [ ] Starting the same ticket from its existing branch still reuses that branch.
- [ ] A rate-limited board move leaves the branch usable and names the resumable rerun.
- [ ] `bash tools/archive.sh` moves only board-`Done` specs, is idempotent, and a ticket
      still resolves by ID once archived.
- [ ] `AGENTS.md` states, before any other section, that Vivek picks tickets and that
      stopping is a successful outcome.
- [ ] Workflow documentation matches the implemented behavior.
- [ ] `bash tools/gate.sh` passes.

## Out of scope

- Automatically deleting merged local or remote branches.
- Starting from a branch with uncommitted changes.
- Changing the finish-ticket or board-ranking behavior.
