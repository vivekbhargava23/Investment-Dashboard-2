# tools/

Helper scripts for the Investment Dashboard project workflow.
See `docs/METHODOLOGY.md` for why these scripts exist.

---

## Scripts

### `gate.sh`

Activates the `investment-dashboard` conda environment and runs the full local
gate: `pytest`, `ruff check .`, `mypy app/`, and `lint-imports`. It exits on the
first failure and names the failed check.

**Usage:**

```bash
bash tools/gate.sh
```

### `next.sh`

Prints the ranked Ready/Backlog ticket menu from the GitHub Projects board, split
into **Startable now** and **Blocked** sections. Each row carries priority,
recommended model, dependency blockers, and the transitive unblock score — how many
open tickets are still waiting behind this one, following the chain all the way down
rather than counting only immediate dependents.

Ranking keys, in order: startable before blocked, `Ready` before `Backlog`, priority,
unblock score, board position. Blocked tickets are shown for context, not hidden, but
they never outrank a startable one. See "How ticket order is decided" in
`docs/METHODOLOGY.md`; the ordering is only as good as the `**Depends on:**` lines in
`docs/TICKETS/`.

**Usage:**

```bash
bash tools/next.sh
```

### `reorder.sh`

Moves the `Ready`/`Backlog` cards on the project board into the same order `next.sh`
ranks, so the board and the menu never disagree. Cards in `In progress`, `In review`
and `Done` are left alone. Each card is pinned directly after the one placed above it,
so a partial failure leaves a correctly ordered prefix rather than a shuffled board.

`tools/file.sh` calls this after filing new tickets: its own priority-band placement
cannot see the `**Depends on:**` graph, so a blocked CRITICAL would otherwise land on
top of the stack.

**Usage:**

```bash
bash tools/reorder.sh            # move the cards
bash tools/reorder.sh --dry-run  # print the target order, move nothing
```

### `start_ticket.sh`

Starts a ticket: reconciles closed `In review` board items to `Done`, gets onto an
up-to-date `main`, creates or reuses the feature branch, marks the ticket file
`IN_PROGRESS`, and moves the board item to `In progress`.

It does not require you to already be on `main`. The session ritual deliberately ends on
the feature branch, so the next session starts there. Branch handling:

| Current branch | Behaviour |
|---|---|
| `main` | Pull `--ff-only`, create the ticket branch. |
| The requested ticket's own branch | Reuse it. No GitHub call, so a rerun is cheap. |
| Another ticket's branch, clean tree, PR merged | Check out `main`, fast-forward, branch. |
| Another ticket's branch, PR open / closed-unmerged / absent | Refuse, change nothing. |
| Any branch with a dirty tree | Refuse before any GitHub call, list the dirty files. |

If GitHub cannot be reached to determine the PR state, it refuses rather than assuming
the branch is disposable.

**Rate limits.** If the board move to `In progress` fails because GitHub is rate limiting,
the branch still exists and the command reports itself as resumable: rerun the same
command once the limit resets and it reuses the branch and redoes only the board move.
The `In review` → `Done` reconcile is treated as housekeeping and is skipped with a
warning rather than aborting the start.

**Usage:**

```bash
bash tools/start_ticket.sh TICKET-M9
```

### `finish_ticket.sh`

Finishes a ticket after the implementation and session-log commits exist. It
reruns `gate.sh`, pushes the current branch, moves the board item to `In review`,
and opens the PR with a `Closes #N` footer.

**Usage:**

```bash
bash tools/finish_ticket.sh TICKET-M9
```

### `archive.sh`

Moves ticket specs the board marks `Done` out of `docs/TICKETS/` and into
`docs/TICKETS/DONE/`, so the working folder only holds live work. Files move with
`git mv`; the commit is left to you.

**This cannot hide a ticket.** Every ticket lookup in `ticket_workflow.py` globs
`docs/TICKETS` recursively via `ticket_file_candidates`, so a ticket resolves by ID from
any depth. New tickets are always filed at the top level by `file.sh`; archiving is the
only thing that moves them, and only after the board says `Done`. Board status stays the
single source of truth — the archive directory is presentation, never state.

**Usage:**

```bash
bash tools/archive.sh --dry-run  # list the moves, touch nothing
bash tools/archive.sh            # git mv them into docs/TICKETS/DONE/
```

### `doctor.sh`

Non-mutating diagnostics for local workflow state: dirty tree, current branch, whether
the current branch's PR is merged (i.e. whether `start_ticket.sh` can hand off from it),
Done tickets awaiting archive, retired workflow files, board sanity, and dependency
blockers.

**Usage:**

```bash
bash tools/doctor.sh
```

### `ticket_workflow.py`

Shared implementation behind `next.sh`, `start_ticket.sh`, `finish_ticket.sh`,
`archive.sh`, `reorder.sh`, and `doctor.sh`. Keep CLI behavior behind the shell entry points; import pure
helpers in tests when dependency parsing or ranking changes.

### `file.sh`

Files one or more untracked `docs/TICKETS/TICKET-*.md` drafts as GitHub issues
and adds them to the project board (Backlog). Related ADR/design files must be
passed explicitly so the committed planning bundle is complete:

**Usage:**

```bash
bash tools/file.sh
bash tools/file.sh \
  docs/DECISIONS/ADR-014-example.md \
  docs/DESIGN/example-design.md
```

The command is safe to resume after a partial GitHub failure: an existing open
issue with the exact ticket ID is updated and reused, and an existing project
card keeps its status and position. Multiple open issues for one ticket ID, or
a ticket ID already held by a closed issue, abort before side effects.

The working tree may contain only the new ticket files and explicitly listed
ADR/design files. Runtime-data changes must be committed or stashed separately.
The script stages only that explicit bundle; `git push` never includes other
modified or untracked files.

### `setup_github.sh`

Idempotent setup of GitHub labels and milestones. Run once per fresh repo clone.

**Usage:**

```bash
bash tools/setup_github.sh
```

### `backfill_isin_from_csv.py`

Idempotently backfills the `isin` field onto `scalable_csv` transactions
whose `isin` is `null`, using each transaction's `csv_reference` to look
up the ISIN from the original Scalable Capital CSV export.

**When to use:** only when CSV-imported transactions have `isin: null` and
you have the original CSV on hand. This arises from the CSV-11 migration bug
where `isin_map.json` was absent at the time `migrate_v2_to_v3` ran.
The portfolio must already be at schema v3.

**Usage (always dry-run first):**

```bash
# Preview what would change — safe, writes nothing
python3 tools/backfill_isin_from_csv.py \
    --portfolio data/portfolio.json \
    --csv path/to/ScalableCapital-Broker-Transactions.csv

# Write changes (creates a timestamped backup first)
python3 tools/backfill_isin_from_csv.py \
    --portfolio data/portfolio.json \
    --csv path/to/ScalableCapital-Broker-Transactions.csv \
    --apply
```

**Backups:** written alongside `portfolio.json` as
`portfolio.json.backfill.bak.<YYYYMMDD-HHMMSS>`. Multiple runs accumulate
backups; prune by hand when no longer needed.

**Safety guarantees:** never overwrites a transaction whose `isin` is already
set; skips manual/switch transactions; refuses to run on non-v3 portfolios.

---

## Toolchain requirements

### `file.sh` and `setup_github.sh`

These scripts are written to be **POSIX-portable** (bash 3.2+, BSD grep, POSIX sed).
No GNU-only constructs (`mapfile`, `grep -P`, `${var,,}`, `declare -A`, etc.) are used.

| Tool | Minimum version | Notes |
|---|---|---|
| `bash` | 3.2+ | Stock macOS bash 3.2.57 is sufficient |
| `grep` | any | BSD grep (macOS default) is sufficient; no `-P` flag used |
| `sed` | POSIX | BSD sed (macOS default) is sufficient |
| `git` | any recent | Must be authenticated to the repo |
| `gh` | any recent | Must be authenticated (`gh auth login`) |
| `jq` | 1.6+ | `brew install jq` if missing |
| `python3` | 3.11+ | Used by `ticket_workflow.py`; the project conda env satisfies this |

### macOS invocation

```bash
bash tools/file.sh
```

No `brew install bash` or GNU grep required. The scripts run on stock macOS.

### Linux invocation

```bash
bash tools/file.sh
```

Identical — no distro-specific packages needed beyond `git`, `gh`, and `jq`.

---

## Forbidden constructs (future contributors)

To keep scripts portable, do **not** introduce:

- `mapfile` / `readarray` — bash 4+ only. Use `while IFS= read -r` loop instead.
- `grep -P` / `grep -oP` — GNU-only. Use `sed -nE` with capture groups instead.
- `${var,,}` / `${var^^}` — bash 4+ case conversion. Use `tr '[:upper:]' '[:lower:]'` instead.
- `declare -A` — associative arrays are bash 4+. Use parallel indexed arrays instead.
- `sed -i 's/foo/bar/' file` — GNU form. BSD requires `sed -i '' 's/foo/bar/' file`.
  Use a temp file (`sed 's/foo/bar/' file > file.tmp && mv file.tmp file`) for portability.
- `date -d <string>` — GNU-only. BSD form is `date -j -f '%Y-%m-%d' "$str" +%s`.

These restrictions are enforced by `shellcheck` in CI (`.github/workflows/ci.yml`).
