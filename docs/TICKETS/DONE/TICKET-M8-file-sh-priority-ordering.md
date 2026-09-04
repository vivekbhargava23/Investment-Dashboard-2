# TICKET-M8 — Add priority-band ordering to `tools/file.sh`

**Status:** QUEUED
**Priority:** MEDIUM
**Estimated session length:** 1 hr
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Milestone:** Workflow

---

## Problem

Per ADR-010: `tools/file.sh` currently appends new tickets at the bottom of the Backlog column in filing order, regardless of priority. The implementation agent's `next` menu therefore surfaces low-priority tickets above high-priority ones if the low-priority was filed earlier. Vivek has to drag-reorder before the menu is useful.

## Solution

Add a new step to `tools/file.sh` after Step 6 (Add to Backlog) that sets each new item's position via the GitHub Projects v2 GraphQL API. The ordering rule is "banded-prepend" per ADR-010: each new ticket lands at the top of its priority band.

### Step 7 (new) — Priority-band ordering

For each new ticket, in filing order:

1. Query current Backlog items and their priority labels:
   ```bash
   gh api graphql -f query='
     query($projectId: ID!) {
       node(id: $projectId) {
         ... on ProjectV2 {
           items(first: 100) {
             nodes {
               id
               fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
               content {
                 ... on Issue {
                   labels(first: 10) { nodes { name } }
                 }
               }
             }
           }
         }
       }
     }' -f projectId="$PROJECT_ID"
   ```
   Filter via `jq` to keep only items with `Status == "Backlog"`, preserving the API's natural order (which reflects current position).

2. For the new ticket's priority (CRITICAL=4, HIGH=3, MEDIUM=2, LOW=1), find the **last** existing Backlog item whose priority rank is strictly higher. Call its id `ANCHOR_ID`.

3. If `ANCHOR_ID` is empty (no strictly-higher item exists), move the new item to the **top** of Backlog by calling the position mutation with no `afterId`:
   ```bash
   gh api graphql -f query='
     mutation($projectId: ID!, $itemId: ID!) {
       updateProjectV2ItemPosition(input: { projectId: $projectId, itemId: $itemId }) {
         items(first: 1) { nodes { id } }
       }
     }' -f projectId="$PROJECT_ID" -f itemId="$NEW_ITEM_ID"
   ```

4. Otherwise, place the new item directly after `ANCHOR_ID`:
   ```bash
   gh api graphql -f query='
     mutation($projectId: ID!, $itemId: ID!, $afterId: ID!) {
       updateProjectV2ItemPosition(input: { projectId: $projectId, itemId: $itemId, afterId: $afterId }) {
         items(first: 1) { nodes { id } }
       }
     }' -f projectId="$PROJECT_ID" -f itemId="$NEW_ITEM_ID" -f afterId="$ANCHOR_ID"
   ```

5. Wrap each mutation in a non-fatal block: on failure, log a warning ("Could not reorder $ticket_id — fix manually by dragging on the board.") and continue.

The query is re-run before each new item's placement so the algorithm sees the post-state of any previous insertions in the same batch.

### Step 8 — Summary line

Update the "Filed N ticket(s)" summary to include each ticket's final Backlog position rank (1-indexed) and band. Example:
```
TICKET-H1  — Move classification to ISIN map -> issue #99, Backlog #1 (CRITICAL)
TICKET-C1  — Add ECB FX adapter            -> issue #100, Backlog #2 (HIGH)
TICKET-C5  — Split analytics.py             -> issue #102, Backlog #7 (LOW)
```

This makes the result visible without opening the browser.

### Doc updates

`METHODOLOGY.md` — anti-pattern list:

- Replace: *"Editing the project board order programmatically. Vivek drags cards; the agent only writes the Status column."*
- With: *"The implementation agent editing project board order programmatically. Only `tools/file.sh` may set position within Backlog (by priority band — see ADR-010). The agent only writes the Status column."*

And the script-mutation rule:

- Replace: *"Writing scripts that mutate the project board outside `tools/file.sh` and the agent's Step 5/8c/Step 0 drop handler. Board state is touched by these three places only."*
- With: *"Writing scripts that mutate the project board outside `tools/file.sh` (Status + Backlog position by priority band per ADR-010) and the agent's Step 5/8c/Step 0 drop handler (Status only). Board state is touched by these three places only."*

`AGENTS.md` — under "What you do NOT do", add one line:

> ❌ Reorder cards on the project board. Only `tools/file.sh` sets Backlog position (by priority band — ADR-010). The agent only writes Status.

### Flip ADR-010 to Accepted

When the PR opens, update `docs/DECISIONS/ADR-010-file-sh-priority-ordering.md` Status from `Proposed` to `Accepted` with today's date. One-line change.

## Acceptance criteria

- [ ] `tools/file.sh` includes Step 7 (priority-band reorder) with banded-prepend semantics.
- [ ] Filing a batch of mixed-priority tickets results in CRITICAL items at the top of Backlog, then HIGH, then MEDIUM, then LOW. Within a band, items appear in the reverse of filing order (last filed at top of its band).
- [ ] Filing a single ticket whose priority is lower than all existing Backlog items places it at the bottom of its priority band (above all strictly-lower items).
- [ ] Filing a single ticket whose priority is higher than all existing Backlog items places it at the top of Backlog.
- [ ] GraphQL mutation failure for any single item logs a warning but does not fail the whole filing run.
- [ ] Summary block shows each ticket's final Backlog rank and priority band.
- [ ] `METHODOLOGY.md` updates the two relevant anti-pattern lines.
- [ ] `AGENTS.md` gets the one-line cross-reference.
- [ ] ADR-010 Status flips to `Accepted` in the same PR.
- [ ] All tests pass; ruff / mypy / lint-imports clean. (`tools/file.sh` itself is bash; shellcheck-clean is a stretch goal but not required.)

### Manual smoke

These tests exist as scripted scenarios; run each by hand on a throwaway branch with the project board open:

1. **Mixed batch.** Draft three tickets locally: one CRITICAL, one HIGH, one MEDIUM. Run `bash tools/file.sh`. Confirm Backlog order top-down is `CRITICAL, HIGH, MEDIUM` and that any existing Backlog items appear below them within their bands.
2. **Single LOW.** With existing Backlog containing one HIGH and one MEDIUM, file a single LOW ticket. Confirm new LOW lands at position 3 (below MEDIUM).
3. **Single CRITICAL hotfix.** With existing Backlog of all MEDIUM/LOW, file one CRITICAL. Confirm it lands at position 1.
4. **Banded preservation.** With existing Backlog of three HIGH items in hand-ordered sequence A, B, C (top-down), file one new HIGH ticket N. Confirm new order is `N, A, B, C` — N at top of HIGH band, A/B/C preserved relative order.
5. **GraphQL failure injection.** Temporarily break the project ID (e.g. `PROJECT_NUMBER=99999` in the script) and run. Confirm tickets are still filed and a warning prints. Restore and re-run a real filing.

## Out of scope

- Reordering items already in Backlog (i.e. running a re-sort against existing items). This script only positions newly-filed items.
- Moving items between columns by anything other than the existing drop / step-5 / step-8c handlers.
- Adding a tools-side `reorder.sh` for ad-hoc reorder passes. If a need emerges, separate ticket.
- Ordering within `Ready`. That stays Vivek-only.

## Notes / assumptions

- Assumes `gh api graphql` is available (it is — already used elsewhere in the script's environment).
- Assumes Vivek's GitHub token has the `project` scope (it does — required by current `gh project item-edit` calls).
- Assumes `updateProjectV2ItemPosition` is the correct mutation name in the live GitHub Projects v2 API. Verify with `gh api graphql -f query='{ __schema { mutationType { fields { name } } } }'` if uncertain.
- Assumes the Backlog rarely exceeds 100 items (the GraphQL query fetches `first: 100`). If it does, paginate via `after:` cursor. Current Backlog is under 30 items; defer pagination until needed.
- Assumes the priority label on each issue matches the ticket's `**Priority:**` field. The script's Step 5 sets the label from the field, so they stay in sync. If they drift, the source of truth for ordering is the issue label (the GraphQL query reads from the issue, not the file).
- The reorder step runs after Step 7 (commit + push), so a failed reorder does not block the commit. Alternatively, place it before commit so a partial state isn't pushed — recommended ordering is reorder-then-commit-then-push because the position is project-side, not file-side, and there's no file to commit either way.
