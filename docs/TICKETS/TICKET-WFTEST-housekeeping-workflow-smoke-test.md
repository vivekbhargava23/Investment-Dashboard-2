# TICKET-WFTEST — Housekeeping workflow smoke test

**Status:** MERGED
**Priority:** LOW
**Estimated session length:** 5 min
**Drafted by:** Claude Code (2026-05-13) — test-only ticket, delete after workflow verified

> This ticket exists solely to verify that the post-merge-housekeeping GitHub Actions
> workflow runs end-to-end after the PYTHONPATH fix in TICKET-M3.
> Once the workflow runs successfully on the PR that closes this ticket, the ticket
> can be deleted from the repo in a follow-up cleanup commit.

---

## What to check after merging the PR that closes this issue

1. The Actions tab shows `post-merge-housekeeping` completed (green) within ~30 s of merge.
2. `docs/TICKETS/TICKET-WFTEST-*.md` shows `**Status:** MERGED`.
3. `docs/PROJECT_STATE.md` "Done ✓" contains `TICKET-WFTEST — ... (PR #N)`.
4. `docs/PROJECT_STATE.md` "In review 👀" no longer contains TICKET-WFTEST.
5. `docs/TICKETS/BACKLOG.md` WFTEST row shows `MERGED`.
6. The housekeeping commit message starts with `chore: post-merge housekeeping for TICKET-WFTEST`.

If all six pass, the workflow is working correctly.
