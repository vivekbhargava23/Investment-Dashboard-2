# TICKET-M9 — Collapse the session ritual into tools (cut token + permission overhead)

**Priority:** HIGH
**Milestone:** Workflow Tooling
**Recommended model:** Opus — cross-cutting change spanning new shell tooling, the permission allowlist, a rewrite of the AGENTS.md ritual, and dependency-aware `next` logic. A plausible-but-wrong rewrite of the ritual is costly and hard to detect.
**Estimated session length:** 2 – 3 hr
**Drafted by:** Vivek + Claude (chat 2026-06-04)
**Depends on:** —

> **After this ticket merges, a session is mostly implementation, not ceremony.** The mechanical ritual (gate check, branch + board moves, push + PR, `next` resolution) lives in a handful of allowlisted scripts. The agent runs one command per phase instead of emitting multi-line `gh`/`jq` blocks and chained `&&` commands that defeat the permission allowlist. `AGENTS.md` shrinks to "run these scripts; stop if they fail."

---

## Problem

Three compounding costs make every session expensive relative to the actual change:

1. **Permission tax.** Claude Code matches permissions by command prefix against the whole command string. `AGENTS.md` Step 7 tells the agent to chain the gate into one line (`source …conda.sh && conda activate … && pytest && ruff check . && mypy app/ && lint-imports`). That compound `&&` string matches *none* of the allow rules in `.claude/settings.json`, even though `pytest`, `ruff`, `source`, etc. are each individually allowlisted — so the agent prompts for approval every session. `settings.local.json` has accumulated cruft from clicking "always allow": one-off `sed -n '55,70p' …` entries, retired-worktree paths (`-csv13`, `-c4`), and a blanket `Bash(bash *)` that approves any script (and is both unsafe and still doesn't match the raw `source && …` chain).

2. **Token tax.** The board-state mechanics are inline `gh`/`jq` blocks repeated across Steps 0/2/5/8 of `AGENTS.md` (~25 lines emitted per session), plus ~830 lines of required reading before any work. Most of a session's tokens are ritual, not implementation.

3. **Ritual lives in prose.** `AGENTS.md` (389 lines) is simultaneously a runbook, a CLI, a policy doc, and a contract. The repetitive mechanics belong in scripts; the doc should explain intent and guardrails.

A side effect: `next` is dependency-blind. The current Backlog leads with RD6, which is blocked by RD1 + RD2 (neither Done), so the menu can offer blocked work first.

## Goals

- Move all repeatable mechanics into named, allowlisted scripts.
- One approval per script entry point; no per-step prompts; no compound `&&` commands that miss the allowlist.
- `next` shows every ticket but **flags** blocked ones and ranks smartly — it does not hide them.
- Shorter `AGENTS.md`: the ritual becomes "run `start_ticket`, implement, run `finish_ticket`, stop."

## Acceptance criteria

### Scripts (all POSIX / bash 3.2 + BSD-tool portable, like existing `tools/*.sh`; pass `shellcheck`)

- [ ] `tools/gate.sh` — activates the conda env and runs `pytest`, `ruff check .`, `mypy app/`, `lint-imports` in sequence; exits non-zero on the first failure with a clear message naming the failed check. This is the single gate entry point.
- [ ] `tools/start_ticket.sh TICKET-XXX` — asserts a clean working tree on `main`, pulls, creates the feature branch (`ticket-<id>-<slug>`), and moves the ticket's board item to **In progress**. Reuses the current branch if already on a matching feature branch (per the existing Step 5 rule). Prints the branch name.
- [ ] `tools/finish_ticket.sh TICKET-XXX` — runs `tools/gate.sh` (aborts on failure), pushes the current branch with `-u`, moves the board item to **In review**, and opens the PR via `gh pr create --base main` with a body containing `Closes #<N>` (issue number resolved from the ticket/board). Assumes the agent has already made its logical commits. Prints the PR URL.
- [ ] `tools/next.sh` — queries the board (`Ready` then `Backlog`, in board order), and for each ticket parses the `**Depends on:**` field from its file in `docs/TICKETS/`. Cross-references dependency status against the board. Prints a menu that:
  - shows **all** eligible and blocked tickets (blocked are never hidden),
  - marks blocked tickets with their blockers, e.g. `⛔ blocked by RD1, RD2`,
  - sorts: priority band first; within a band, eligible above blocked; among eligible, prefer the ticket that **unblocks the most** downstream Backlog tickets ("unblock score"),
  - surfaces the `**Recommended model:**` in brackets (existing behaviour),
  - lets a blocked ticket still be picked, but prints a warning first.
  - Robust parsing: handles `**Depends on:** —`, bare IDs (`RD1`), and full IDs (`TICKET-013`); treats a dependency whose issue is closed/Done as satisfied.
- [ ] `tools/doctor.sh` — preflight diagnostics, non-mutating: reports dirty tree, current branch vs `main`, any stale-doc references (e.g. lingering `CONTEXT.md`), board sanity, and a dependency report. Exits non-zero if it finds a blocking problem (dirty tree when one isn't expected, etc.).

### Permission allowlist

- [ ] `.claude/settings.local.json` is rewritten to a tight, intentional allowlist: the five script entry points above plus the read/edit/standard-git rules actually needed. **Remove** the one-off `sed -n` entries, the retired-worktree paths, and the blanket `Bash(bash *)`.
- [ ] Add `Bash(git push origin main:*)` and the `HEAD:main` variant to the `deny` list (defence-in-depth, since branch protection is not enforced on a free private repo).
- [ ] Verify (manually, noted in PR) that running `bash tools/gate.sh` and the other scripts does **not** trigger a permission prompt under the new allowlist.

### AGENTS.md / METHODOLOGY.md rewrite

- [ ] Rewrite the `AGENTS.md` ritual so Steps 0/2/5/8 call the scripts instead of inlining `gh`/`jq`. The guardrails stay verbatim: gates must pass, domain purity, never push to `main`, never self-merge, no runtime "while I'm here" scope creep. Net line count drops materially.
- [ ] `METHODOLOGY.md` ticket-sizing guidance changes from "smallest atomic change" to **"one coherent, independently-reviewable change (~1–2 hr)."**
- [ ] Relax "one ticket = one branch = one PR" to **"one coherent change = one PR; a PR may close several tightly-coupled tickets via multiple `Closes #N`."** Keep the rest of the non-negotiable rules unchanged.

## Files likely touched

- New: `tools/gate.sh`, `tools/start_ticket.sh`, `tools/finish_ticket.sh`, `tools/next.sh`, `tools/doctor.sh`
- `tools/README.md` (document the new scripts), `.claude/settings.local.json`
- `AGENTS.md` (ritual rewrite), `docs/METHODOLOGY.md` (sizing + PR-per-change rule)
- `tests/` — shell tests are not standard here; at minimum add a unit test for the dependency-parsing/ranking logic if it is implemented in Python, or document manual verification in the PR.

## Out of scope

- ❌ Auto-merge of any kind. Vivek still merges every PR by hand. (Explicit per the design discussion.)
- ❌ Programmatic board reordering beyond what `file.sh` already does (ADR-010 unchanged).
- ❌ Paying for GitHub Team / making the repo public to get enforced branch protection — handled by the deny-rule + the manual merge gate instead.
- ❌ Consolidating the RD0–RD7 tickets — that is a chat re-draft, not this ticket.

## Tests

- [ ] `shellcheck` passes on all new `tools/*.sh` (CI already runs shellcheck on `tools/`).
- [ ] `tools/next.sh` against the current board surfaces RD0/RD1/RD4/RD5 as eligible and flags RD2 (RD1), RD3 (RD0), RD6 (RD1, RD2), RD7 (RD4) as blocked, in priority-band order.
- [ ] `tools/gate.sh` exits non-zero (and names the check) when any of pytest/ruff/mypy/lint-imports fails, and zero when all pass.
- [ ] `pytest && ruff check . && mypy app/ && lint-imports` all pass (the change is mostly tooling/docs; keep the app green).
- [ ] Manual: a full dry-run of `start_ticket` → implement-noop → `finish_ticket` on a throwaway branch produces a PR with `Closes #N` and the board moves In progress → In review, with no permission prompts.

## Notes

- This ticket deliberately edits `AGENTS.md` and `METHODOLOGY.md`; that is allowed because this *is* the dedicated ticket for it (the "no editing methodology mid-implementation" rule targets incidental edits).
- Bootstrapping: the implementing agent does not need to use the new ritual to build it — it edits files and scripts normally, then runs the existing gate before committing.
- Root-cause reference for the permission tax: compound `&&` commands are evaluated as one string and match no prefix rule; the fix is single allowlisted script entry points, not broader wildcards.
- If TICKET-M10 (doc truth-up) is in flight at the same time, expect a small rebase in `docs/METHODOLOGY.md` and `tools/README.md`; do M10 first if convenient.
