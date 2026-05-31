# ADR-011 — Parallel agent implementation via git worktrees; multi-CLI is first-class

**Status:** Accepted (2026-05-31)
**Date:** 2026-05-31
**Drafted by:** Vivek + Claude (Cowork session 2026-05-31)
**Supersedes / amends:** None (extends `METHODOLOGY.md` "Single source of truth" and `AGENTS.md` Step 1)

---

## Context

The current workflow assumes one agent, one terminal, one ticket at a time. As of 2026-05-31 there are 14 open tickets in `Backlog`. Sequential execution would take weeks; many of these tickets touch disjoint files and could be implemented in parallel without conflict.

Vivek wants to:
1. Run multiple agents at the same time on different tickets.
2. Use non-Claude CLIs (Codex, Aider, Gemini CLI) alongside Claude Code to compare their behaviour on the same project.
3. Have the workflow gracefully handle "two terminals, two branches" without manual git gymnastics.

The current workflow is technically compatible with all three — sessions are stateless, one ticket per branch, main is branch-protected, and `AGENTS.md` is a portable rulebook. But the convention isn't documented, and two agents in the same checkout will fight over the working directory.

## Decision

**Parallel implementation is a first-class workflow, and worktree + environment setup is automated. The agent owns the plumbing; Vivek owns the picking.** Any CLI that honours `AGENTS.md` is supported.

### The Vivek-side experience (target)

1. `cd ~/Desktop/Apps/Investment-Dashboard-2`
2. `claude` (or `codex`, `aider`, etc.)
3. `next` or `implement TICKET-XXX`
4. (PR shows up in inbox.)

That is the entire flow. No `git worktree add`, no `conda activate`, no manual cd. If Vivek runs three terminals from step 1, three parallel sessions start without him touching git or conda once.

### The agent-side behaviour (what gets automated)

`AGENTS.md` Step 5 is amended (by TICKET-M9) so that when the agent is sitting in the **main checkout** and picks a ticket:

1. Compute slug: `ticket-<id-lowercased>-<short-name>`.
2. Run: `git worktree add "../$(basename $REPO_ROOT)-${id-lowercased}" -b "$slug"`.
3. `cd` into the new worktree for all subsequent steps.
4. Prefix every shell call that needs Python (`pytest`, `ruff`, `mypy`, `lint-imports`, `streamlit run`) with conda env activation:
   `source $(conda info --base)/etc/profile.d/conda.sh && conda activate investment-dashboard && <cmd>`.
5. Continue Steps 6–9 of the existing ritual unchanged.

When the agent is already running inside a worktree (e.g. Vivek `cd`'d in to address PR review comments), Step 5 detects this — `HEAD` is not `main` — and reuses the existing branch instead of creating a new worktree.

After PR merge, an automated cleanup task removes the worktree:

```bash
git worktree remove ../Investment-Dashboard-2-h1
git worktree prune
```

The post-merge GitHub Action can't reach Vivek's local worktrees, so cleanup is a small `tools/cleanup-worktrees.sh` script that scans for branches deleted upstream and removes their worktrees locally. Vivek runs it occasionally; if it becomes friction, a shell hook on `git fetch` can run it automatically.

### Convention summary

1. **One worktree per concurrent ticket**, named `<repo>-<ticket-id-lower>`, sibling of the main checkout:
   ```
   ~/Desktop/Apps/
   ├── Investment-Dashboard-2/           # main checkout (always on main)
   ├── Investment-Dashboard-2-h1/        # auto-created for TICKET-H1
   ├── Investment-Dashboard-2-c2/        # auto-created for TICKET-C2
   └── Investment-Dashboard-2-m8/        # auto-created for TICKET-M8
   ```

2. **The agent creates the worktree.** Not Vivek. Per TICKET-M9.

3. **The agent activates the conda env per shell call.** Not Vivek's outer shell. The agent's subshells handle it.

4. **The main checkout stays on `main`.** Branches live only in worktrees. This satisfies "Step 1: verify clean main" automatically.

5. **Each worktree runs its own agent.** Any CLI: `claude`, `codex`, `aider`, `gemini`, `cursor`. All read `AGENTS.md` at their working directory.

6. **Pick tickets explicitly when running in parallel.** Use `implement TICKET-XXX` form, not `next`. Two agents both calling `next` would see the same Ready/Backlog state. Explicit picking removes the race. (A future improvement: `next` could optimistically move the picked card to `In progress` before returning the choice, which would race-protect even concurrent `next` calls. Worth a follow-up ticket if it bites.)

### Multi-CLI compatibility

The agent ritual in `AGENTS.md` is portable. Verified behaviours per CLI:

- **Claude Code** — reads `AGENTS.md` and per-module `CLAUDE.md` files. Full ritual support, including board mutations via `gh`.
- **OpenAI Codex CLI** — reads `AGENTS.md`. Has shell + file edit tools. Full ritual support assuming `gh` is on PATH.
- **Aider** — reads `AGENTS.md` if pointed at it via `--read AGENTS.md`. File-edit-focused; `gh` calls work because Aider runs commands in the same shell.
- **Cursor CLI / Gemini CLI** — emerging support; verify case-by-case.

The ritual depends only on three things being available at the shell: `git`, `gh` (authenticated), `jq`. Any CLI agent with shell access can execute it.

### Ticket dependency notation

Tickets sometimes touch the same files. To avoid stepping on each other, add a `**Dependencies:**` line below `**Milestone:**` in tickets when applicable:

```markdown
**Milestone:** UI polish
**Dependencies:** TICKET-R5 (cache consolidation must merge first)
```

`tools/file.sh` doesn't parse this today — it's a human-facing hint for which tickets are safe to parallelize. If two unrelated tickets touch the same file by coincidence, that's not a dependency; it's just a merge conflict to resolve at PR time.

### What does NOT change

- One ticket = one branch = one PR. Worktrees enforce this naturally.
- Main is branch-protected. Worktrees can't write to main.
- The ritual itself is unchanged. Steps 1–9 run identically in each worktree.
- Vivek still reviews and merges every PR. No agent merges its own PR.
- Board state mutations are still owned by `tools/file.sh` and the agent's Steps 5/8c/0 — worktrees don't change who writes the board.
- `CONTEXT.md` regeneration is still post-merge. Parallel branches see the same `CONTEXT.md` at session start, which is fine because they're working on disjoint tickets.

## Reasoning

1. **The architecture already supports it.** Stateless sessions + one-ticket-per-branch = inherently parallel. Worktrees are the missing infrastructure piece.
2. **It compresses the timeline.** Sequential implementation of the current 14-ticket queue is ~25 hours of agent time. Three-way parallel cuts that by ~60% (limited by the dependency chains).
3. **Multi-CLI comparison is mission #2.** Per `LEARNING-GOALS.md`, comparing how Claude Code, Codex, and Aider handle the same `AGENTS.md` ritual is one of the explicit learning goals. The parallel workflow enables it.
4. **Worktrees are a git native feature.** No new tools, no scripts, no dependencies. `git worktree` ships with git 2.5+ (2015).
5. **Disjoint-file checking is human work.** Heuristics could check overlap before parallelizing, but for a personal project with a clear ticket queue, eyeballing the "Files likely touched" section is faster.

## Consequences

- **Pro:** 2–3× implementation throughput on the current queue.
- **Pro:** Multi-CLI learning becomes a normal Tuesday, not an experiment.
- **Pro:** Worktree cleanup is one command after each merge.
- **Pro:** No methodology violation — every rule still holds; we're just running multiple instances of the ritual.
- **Con:** Disk usage grows by one full checkout per concurrent ticket. The repo is small (<50MB); negligible.
- **Con:** Two agents picking the same ticket via `next` is a real race. Mitigation: use explicit `implement TICKET-XXX` form for parallel runs.
- **Con:** Two agents touching overlapping files produce merge conflicts at PR time. Mitigation: read each ticket's "Files likely touched" section before parallelizing; sequence what overlaps.
- **Con:** Each new CLI tool needs verification that it executes the ritual correctly. Mitigation: verify in a no-op ticket first; treat each CLI as untrusted until proven.

## Edge cases

1. **Worktree on a branch that's deleted upstream.** `git worktree remove --force` handles it cleanly. Or `git worktree prune` after the branch is gone.
2. **Two agents both running `Step 1` (verify clean main) at the same time.** Each runs in its own worktree; each sees a clean state. No conflict.
3. **Branch protection rejects a push.** Same handling as today — the agent stops and reports. Per-branch, per-worktree.
4. **One agent's PR merges; the other's PR now has conflicts with main.** The second agent's Step 1 (next session) would catch this. Or a manual rebase: `cd worktree-2 && git pull --rebase origin main`. Standard git.
5. **Vivek runs `tools/file.sh` while two agents are working.** `file.sh` operates only on main, only on the main checkout. Worktrees are unaffected.
6. **Both agents try to push the same branch name.** Impossible — branches are per-worktree, and you can't add a worktree on an already-checked-out branch. Git enforces this.
7. **The agent in Worktree 2 reads `CONTEXT.md` regenerated by Worktree 1's just-merged PR.** Fine. CONTEXT.md is auto-regenerated post-merge by GitHub Actions. Both worktrees `git pull origin main` at session start (Step 1).
8. **An agent runs `next` in a worktree (not main).** The board query works fine — it's a network call, not a git operation. The board doesn't know about worktrees.
9. **A Codex run leaves uncommitted changes in its worktree.** Same handling as a Claude Code session that fails mid-implementation: agent reports via Stop Conditions; Vivek either has the agent finish or wipes the worktree.
10. **Per-CLI quirks in handling `AGENTS.md`.** Some CLIs may not auto-load module-level instruction files. The root `AGENTS.md` says "read these per-module files when working on a module" — agents that don't follow the link are still functional but less precise. Document per-CLI behaviour in `LEARNING-GOALS.md` as it accumulates.

## Reversal cost

Stop using worktrees; revert to sequential single-agent workflow. ~0 minutes; it's purely a convention. The methodology survives either way.

## Alternatives considered

- **Separate full clones instead of worktrees.** Rejected — duplicates `.git` per clone, slower to set up, no benefit over worktrees.
- **One CLI agent driving a multi-step parallel orchestration.** Rejected — the Claude Agent SDK supports this via subagents, but it adds complexity. The git-worktree pattern is the simpler primitive; subagent orchestration is a separate learning thread (`LEARNING-GOALS.md`).
- **A `tools/worktree.sh` helper script.** Considered. Deferred — `git worktree add/remove` is two commands; a wrapper saves three keystrokes. File only if real friction shows up.
- **Adding parallelism rules to `AGENTS.md`.** Rejected — `AGENTS.md` is per-session rules. Parallel orchestration is a methodology concern; lives in this ADR and the cross-reference in `METHODOLOGY.md`.

## Cross-references

- The learning-mission context for this ADR: `docs/LEARNING-GOALS.md`
- The agent ritual being parallelized: `AGENTS.md` Steps 1–9
- Per-module instruction files (read in each worktree): `app/*/CLAUDE.md`

## Implementation

TICKET-M9 implements the agent-side automation (AGENTS.md Step 5 amendment, `tools/cleanup-worktrees.sh`, env-activation pattern, and a one-paragraph addition to `docs/VIVEK.md` showing the new Vivek-side experience).
