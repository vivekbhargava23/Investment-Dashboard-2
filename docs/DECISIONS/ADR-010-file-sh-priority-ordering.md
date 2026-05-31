# ADR-010 — `tools/file.sh` orders new Backlog items by priority band

**Status:** Accepted
**Date:** 2026-05-31
**Drafted by:** Vivek + Claude (Cowork session 2026-05-31)
**Supersedes / amends:** METHODOLOGY.md "Anti-patterns" list (one entry); AGENTS.md (one cross-reference)

---

## Context

Today the `next` menu in the implementation agent shows `Ready` items first (Vivek-vetted), then `Backlog` items in their current board order. Position within Backlog is set by `gh project item-add`, which appends each new ticket at the end of the column. With ten tickets filed in a single batch, the order is "filing order" — independent of priority. A CRITICAL filed last appears below a LOW filed first. Vivek must drag-reorder before the `next` menu surfaces the right work.

Two rules in `METHODOLOGY.md` block any script from touching the board's order:

> ❌ *"Editing the project board order programmatically. Vivek drags cards; the agent only writes the Status column."*
> ❌ *"Writing scripts that mutate the project board outside `tools/file.sh` and the agent's Step 5/8c/Step 0 drop handler. Board state is touched by these three places only."*

The second rule already carves out `file.sh` as a board-touching place. We are now expanding what `file.sh` may touch — from "Status column only" to "Status column + position within Backlog".

## Decision

**`tools/file.sh` sets each new ticket's position in Backlog by priority band, using banded-prepend.** No other surface gains board-reorder powers.

### The rule (precise)

After validating ticket files, creating GitHub issues, adding items to the project, and setting Status=Backlog:

For each new ticket, in filing order:

1. Read the ticket's `**Priority:**` (already validated by Step 4 of `file.sh`).
2. Query the current Backlog items + their priority labels, top-first.
3. Find the **last** existing Backlog item whose priority is **strictly higher** than the new ticket's priority. Call that item `anchor`.
4. Call `updateProjectV2ItemPosition` with `afterId = anchor.id` (or omit `afterId` to move the new item to the top of Backlog when no strictly-higher item exists).

Net effect: each new ticket lands at the **top of its priority band**, above all existing items of equal or lower priority, below all existing items of strictly higher priority. Within the new batch, items are processed in filing order, so the *last* CRITICAL filed ends up at the very top of the CRITICAL band.

Priority order: `CRITICAL > HIGH > MEDIUM > LOW`.

### What does NOT change

- `Ready` column is never touched. Vivek's vetted + ordered list stays exactly as he set it.
- The implementation agent (`AGENTS.md` Steps 5, 8c, Step 0 drop handler) does not gain reorder powers — those steps still only write Status.
- Vivek's drag-overrides win. The script runs only on filing; nothing re-asserts after.
- Ticket validation, issue creation, label/milestone application — all unchanged.

### Methodology document updates

`METHODOLOGY.md`'s anti-pattern list changes one entry from:

> ❌ Editing the project board order programmatically. Vivek drags cards; the agent only writes the Status column.

to:

> ❌ The implementation agent editing project board order programmatically. Only `tools/file.sh` may set position within Backlog (by priority band — see ADR-010). The agent only writes the Status column.

And the second board-mutation rule's parenthetical updates to clarify that `file.sh` writes both Status and Backlog position.

`AGENTS.md` gets a one-line cross-reference under "What you do NOT do".

## Reasoning

1. **The `next` menu becomes useful by default.** Today Vivek often has to drag immediately after `file.sh` runs. Banded-prepend means the menu's first item is the most-recently-filed CRITICAL, second is the next most recent CRITICAL or first HIGH, and so on. No drag needed in the common case.
2. **Vivek's manual ordering is preserved across priority bands.** Hand-ordered HIGH items keep their relative order — new HIGH items go ABOVE them (newest most important), but existing HIGH items don't shuffle among themselves.
3. **The carve-out is small and bounded.** Only `file.sh`, only Backlog, only on filing. The implementation agent and the drop handler still don't reorder.
4. **Reversible cheaply.** Drag-overrides always win; if the priority sort is wrong for a given case, one drag fixes it.
5. **Methodology rules are ours to amend.** The original rule reflects a 2026-05 stance ("agents should not reorder"); the carve-out reflects what we learned filing 10+ tickets at once.

## Consequences

- **Pro:** Implementation agent's `next` menu surfaces the most important work first, without Vivek dragging.
- **Pro:** Filing a CRITICAL hotfix surfaces it at the top of Backlog instantly.
- **Pro:** Banded ordering preserves Vivek's hand-ordering within a priority band.
- **Pro:** Reversal is one revert commit + restore the methodology line.
- **Con:** A ticket filed with the wrong `**Priority:**` field ends up in the wrong band. Mitigation: the priority is also the GitHub label, which is visible in the menu and easy to spot.
- **Con:** Existing Backlog items below new arrivals shift down within their band by N positions per batch. Vivek can drag to override if a specific existing item should stay at top.
- **Con:** Adds two GraphQL calls per new ticket (one query, one mutation). For a 10-ticket batch that's 20 extra API calls; well within `gh` rate limits.
- **Con:** The script now does more work; failure modes increase. Mitigation: the reorder step is non-fatal — a failed mutation logs a warning, the ticket is still filed, drag fixes order manually.

## Edge cases handled in implementation

1. **Backlog empty.** `afterId = null` for every new item; they go to the top in priority order, last-filed at position 1 within its band.
2. **GraphQL mutation fails for one item.** Log a warning, continue. Item is filed but at the wrong position; drag to fix.
3. **GraphQL mutation fails for all items.** Tickets and board items are already created; `file.sh` exits 0 with a warning summary. No data lost.
4. **Existing CRITICAL in Backlog at top.** New CRITICAL is processed in filing order; each insertion goes "above the last strictly-higher item, below the last equal-or-higher item". If no strictly-higher item exists, new item goes to position 1 (above existing CRITICALs of the same band — banded-prepend semantic).
5. **Vivek hand-drags after filing.** No script re-asserts. Drag wins.
6. **`drop N` flow.** Unaffected. Drop touches Status only; ADR-010 covers position only on filing.
7. **Custom board views.** The mutation writes the project-level position. Views with custom sort overrides are not touched.
8. **Race with another filing run.** The query-then-mutate pattern is not atomic. For a single-user setup this is acceptable; concurrent runs are not a scenario.
9. **Ticket with no `**Priority:**`.** Already aborts validation in `file.sh` Step 4. Position step is never reached for invalid tickets.
10. **Bash 3.2 / BSD grep compatibility.** The new logic uses `sed -nE`, `jq`, `gh api graphql` — all already in use. No new toolchain dependencies.

## Reversal cost

Revert the `file.sh` patch + restore the methodology line + restore the AGENTS.md cross-reference. ~10 minutes. Low.

## Alternatives considered

- **Banded-append** (new item at BOTTOM of its band). Rejected — preserves Vivek's hand-ordering completely but slows the "see the new CRITICAL first" win.
- **Full re-sort of Backlog every run.** Rejected — overrides any non-priority manual ordering Vivek did within a band.
- **A separate script `tools/reorder.sh` for manual ordering passes.** Rejected for now — banded-prepend at filing time covers the 95% case. Add later if a real need emerges.
- **Promote CRITICAL items directly into `Ready`.** Rejected — `Ready` is Vivek's vetted list; auto-promotion would let unvetted tickets enter the implementation queue.

## Implementation ticket

TICKET-M8.
