# TICKET-M3 — Tooling self-heal: branch guard, auto-milestone, Next-up reconciliation, GitHub Actions post-merge housekeeping

**Status:** QUEUED
**Priority:** HIGH
**Estimated session length:** 1.5 – 2 hr
**Drafted by:** Vivek + Claude (chat 2026-05-12)
**Implemented by:** _pending_
**Depends on:** TICKET-M1 (existing GitHub label/milestone setup), TICKET-M2 (WORKFLOW.md — minor cross-reference touch-ups in scope)

> **After this ticket merges, the ticket-filing flow is self-healing.** `tools/draft_ticket.sh` refuses to run from any branch other than `main`. Missing Milestone sections in `BACKLOG.md` are created automatically instead of erroring. The "Next up" lists in both `PROJECT_STATE.md` and `BACKLOG.md` are reconciled against GitHub Issues on every run — no more stale `1.`, `1.`, `1.` artifacts. A new GitHub Actions workflow does the "MERGED" bookkeeping the moment Vivek merges a PR — no waiting for the next implementation session. AGENTS.md Step 2 becomes a verification step instead of the primary path.

---

## Problem

The current tooling has a tangle of latent bugs that surfaced during the C1 (TICKET-025) drafting session:

1. **`draft_ticket.sh` ran from a non-main branch (`ticket-M2-add-workflow-md`).** It would have committed and pushed to that branch. The script halted for an unrelated reason (missing milestone in BACKLOG.md), which is the only reason no damage occurred.
2. **`update_backlog.py` errored** because the `Company Deep Dive` Milestone section didn't exist yet. Required manual edit before the script could run.
3. **`update_state.py` produced `1.`, `1.`, `1.`** in PROJECT_STATE.md because it only ever prepends — never demotes superseded entries (in-review tickets, merged tickets) off the "Next up" list.
4. **Housekeeping lag.** When Vivek merges a PR, ticket status (`IN_REVIEW` → `MERGED`), PROJECT_STATE.md "Done" / "In review" sections, and BACKLOG.md status column don't update until the *next* implementation session runs Step 2. If Vivek drafts 3 tickets between implementations, all 3 see stale state.
5. **Cosmetic but real:** when `update_backlog.py` did succeed (for TICKET-025), it inserted the row in a way that broke the `|---|` table-separator placement. Visible right now in BACKLOG.md's Company Deep Dive section.

The root cause of (1)–(3) is that the scripts assume a perfect prior state and don't reconcile against ground truth. The root cause of (4) is that housekeeping is tied to the implementation agent's session lifecycle, not to the GitHub event that actually represents "merged."

This ticket fixes all five, plus tightens the contract between the tooling, AGENTS.md, and GitHub Actions.

---

## Architectural decisions implemented by this ticket

### 1. `main`-only enforcement in `draft_ticket.sh` (hard fail)

`draft_ticket.sh` is the entry point for filing a ticket. It writes a file, mutates two markdown docs, creates a GitHub issue, and pushes to `main`. Every one of those side effects assumes the working tree represents `main`.

When run from a feature branch, the script's last line (`git push origin main`) literally pushes the local `main` to origin — which is fine if `main` is current, but the *commit it just made* lands on the **current branch**, not main. End result: ticket commit on a feature branch, no ticket commit on main, and you don't know until you look.

Fix: at the top of `draft_ticket.sh`, immediately after the `cd "$(git rev-parse --show-toplevel)"` line:

```bash
CURRENT_BRANCH="$(git branch --show-current)"
if [ "$CURRENT_BRANCH" != "main" ]; then
  echo "Error: tools/draft_ticket.sh must be run from main." >&2
  echo "  You are on: $CURRENT_BRANCH" >&2
  echo "  Run: git checkout main && git pull" >&2
  exit 1
fi
```

Also require a clean working tree (no uncommitted changes that would get swept into the script's `git add`):

```bash
if [ -n "$(git status --porcelain)" ]; then
  echo "Error: working tree is dirty. Commit or stash before drafting a ticket." >&2
  git status --short >&2
  exit 1
fi
```

Both checks fire before the script writes anything to disk or hits the GitHub API. Hard fail; no auto-recovery, no auto-switch — the user knows exactly what to do.

### 2. Auto-create missing Milestone sections in `update_backlog.py`

Current behaviour: error out with a list of available milestones. User has to hand-edit BACKLOG.md.

New behaviour: if the named Milestone section doesn't exist in BACKLOG.md, **create it** just before the "Next up (in execution order)" section at the bottom. The auto-created section uses this template:

```markdown
## Milestone — {milestone_name}

| ID | Title | Status | Priority | Est |
|---|---|---|---|---|

---

```

(Header row, separator row, then a blank table — the new ticket row gets appended immediately after.)

Why insert before "Next up": "Next up" is the last section in BACKLOG.md. New milestones go between the last existing milestone and the "Next up" closer. The Investment Panel milestone (which is also at the bottom) stays where it is — but new milestones get inserted *before* it. The rule: find the `## Next up` line; insert the new milestone immediately before it (with an `---` separator below).

The function gets a short comment in `update_backlog.py` saying when this triggers. No new CLI flag — auto-create is the default behaviour.

### 3. Fix the table-separator placement bug

Current behaviour (BACKLOG.md as it stands today, Company Deep Dive section):

```markdown
## Milestone — Company Deep Dive

| ID | Title | Status | Priority | Est |
| TICKET-025 | Company data layer: ... | QUEUED | HIGH | 1.5 – 2 hr |
|---|---|---|---|---|
```

The separator `|---|---|...` landed *after* the data row, not after the header row. Cosmetically it still renders OK in most markdown viewers, but it's wrong.

Root cause in `update_backlog.py`: the insertion point logic finds the "last table row" and appends after it. On a fresh section with just `header + separator`, the separator is the last row, so the data row goes after it.

Fix: change the insertion logic to find the position **immediately before the first blank line after the last table row** (or the end of the section, whichever comes first). The insertion point is always at the bottom of the table proper, not after stray separators.

In the same pass, **fix the existing malformed Company Deep Dive section** in BACKLOG.md as a one-off correction commit inside this ticket.

### 4. Next-up reconciliation: a single source-of-truth rebuild

The bug is that both `update_state.py` and `update_backlog.py` *prepend* to "Next up" lists without demoting existing entries. With 3 successive `NEXT_UP=true` ticket drafts (no merges in between), you get 3 entries at the top, only one of which is actually next.

Fix: replace the prepend logic with a **full rebuild from GitHub Issues**.

The new logic, common to both scripts (extracted into a shared helper `tools/_next_up.py`):

```python
def rebuild_next_up_list() -> list[tuple[str, str]]:
    """Query GitHub Issues, return the ordered Next-up list.

    Returns: list of (ticket_id, title) tuples in execution order.

    The ordering rule:
    1. The issue currently labelled `next-up` goes first (there should be exactly one).
    2. All other QUEUED issues (label `queued`, no `next-up`), sorted by:
       - milestone "priority hint" (Company Deep Dive comes before Investment Panel etc.
         — derived from BACKLOG.md milestone order)
       - then by issue number ascending (FIFO).
    3. IN_REVIEW / MERGED / CLOSED issues are excluded.
    """
```

Both `update_state.py` and `update_backlog.py` call this helper instead of prepending. The "Next up" section in each file gets fully rewritten on every run — header + a clean numbered list + the trailing `*Panel framework brainstorm session*` line preserved if it was already there (matched by the literal `*` prefix; this is a known free-form entry).

For `PROJECT_STATE.md`, the "Next up 📋" section rewrite preserves the `### Next up 📋` header and the section terminator (the blank line + `See ...BACKLOG.md...`).

For `BACKLOG.md`, the "Next up (in execution order)" section rewrite preserves the header and the trailing `**Workflow reminder:**` block.

The rebuild is **always called**, whether or not `NEXT_UP=true` was passed. Even drafting a `NEXT_UP=false` ticket reconciles the list — it doesn't add the new ticket to "Next up", but it does drop any stale entries.

### 5. `tools/sync_state.py` — standalone reconciliation

The rebuild helper from §4 is also exposed as a standalone command:

```bash
python3 tools/sync_state.py
```

What it does:
- Queries GitHub Issues for all open QUEUED / IN_PROGRESS / IN_REVIEW tickets.
- Rebuilds the "Next up" lists in both `PROJECT_STATE.md` and `BACKLOG.md`.
- Updates the "In review 👀" section of `PROJECT_STATE.md` from GitHub (issues with linked open PRs).
- Updates the "In progress 🚧" section of `PROJECT_STATE.md` from GitHub (issues labelled `in-progress`).
- Does **not** touch the "Done ✓" section (that's append-only history, managed by the GitHub Actions workflow in §6).
- Does **not** commit. The user (or the agent's Step 2) runs this and reviews the diff before committing.

Use cases:
- Vivek manually reconciling after a state-drift incident.
- The agent's Step 2 calling this as the verification mechanism (per §7).
- A future scheduled CI job (out of scope for this ticket).

Output: prints a one-line summary per section showing the count and any changes made. Returns non-zero exit code if nothing could be reconciled (e.g. `gh` not authenticated).

### 6. GitHub Actions workflow: post-merge housekeeping

New file: `.github/workflows/post-merge-housekeeping.yml`.

Trigger: PRs merged to `main`.

What it does:

1. Parse the merged PR body for `Closes #(\d+)` to find the ticket's issue number.
2. Fetch the ticket file path from the issue body (issues created by `draft_ticket.sh` start with `Ticket file: \`docs/TICKETS/...\``).
3. In a fresh checkout of `main`:
   a. Update the ticket file: `Status: IN_REVIEW` → `Status: MERGED`.
   b. In `PROJECT_STATE.md`: move the ticket from "In review 👀" to "Done ✓" (with the PR number appended in the format used by existing entries: `TICKET-XXX — Title (PR #N)`).
   c. In `BACKLOG.md`: update the ticket's status column to `MERGED`.
   d. Update the "Last updated:" line at the top of `PROJECT_STATE.md` to today's date.
   e. Call `tools/sync_state.py` to reconcile "Next up" lists.
4. Commit with message `chore: post-merge housekeeping for TICKET-XXX (#N) [skip ci]`.
5. Push to `main`.

The `[skip ci]` suffix prevents CI from running on this housekeeping commit, since the diff is doc-only.

The workflow runs as the `github-actions[bot]` user, which requires a branch-protection exemption. See §9.

If any of steps 1–3 fail (PR body has no `Closes #N`, issue body has unexpected format, ticket file not at the expected path, regex didn't match), the workflow **fails loudly** — does not commit a partial update. Vivek sees a red check on the Actions tab and can run `tools/sync_state.py` manually plus edit the ticket file directly. The failure mode is "nothing happened, fix it by hand" — never "half-done state on main."

### 7. AGENTS.md Step 2 becomes a verification step

Current Step 2 (paraphrased): "Query `gh issue view <N>`. If CLOSED, do the housekeeping commit."

New Step 2: "Query `gh issue view <N>`. If CLOSED, **verify** that PROJECT_STATE.md, BACKLOG.md, and the ticket file already reflect MERGED status (the GitHub Actions workflow should have done this within seconds of the merge). If they don't, run `tools/sync_state.py` and commit the result with `chore: reconcile state` before proceeding to Step 3."

The agent stays as the safety net — if Actions failed, the agent picks up the slack at the start of the next session. This means we don't lose anything that today's flow provides; we add a faster primary path that almost always pre-empts the agent.

The full diff to AGENTS.md is small: replace the Step 2 instructions with the new wording, add a note at the bottom of the "When Vivek says 'I merged it'" section saying "GitHub Actions handles the housekeeping — Step 2 of the next session verifies it landed."

### 8. WORKFLOW.md cross-reference touch-ups

The Section 4 ("Filing a ticket") description should mention that the script now self-checks branch and milestone state. The Section 5 ("Implementing a ticket") description should mention that housekeeping is automatic on merge. These are small wording updates — no structural change.

### 9. Branch protection exemption for `github-actions[bot]`

The current rule is "Only Vivek can merge to main." The exemption: `github-actions[bot]` can push directly to `main` *only* for commits where the commit message starts with `chore: post-merge housekeeping`.

This can be enforced two ways:

**Option A (chosen):** Add `github-actions[bot]` to the branch protection rule's "allow specified actors to bypass required pull requests" list. The exemption is per-user, not per-commit-message; we trust the workflow's own logic to only commit housekeeping commits.

**Option B (rejected):** Have the workflow open a tiny PR and auto-merge it. Adds PR noise; equivalent security since the bot would still need merge permission.

Option A is what GitHub recommends for this pattern. The acceptance criteria below include a manual step for Vivek to add this exemption via the GitHub UI (Settings → Branches → main → Bypass pull requests) — the workflow itself can't grant its own exemption.

### 10. `setup_github.sh` milestone list — left alone

Out of scope. New milestones (like `Company Deep Dive`) are created via the one-liner Vivek already knows:

```bash
gh api -X POST repos/$(gh repo view --json nameWithOwner -q .nameWithOwner)/milestones \
  -f title='<Name>' -f description='<desc>'
```

If `setup_github.sh` is re-run later, missing milestones can be added there as a one-line addition. Hardcoded for now; if this becomes annoying in 6 months, file a separate ticket then.

---

## Acceptance criteria

### `tools/draft_ticket.sh` — branch guard + clean-tree guard

- [ ] Immediately after `cd "$(git rev-parse --show-toplevel)"`, the script checks `git branch --show-current`. If not `main`, prints the three-line error from §1 and exits 1. Verified by running from a feature branch.
- [ ] Immediately after the branch check, the script checks `git status --porcelain`. If non-empty, prints "working tree is dirty" + the `git status --short` output and exits 1. Verified by running with an uncommitted file.
- [ ] Both checks fire **before** any file is written, any GitHub API call is made, and any `git` mutation. (Effectively: no side effects on failure.)
- [ ] The script unconditionally calls `python3 tools/sync_state.py` at the start (after the guards, before parsing the spec). This reconciles "Next up" lists against GitHub even if the new ticket itself isn't `NEXT_UP=true`. Output of sync_state is shown to the user; if it returns non-zero, the script halts.

### `tools/update_backlog.py` — auto-create milestone, fix separator placement

- [ ] When the named Milestone section doesn't exist in BACKLOG.md, the script creates it per §2 instead of exiting. Verified by deleting the Company Deep Dive section locally and re-running with `--milestone "Company Deep Dive"` — section is recreated correctly.
- [ ] The new section template is exactly:
  ```
  ## Milestone — {name}

  | ID | Title | Status | Priority | Est |
  |---|---|---|---|---|

  ---

  ```
  (Header row, separator row, blank line, `---` rule, blank line. The new ticket row gets appended between the separator row and the blank line.)
- [ ] Insertion point fix per §3: the new row is appended **immediately after the last table row that starts with `|---` or `|`**, *before* any blank line that ends the table. Verified by re-running on a freshly-auto-created section: the row appears between separator and blank line, not after a stray separator.
- [ ] The script no longer maintains its own "Next up" prepend logic. It calls the shared helper from `tools/_next_up.py` per §4.
- [ ] All existing CLI flags preserved (`--id`, `--title`, `--milestone`, `--priority`, `--estimate`, `--next-up`).

### `tools/update_state.py` — rebuild Next up from GitHub

- [ ] The `update_next_up` function no longer prepends. It calls the shared helper from `tools/_next_up.py` to get the canonical ordered list, then fully rewrites the "Next up 📋" section.
- [ ] The rewrite preserves: the `### Next up 📋` header, the trailing line `See \`docs/TICKETS/BACKLOG.md\` for the full ticket list with statuses.`, and any blank lines.
- [ ] The `*Panel framework brainstorm session*` free-form entry, if present at the end of the previous list, is preserved at the end of the new list.
- [ ] When called with `--id TICKET-XXX --title "..."` arguments, those arguments are now redundant if the issue is already on GitHub (the script will pick it up from there). They're kept for backwards compatibility with `draft_ticket.sh` but no longer affect output. Add a comment in the script explaining this.

### `tools/_next_up.py` — new shared helper

- [ ] New module with public function `rebuild_next_up_list() -> list[NextUpEntry]` per §4. `NextUpEntry` is a `dataclass` with fields `ticket_id: str`, `title: str`, `is_next_up: bool` (true only for the single issue with the `next-up` label).
- [ ] Ordering rule exactly as in §4: `next-up`-labelled issue first; remaining QUEUED issues sorted by (milestone order in BACKLOG.md, then issue number ascending).
- [ ] **Milestone order extraction:** parse BACKLOG.md once, build a `dict[milestone_name, int]` mapping each `## Milestone — <name>` to its file order (0, 1, 2, …). Use this to sort.
- [ ] **GitHub query:** uses `gh issue list --label queued --state open --json number,title,labels,milestone` (single call, paginated if needed; the existing repo is well under 100 open issues so a single page is sufficient).
- [ ] **Filtering:** issues with the `superseded` or `blocked` labels are excluded from "Next up" (they're still QUEUED but not actionable).
- [ ] **Free-form entries** (like `*Panel framework brainstorm session*`) are not in the GitHub query result. They're handled by the *callers* of this helper, which preserve them from the existing file content.
- [ ] **Public helper for "preserve free-form trailing entries":** `extract_freeform_entries(section_text: str) -> list[str]` returns lines starting with `*` and ending with `*` (italic markdown). Used by both `update_state.py` and `update_backlog.py`.
- [ ] **Returns a sensible result when offline:** if `gh` returns non-zero, raise a clear exception (e.g. `RuntimeError("gh CLI not authenticated or offline; cannot rebuild Next up")`). Callers decide whether to halt or skip.
- [ ] Module is importable: `from tools._next_up import rebuild_next_up_list`.

### `tools/sync_state.py` — new standalone reconciliation script

- [ ] New module per §5. CLI entry point: `python3 tools/sync_state.py`.
- [ ] Rebuilds:
  - "Next up 📋" section in `PROJECT_STATE.md`
  - "Next up (in execution order)" section in `BACKLOG.md`
  - "In review 👀" section in `PROJECT_STATE.md` (issues with linked open PRs — query: `gh issue list --state open --json number,title,...` then filter to issues with a linked PR via `gh pr list --state open --json number,headRefName,body` and matching `Closes #N`)
  - "In progress 🚧" section in `PROJECT_STATE.md` (issues labelled `in-progress`)
- [ ] Does **not** touch "Done ✓" section.
- [ ] Does **not** commit. Just edits the files in place. Prints a one-line summary per section.
- [ ] Exit code 0 on success, 1 on any failure (offline, malformed input, etc.).
- [ ] Idempotent: running it twice in a row produces no diff on the second run.

### `.github/workflows/post-merge-housekeeping.yml` — new workflow

- [ ] New file with the workflow per §6.
- [ ] Trigger: `on: pull_request: types: [closed]`, and the job guards with `if: github.event.pull_request.merged == true`.
- [ ] Job runs on `ubuntu-latest` with permissions: `contents: write`, `issues: read`, `pull-requests: read`.
- [ ] Job uses `actions/checkout@v4` with `ref: main` and `fetch-depth: 0`.
- [ ] Sets up Python 3.11 via `actions/setup-python@v5` (matches the project's Python version) so `tools/sync_state.py` can run.
- [ ] Installs `gh` (preinstalled on ubuntu-latest, but verify with `gh --version`).
- [ ] Sets `GH_TOKEN` env var to `${{ secrets.GITHUB_TOKEN }}` for all steps that call `gh`.
- [ ] Step "Find ticket from PR body": uses `gh pr view ${{ github.event.pull_request.number }} --json body` to fetch the body, greps for `Closes #(\d+)`, captures issue number. If no match → fail with a clear error.
- [ ] Step "Find ticket file from issue body": uses `gh issue view <N> --json body`, greps for `` Ticket file: `docs/TICKETS/...` ``, captures the path. If no match → fail with a clear error.
- [ ] Step "Update ticket file": runs `sed -i 's/^\*\*Status:\*\* IN_REVIEW/\*\*Status:\*\* MERGED/' <path>`. Verifies the change by grepping for `Status: MERGED`. Fails if not present after sed.
- [ ] Step "Update PROJECT_STATE.md": runs a Python one-liner (or invokes a helper in `tools/sync_state.py` with a new `--mark-merged TICKET-XXX --pr N` flag — chose this; see below) to move the ticket from "In review 👀" to "Done ✓" and update "Last updated:".
- [ ] **Extends `tools/sync_state.py`** with a `--mark-merged <TICKET-ID> --pr <PR-N>` flag that performs the "In review → Done" move and the "Last updated" bump, then calls the rebuild logic. Used by the workflow. Acceptance criterion: the flag is callable from CI; same behaviour as running the script and editing PROJECT_STATE manually.
- [ ] Step "Update BACKLOG.md": same `sync_state.py --mark-merged` invocation handles BACKLOG.md (updates the row's status column from IN_REVIEW to MERGED).
- [ ] Step "Reconcile Next up": `python3 tools/sync_state.py` (no flags — the standard reconciliation).
- [ ] Step "Commit and push":
  ```bash
  git config user.name "github-actions[bot]"
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
  git add docs/TICKETS/ docs/PROJECT_STATE.md docs/TICKETS/BACKLOG.md
  git commit -m "chore: post-merge housekeeping for TICKET-XXX (#N) [skip ci]"
  git push origin main
  ```
- [ ] **Failure handling:** any step failure marks the workflow run as failed and skips the commit step. Partial updates never reach `main`.
- [ ] Workflow is reviewable in isolation: lint-yamllint-clean, no inline magic. Helper logic lives in `tools/sync_state.py`.

### `AGENTS.md` — Step 2 becomes verification

- [ ] Replace the Step 2 body with the new wording per §7. The new wording explicitly says: "GitHub Actions should have already updated docs. Verify by reading PROJECT_STATE.md; if the ticket is still in 'In review 👀' or BACKLOG row shows `IN_REVIEW`, the workflow failed — run `python3 tools/sync_state.py --mark-merged TICKET-XXX --pr N` and commit with `chore: reconcile state`."
- [ ] At the end of the "When Vivek says 'I merged it'" section, add a one-paragraph note: "GitHub Actions handles housekeeping the moment the PR merges. By the time you start the next session, PROJECT_STATE.md, BACKLOG.md, and the ticket file should already reflect MERGED status. Step 2 verifies this; in the rare case Actions failed, Step 2 reconciles manually."
- [ ] No other section of AGENTS.md is touched. (The "Files NOT to modify" rule applies to AGENTS.md too — don't drift.)

### `docs/WORKFLOW.md` — cross-reference touch-ups

- [ ] In Section 4 ("Filing a ticket"), add one sentence after "Paste the shell block into your terminal and press Enter.": "If you're not on `main` or your working tree is dirty, the script will refuse to run with a clear error — fix and retry."
- [ ] In Section 4, add one bullet to the list of what `draft_ticket.sh` does: "Reconciles the 'Next up' list in both PROJECT_STATE.md and BACKLOG.md against GitHub Issues (no more stale entries)."
- [ ] In Section 5 ("Implementing a ticket"), add one sentence to the "What you do during the session" paragraph: "Housekeeping for the previous ticket happens automatically on merge via GitHub Actions; the agent's Step 2 verifies it landed."
- [ ] Update the Section 8 ("What changed in TICKET-M1 (transitional)") title to be inclusive of M3 changes, OR add a new short Section 9 documenting the M3 self-heal behaviour. Pick one; document the choice in the PR.

### One-off correction: fix BACKLOG.md's Company Deep Dive section

- [ ] As part of this ticket's implementation, fix the malformed section in BACKLOG.md (separator row currently after the data row) so it reads:
  ```
  ## Milestone — Company Deep Dive

  | ID | Title | Status | Priority | Est |
  |---|---|---|---|---|
  | TICKET-025 | Company data layer: ... | QUEUED | HIGH | 1.5 – 2 hr |
  ```
- [ ] This is a one-line edit done in the same commit as the `update_backlog.py` fix. It's a smoke test that the new insertion logic produces the right shape on a fresh section: after the fix, *re-run* `update_backlog.py` mentally (or actually, with a throwaway test ticket) against the corrected section — the result should match the desired shape.

### Tests

- [ ] **`tests/unit/tools/test_next_up.py`** (new): tests for `tools/_next_up.py`:
  - `rebuild_next_up_list` returns the `next-up`-labelled issue first.
  - Issues with `superseded` or `blocked` labels are excluded.
  - Ordering by milestone order in BACKLOG.md works (mock the BACKLOG read).
  - Ordering tiebreaker is issue number ascending.
  - `extract_freeform_entries` returns lines starting and ending with `*`.
  - Helpers raise a clear exception if `gh` is unavailable (mock `subprocess.run` returning non-zero).
- [ ] **`tests/unit/tools/test_sync_state.py`** (new): tests for `tools/sync_state.py`:
  - Idempotent: running twice on the same fixture produces no diff on the second run.
  - `--mark-merged TICKET-XXX --pr N` moves the ticket from "In review" to "Done" with the expected format.
  - "Last updated:" line is rewritten with today's date.
  - BACKLOG.md row status column updates from IN_REVIEW to MERGED for the named ticket.
- [ ] **`tests/unit/tools/test_update_backlog.py`** (new): tests for `tools/update_backlog.py`:
  - Missing milestone section is auto-created with the correct template.
  - New row is inserted immediately before the blank line after the separator, never after a stray separator.
  - Running on an existing section appends to the bottom of that section's table.
- [ ] **`tests/unit/tools/test_draft_ticket.sh`** (new): a small shell-based test using `bats` or just plain bash:
  - Running from a non-main branch fails with exit 1 and the expected error message.
  - Running with a dirty working tree fails with exit 1.
  - Both checks fire before any file is written (verify by ensuring no new files appear in `docs/TICKETS/` after a failed run).
  - **If `bats` is not in the project's dev deps**, fall back to a pytest-based subprocess test that invokes the shell script and asserts on exit code and stderr.
- [ ] All new tests pass: `pytest tests/unit/tools/`.
- [ ] Existing test suite passes unchanged: `pytest`.

### Lints / quality

- [ ] `ruff check .` passes.
- [ ] `mypy app/` passes (no changes to `app/`, but verify untouched).
- [ ] `lint-imports` passes (no architecture violations — `tools/` is outside the layer rules but should not import from `app/`).
- [ ] The new workflow file is valid YAML and passes a syntax check (`actionlint` if available, otherwise `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/post-merge-housekeeping.yml'))"`).

### State updates (per `AGENTS.md` Step 8b)

- [ ] `docs/SESSION_LOG.md` appended with a new entry.
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-M3 → IN_REVIEW).
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-M3 row → IN_REVIEW).
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --base main`, body contains `Closes #<N>`.

### Manual step for Vivek (called out in PR description)

- [ ] **Branch protection exemption:** in GitHub Settings → Branches → main → "Allow specified actors to bypass required pull requests," add `github-actions[bot]`. The workflow cannot grant this exemption itself. The PR description must include this as a checklist item Vivek does before merging the PR (otherwise the first post-merge housekeeping run will fail with a permission error).

---

## Files created

```
.github/workflows/post-merge-housekeeping.yml
tools/_next_up.py
tools/sync_state.py
tests/unit/tools/__init__.py
tests/unit/tools/test_next_up.py
tests/unit/tools/test_sync_state.py
tests/unit/tools/test_update_backlog.py
tests/unit/tools/test_draft_ticket.sh           (or test_draft_ticket.py if no bats)
```

## Files modified

```
tools/draft_ticket.sh                ← branch guard, clean-tree guard, call sync_state at start
tools/update_backlog.py              ← auto-create milestone, fix separator, use _next_up helper
tools/update_state.py                ← use _next_up helper for full rebuild
AGENTS.md                            ← Step 2 becomes verification; add Actions note
docs/WORKFLOW.md                     ← cross-reference touch-ups (Sections 4, 5; new 9 or extend 8)
docs/TICKETS/BACKLOG.md              ← fix malformed Company Deep Dive section; ticket row → IN_REVIEW
docs/PROJECT_STATE.md                ← TICKET-M3 → IN_REVIEW
docs/SESSION_LOG.md                  ← new session entry
```

## Files NOT to modify

- `tools/setup_github.sh` — out of scope per §10. The hardcoded milestone list stays. If a new milestone is needed for a future ticket, the `gh api` one-liner is the workflow.
- `app/**` — zero application code changes. This is purely tooling and docs.
- `tests/unit/domain/`, `tests/unit/services/`, `tests/unit/ui/`, `tests/integration/`, `tests/e2e/` — zero application test changes.
- `pyproject.toml` / `environment.yml` — no new dependencies. `gh` CLI is assumed installed (already used). `bats` is optional; if not available, use pytest+subprocess.
- `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md` — no changes. The methodology document already covers the lifecycle vocabulary; M3 is an implementation of what METHODOLOGY already prescribes, not a redefinition.
- `.github/workflows/ci.yml` — existing CI workflow stays as-is. The new workflow is a separate file.
- `docs/TICKETS/TICKET-025-*.md` — TICKET-025's content is locked. The malformed BACKLOG.md row referring to it gets fixed, but the ticket file itself is not touched.

---

## Out of scope

- **A general-purpose `tools/lint_docs.py`** that scans for state drift (e.g. tickets in BACKLOG without GitHub issues, tickets with GitHub issues but no file, label/status mismatches). Useful but bigger than M3. File as a separate ticket if/when state drift incidents happen again post-M3.
- **Auto-deriving the milestone list in `setup_github.sh` from BACKLOG.md.** Hardcoded for now; revisit if it becomes annoying.
- **A scheduled GitHub Actions job** running `tools/sync_state.py` daily as a drift catch. Out of scope; the merge-time workflow + on-draft-time self-heal cover the realistic cases.
- **Slack / email notifications** when the post-merge workflow fails. Out of scope; Vivek will see the red check on the Actions tab the next time he visits GitHub. If this becomes a problem, add a notification step in a follow-up ticket.
- **Migrating PROJECT_STATE.md to a structured format (YAML / TOML)** so reconciliation doesn't have to do regex surgery. The current markdown format is human-readable and has worked OK; reconsider if regex bugs multiply.
- **Reconciling the "Done ✓" section automatically.** Today it's append-only and built manually by the post-merge workflow inserting one line per merged ticket. Cleaning up the section (e.g. trimming to last 5 — which the file already does manually) is out of scope; the workflow inserts; trimming is a manual edit when it gets long.
- **Changing how the agent picks the next ticket in Step 0.** That logic (`gh issue list --label next-up --state open`) is already correct; M3 makes the `next-up` label more reliably set.
- **Backfilling MERGED status on historical tickets that were merged before this workflow existed.** Those tickets' files have whatever status they were last set to; they're not re-touched. The workflow only fires for *future* merges.
- **Adding a `--dry-run` flag to `tools/sync_state.py`.** Nice-to-have but not necessary; the script doesn't commit, so its current behaviour is effectively a dry-run already.

---

## Test cases (manual review checklist for the PR)

Most of the value here is observable behaviour, not unit tests. Run through these manually after the PR is up:

- [ ] **Branch guard fires:** `git checkout -b throwaway && bash tools/draft_ticket.sh <<< "ID: TICKET-999..."` — exits 1 with the expected message. No files created.
- [ ] **Clean-tree guard fires:** on main, `touch newfile.txt`, then run draft_ticket — exits 1 with "working tree is dirty". `rm newfile.txt` and retry — succeeds.
- [ ] **Auto-create milestone:** in a throwaway branch, delete the Company Deep Dive section from BACKLOG.md, then run `python3 tools/update_backlog.py --id TICKET-999 --title "test" --milestone "Company Deep Dive" --priority HIGH --estimate "1 hr"` — section auto-created with the expected template.
- [ ] **Separator placement:** after the auto-create, inspect BACKLOG.md — header row, separator row, then data row, then blank line. Not the malformed shape.
- [ ] **Next up reconciliation:** run `python3 tools/sync_state.py` on the current repo — observe that the doubled `1.` entries in PROJECT_STATE.md and BACKLOG.md are flattened to a clean numbered list with TICKET-025 first.
- [ ] **Sync is idempotent:** run `python3 tools/sync_state.py` twice in a row — `git diff` is empty after the second run.
- [ ] **End-to-end with TICKET-025 stand-in:** open the TICKET-025 PR (when implementing C2 onward), merge it — observe within 1 minute that:
  - The Actions tab shows the post-merge workflow ran and succeeded.
  - PROJECT_STATE.md "Done ✓" now contains `TICKET-025 — ... (PR #N)`.
  - PROJECT_STATE.md "In review 👀" no longer contains TICKET-025.
  - BACKLOG.md TICKET-025 row shows `MERGED`.
  - `docs/TICKETS/TICKET-025-*.md` file shows `Status: MERGED`.
  - The "Last updated:" line in PROJECT_STATE.md shows today's date.
- [ ] **End-to-end with Actions failure:** induce a failure by, e.g., merging a PR whose body lacks `Closes #N`. The workflow fails loudly; no commit on main; running `tools/sync_state.py --mark-merged TICKET-NNN --pr X` manually cleans up.
- [ ] **AGENTS.md / WORKFLOW.md read coherently:** re-read both files end-to-end. The new wording (Step 2 verification, Section 9 self-heal note) should fit naturally without contradicting earlier sections.

---

## Notes (architectural and methodological — for future AI sessions)

### Why GitHub Actions is the right place for housekeeping

Three traits make this work:

1. **The trigger is unambiguous.** A PR merging to `main` is a single GitHub event. No human signal to interpret ("merged" vs "approved" vs "ready"), no race conditions, no "I told the agent merged but I actually didn't yet."
2. **The actor is deterministic.** `github-actions[bot]` is a single identity with constrained permissions. Easier to audit and reason about than "the agent in some session at some time."
3. **The latency is near-zero.** Today's housekeeping lag is "until the next implementation session" — could be days. With Actions, it's seconds. Drafting 3 tickets in a row sees fresh state on each.

The cost: a branch-protection exemption for the bot. That's a small, well-understood concession in exchange for eliminating an entire class of state-drift bugs.

### Why the agent's Step 2 stays as a verification step

If we removed Step 2 entirely (full trust in Actions), then any Actions failure leaves `main` in a broken state forever. Step 2 is the safety net: every time the agent starts a session, it verifies the previous ticket's housekeeping landed. If Actions failed for any reason — workflow syntax bug we shipped, GitHub outage, token expired, network blip — the agent catches it and reconciles.

The cost of keeping Step 2: ~5 seconds per session for a `gh issue view` call and a file read. Cheap insurance.

### Why the rebuild is "full rebuild from GitHub," not "prepend + dedup"

Tried both in my head. "Prepend + dedup" requires knowing which entries to drop, which requires knowing which issues are no longer QUEUED, which requires querying GitHub anyway. Once you're querying GitHub, the simpler model is "ask GitHub what's QUEUED, write that list down." No drift possible; no rules about which entries supersede which.

The downside: the order of GitHub-derived entries is fixed by the helper's sort rules. If Vivek wants a custom order ("I'd like TICKET-029 before TICKET-027 even though 027 is older"), he can't get it just by editing PROJECT_STATE.md — he has to use the `next-up` label on GitHub or change the milestone order in BACKLOG.md. This is fine. The cases where Vivek wants a custom order are rare; for those, he uses the `next-up` label to put the chosen ticket first.

### Why `extract_freeform_entries` is a separate helper

The `*Panel framework brainstorm session*` entry is a non-ticket placeholder — it's a reminder to Vivek that a design session is pending. It doesn't correspond to a GitHub issue. The clean fix would be "file an issue for it"; the lazy fix is "preserve free-form italic entries verbatim." The lazy fix wins because it's two functions and avoids a new convention (issues for non-ticket things).

Future tickets may introduce more such entries; the helper accommodates them.

### Why the `[skip ci]` suffix on the housekeeping commit

The housekeeping commit only touches docs (markdown files, ticket files). Running the full CI suite on every merge to verify a doc edit is wasteful. The `[skip ci]` suffix on the commit message tells GitHub Actions to skip workflow runs triggered by that commit. The post-merge-housekeeping workflow itself only runs on PR merges (not on push), so it's not at risk of recursing.

### What happens if a future ticket changes `PROJECT_STATE.md`'s structure

The regex-based reconciliation in `tools/sync_state.py` is fragile against structural changes. If someone later renames "In review 👀" to "In review" or moves the "Last updated:" line, the script breaks.

Mitigation: the `--mark-merged` code paths fail loudly with a clear error. Any future ticket touching PROJECT_STATE.md structure must update the regexes in `tools/sync_state.py` in the same PR. Add a comment to PROJECT_STATE.md at the top:

```markdown
<!-- The section headers below are matched by tools/sync_state.py regexes.
     If you rename or reorder them, update sync_state.py in the same PR. -->
```

This is the M3 ticket's responsibility to add. Single line, easy to miss otherwise.
