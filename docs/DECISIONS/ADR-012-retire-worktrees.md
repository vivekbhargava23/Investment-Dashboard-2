# ADR-012 — Retire git worktrees; implement on plain branches

**Status:** Accepted (2026-06-02)
**Date:** 2026-06-02
**Drafted by:** Vivek + Claude (Cowork session 2026-06-02)
**Supersedes / amends:** Supersedes [ADR-011](ADR-011-parallel-agent-workflow.md). Amends `AGENTS.md` Steps 5, 7, 9.

---

## Context

ADR-011 made "one git worktree per concurrent ticket" the default plumbing for every
ticket, on the premise that Vivek would routinely run multiple agents in parallel on
disjoint tickets. In practice:

- Tickets are picked and implemented one at a time, so the parallelism the worktrees
  existed to enable is rarely exercised.
- The worktree machinery has a real cost on every single ticket: an extra sibling
  directory, `data/` and `.env` symlinks, a `tools/run.sh <slug>` indirection for running
  the env, and a `tools/cleanup-worktrees.sh` pass that has to be remembered.
- Stale worktrees accumulate when cleanup isn't run — at decision time there were two
  prunable worktrees (`csv13`, `r2`) sitting around.
- A separate (non-Claude) agent recently reported a fabricated PR that included an invented
  worktree path, which surfaced how much incidental surface area the worktree step adds to
  the ritual without adding safety.

The worktree was never load-bearing for correctness. `main` is branch-protected, one
ticket = one branch = one PR, and sessions are stateless — none of that depends on
worktrees. Worktrees were an optimisation for a parallelism mode that isn't the day-to-day
reality.

## Decision

**Retire the worktree requirement. Agents implement each ticket on a plain branch created
off `main` in the single main checkout.**

`AGENTS.md` Step 5 becomes:

```bash
slug="ticket-<id-lower>-short-name"
git checkout -b "$slug"
```

No worktree creation, no `data`/`.env` symlinks, no `tools/run.sh <slug>` wrapper. Gate
checks (Step 7) and the app run with the conda env activated directly in the checkout:

```bash
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate investment-dashboard && \
  pytest && ruff check . && mypy app/ && lint-imports
```

The "how to test locally" block in Step 9 drops the worktree path and its pruned-worktree
fallback in favour of a single `git checkout <branch>` block.

### What about parallelism?

The *intent* of ADR-011 — parallel agents and multi-CLI comparison — is not abandoned. If
genuine parallel work resumes, an agent (or Vivek) can still run `git worktree add` ad hoc;
it's a native git command available at any time. It simply stops being a mandatory step in
the per-ticket ritual. Parallelism becomes opt-in rather than always-on.

## What does NOT change

- One ticket = one branch = one PR.
- `main` is branch-protected; agents never push to it.
- Vivek reviews and merges every PR; no agent merges its own.
- Steps 0–4, 6, 8, 9 (commit/log/push/board/PR) are otherwise unchanged.
- Board state mutations remain API-only via `gh`.

## Consequences

- **Pro:** Simpler ritual — one fewer concept, no symlinks, no `run.sh` indirection, no
  stale-worktree cleanup to remember.
- **Pro:** "How to test locally" is a plain `git checkout`, which always works.
- **Pro:** Fewer moving parts means fewer places for an agent to drift or fabricate.
- **Con:** Two agents in the same checkout would now collide on the working directory.
  Mitigation: don't run two agents in one checkout; if parallel work is needed, add a
  worktree ad hoc for that session only.
- **Con:** Feature branches accumulate locally over time (already true today). Mitigation:
  `git branch -d <merged-branch>` occasionally, or a periodic prune.

## Reversal cost

~0 minutes. Re-instating worktrees is reverting AGENTS.md Steps 5/7/9 to the ADR-011 text.
The methodology survives either way.

## Follow-ups (optional, not required by this ADR)

- `tools/run.sh` and `tools/cleanup-worktrees.sh` become dead once Step 5/7 no longer call
  them. Remove in a separate `chore:` ticket if desired.
- `docs/VIVEK.md` may still describe the worktree experience (added per ADR-011/TICKET-M9);
  trim that paragraph when convenient.

## Cross-references

- Supersedes: `docs/DECISIONS/ADR-011-parallel-agent-workflow.md`
- The amended ritual: `AGENTS.md` Steps 5, 7, 9
- Learning-mission context: `docs/LEARNING-GOALS.md`
