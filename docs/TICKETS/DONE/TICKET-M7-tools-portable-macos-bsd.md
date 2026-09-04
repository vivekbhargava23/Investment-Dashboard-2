# TICKET-M7 — Make tools/ scripts portable to macOS/BSD userland

**Status:** IN_PROGRESS
**Priority:** HIGH
**Estimated session length:** 1–1.5 hr
**Drafted by:** Vivek + Claude Chat (2026-05-14)
**Milestone:** Tooling / Workflow

---

## Problem

`tools/file.sh` (and any future `tools/*.sh`) is written assuming GNU/Linux userland and bash 4+. On macOS — Vivek's actual dev machine — stock `/bin/bash` is 3.2.57 (frozen 2007 for GPLv3 reasons) and core utilities are BSD variants. This caused two hard failures while filing TICKET-M6:

1. **`mapfile` not found** — `tools/file.sh:48` uses `mapfile -t NEW_FILES < <(...)`. `mapfile` (and its alias `readarray`) is bash 4+. macOS stock bash 3.2 doesn't have it. Error: `tools/file.sh: line 48: mapfile: command not found`. Workaround used: `/opt/homebrew/bin/bash tools/file.sh` (Homebrew bash 5+).

2. **`grep -P` invalid option** — `tools/file.sh` uses `grep -oP` in multiple places (lines extracting ticket ID, priority, milestone, issue number from output). `-P` is Perl-compatible regex, GNU-only. BSD grep errors with `grep: invalid option -- P`. Workaround used: `PATH="/opt/homebrew/opt/grep/libexec/gnubin:$PATH" /opt/homebrew/bin/bash tools/file.sh` (installs GNU grep via `brew install grep`, prepends to PATH).

Both workarounds work but are non-discoverable. A fresh agent or contributor on macOS hits these head-on with no breadcrumb. The script either needs to be portable (preferred — works everywhere out of the box) or it needs to **explicitly require** GNU userland with a clean error message at the top of the file. Limping along with implicit workarounds is the worst of both worlds.

Additionally, a defensive sweep is needed for **other latent bash 4+ / GNU-only constructs** in `tools/file.sh` that haven't fired yet but will if the script is extended. The full list (per HANDOFF doc):

- `sed -i ''` (BSD requires empty arg) vs `sed -i` (GNU)
- `date -d <string>` (GNU) vs `date -j -f <format>` (BSD)
- `readarray` (bash 4+, same as `mapfile`)
- `${var,,}` / `${var^^}` case-conversion (bash 4+) — **already used at `tools/file.sh:147` as `${VALID_PRIORITIES[$i],,}`**
- `declare -A` associative arrays (bash 4+)
- `<()` process substitution (works in bash 3.2, but worth flagging)
- `${var@Q}` quoted expansion (bash 4.4+)

---

## Acceptance criteria

### A. Decide on the portability strategy (do this FIRST, before any code)

Read the entire current `tools/file.sh` and `tools/regen_context.py` (if it shells out). Then **pick exactly one** of these two strategies for `tools/*.sh` and apply it consistently:

**Strategy 1 — Make scripts portable.** Rewrite GNU-isms to POSIX or bash 3.2-compatible forms. No `mapfile`, no `grep -P`, no `${var,,}`. Script runs unchanged on stock macOS bash 3.2 + BSD grep.

**Strategy 2 — Require GNU userland with a hard preamble.** Keep GNU-isms. Add a shebang/preamble that:
  - Detects `bash --version` < 4 → prints actionable error (`brew install bash` + invocation hint) → exits non-zero.
  - Detects BSD grep (no `-P` support) → prints actionable error (`brew install grep` + PATH hint) → exits non-zero.
  - Lists the required tools at the top of the script as a comment block.

The ticket file does NOT pick the strategy. The implementing agent reads the script, weighs effort/clarity, and picks one. **Document the choice in the PR description** with one paragraph of reasoning.

**Recommendation (not binding):** Strategy 1 is preferred if the GNU-isms are <10 occurrences and have clean POSIX equivalents. Strategy 2 is preferred if there are many usages or rewriting would obscure intent.

### B. Implement the chosen strategy

- [ ] **If Strategy 1:** every `mapfile`, `grep -P`, `${var,,}`, `${var^^}`, `readarray`, `declare -A`, `sed -i` without `''`, and GNU-only `date` invocation in `tools/*.sh` is replaced with a portable equivalent. See "Implementation notes" below for concrete replacements.
- [ ] **If Strategy 2:** a preamble function `require_gnu_userland()` runs before any other logic. It checks bash version and grep capability. Failures print a precise remediation command and exit 1.
- [ ] Either way, the **shebang line** is reconsidered. Current `#!/usr/bin/env bash` finds whatever `bash` is first on PATH. If Strategy 2 is chosen, the preamble must guard against bash 3.2 even if shebang resolves to it.

### C. Verification on macOS

The implementing agent **cannot run on macOS** (it runs in a Linux container). So verification has to be specified, not performed:

- [ ] Add a comment block at the top of `tools/file.sh` documenting "Tested on:" with the GNU/Linux invocation that the agent verified, plus a "Known macOS invocation:" line showing the exact command Vivek should run.
- [ ] If Strategy 2 was chosen, the preamble's error messages must be tested by **simulating** the failure on Linux: temporarily alias `bash` to a 3.2 stub, or `PATH=/usr/bin grep` to force BSD-less grep — verify error path fires correctly. Document the simulation in the PR.
- [ ] If Strategy 1 was chosen, add a test that runs the script against a temp ticket file in CI under `bash --posix` or with bash version pinned (best-effort — bash 3.2 is hard to get in CI; document the limitation if so).

### D. Documentation updates

- [ ] `AGENTS.md` (root) gets a short note in a new or existing "Local environment" section: "macOS users: ensure `bash` >= 4 and GNU grep on PATH before running `tools/*.sh`. Run `brew install bash grep` once. See `tools/README.md` for details." (Or whatever the actual instruction becomes after the implementation choice.)
- [ ] `tools/README.md` is created (or updated if it exists). It documents:
  - Required toolchain (bash version, grep flavor, any other utilities)
  - The exact macOS invocation if the script isn't fully portable
  - Why these scripts exist (one-line link to METHODOLOGY.md)
- [ ] No reference in any doc to the old non-portable invocation as if it were normal. The macOS invocation, if still needed, is named explicitly as a workaround.

### E. Test/lint gate

- [ ] `pytest -q` passes.
- [ ] `ruff check .` passes (covers any Python in `tools/`).
- [ ] `mypy app/` passes (no change to `app/` expected).
- [ ] `lint-imports` passes.
- [ ] `shellcheck tools/*.sh` passes. **Add shellcheck to the pre-commit / CI checks if it isn't already there.** This is the single highest-leverage prevention for future GNU-isms. Shellcheck flags most of them (`SC2207` for `mapfile` alternatives, `SC2018`/`SC2019` for case conversion, etc.).
- [ ] If shellcheck isn't currently in CI: add it. The job runs on every PR touching `tools/*.sh`.

---

## Files likely touched

- `tools/file.sh` — primary target. Either rewritten for portability or guarded with a preamble.
- `tools/regen_context.py` — if it shells out via `subprocess.run(["bash", ...])` or similar, also subject to the same rules. Likely unaffected since Python's stdlib is portable, but verify.
- `tools/README.md` — created or expanded.
- `AGENTS.md` (root) — one-paragraph note added.
- `.github/workflows/ci.yml` — add shellcheck job if not present.
- `.pre-commit-config.yaml` — add shellcheck hook if pre-commit is used (verify whether it is — check `pyproject.toml` and `.pre-commit-config.yaml`).

---

## Out of scope

- Any change to `tools/file.sh`'s **logic**. This is purely a portability/robustness pass. Don't refactor the validation logic, don't change error messages beyond what's needed for the preamble, don't rename variables, don't reorder steps. If a non-portable construct is the cleanest expression of the intent, rewrite it minimally — do not "improve" the surrounding code.
- Any change to GitHub Actions other than adding shellcheck. The board API logic, milestone handling, and post-merge hooks stay exactly as they are.
- Any change to TICKET-M6's deliverables. M6 is already filed (#70) and unrelated.
- Rewriting `tools/file.sh` in Python. Tempting (Python is portable by default), but it's a separate decision with its own tradeoffs. If the agent finds the bash rewrite excessively painful, **stop and report**. Don't unilaterally rewrite in Python.
- Cross-platform support for Windows. macOS + Linux is the target. Windows is explicitly out of scope.

---

## Implementation notes

### Concrete replacements (Strategy 1)

If the agent picks Strategy 1, use these specific rewrites. Test each by running the modified script against a real ticket file in `docs/TICKETS/`.

#### `mapfile -t ARRAY < <(cmd)` → portable read loop

**Current (tools/file.sh:48):**
```bash
mapfile -t NEW_FILES < <(git ls-files --others --exclude-standard docs/TICKETS/TICKET-*.md 2>/dev/null || true)
```

**Replacement:**
```bash
NEW_FILES=()
while IFS= read -r line; do
  NEW_FILES+=("$line")
done < <(git ls-files --others --exclude-standard docs/TICKETS/TICKET-*.md 2>/dev/null || true)
```

`< <(...)` process substitution works in bash 3.2. The empty-array initializer (`NEW_FILES=()`) is portable.

#### `grep -oP 'pattern'` → `sed -nE 's/.../.../p'` or `awk`

**Current (tools/file.sh, multiple lines):**
```bash
filename_id="$(echo "$basename_f" | grep -oP '^TICKET-[A-Z0-9-]+(?=-[a-z])')"
priority="$(echo "$content" | grep -oP '(?<=\*\*Priority:\*\* )(CRITICAL|HIGH|MEDIUM|LOW)' | head -1)"
milestone="$(echo "$content" | grep -oP '(?<=\*\*Milestone:\*\* ).+' | head -1 | tr -d '\r')"
issue_num="$(echo "$issue_url" | grep -oP '\d+$')"
```

**Replacement (using sed -nE — POSIX-ish, works on BSD and GNU):**
```bash
# Filename ID — first capture group, stop before -lowercase
filename_id="$(echo "$basename_f" | sed -nE 's/^(TICKET-[A-Z0-9-]+)-[a-z].*/\1/p')"

# Priority — lookbehind not available in BRE/ERE, capture instead
priority="$(echo "$content" | sed -nE 's/.*\*\*Priority:\*\* (CRITICAL|HIGH|MEDIUM|LOW).*/\1/p' | head -1)"

# Milestone — same pattern
milestone="$(echo "$content" | sed -nE 's/.*\*\*Milestone:\*\* (.+)$/\1/p' | head -1 | tr -d '\r')"

# Issue number — trailing digits
issue_num="$(echo "$issue_url" | sed -nE 's|.*/([0-9]+)$|\1|p')"
```

`sed -nE` uses extended regex on both BSD and GNU. The `-n` suppresses default output; `p` prints only matched substitutions. Lookbehind isn't supported, so use capture groups instead.

**Alternative (awk):**
```bash
priority="$(echo "$content" | awk -F'\\*\\*Priority:\\*\\* ' '/\*\*Priority:\*\*/{print $2}' | awk '{print $1}' | head -1)"
```
sed is cleaner here. Use awk only if sed gets ugly.

#### `${var,,}` (lowercase) → `tr` or `awk`

**Current (tools/file.sh:147):**
```bash
priority_lower="${VALID_PRIORITIES[$i],,}"
```

**Replacement:**
```bash
priority_lower="$(echo "${VALID_PRIORITIES[$i]}" | tr '[:upper:]' '[:lower:]')"
```

`tr` is POSIX. Works everywhere.

#### `readarray` — same as `mapfile`, same fix.

#### `sed -i ''` vs `sed -i`

Not currently used in `tools/file.sh` (verify with `grep -n "sed -i" tools/file.sh`). If introduced later, the portable form is:
```bash
# Cross-platform sed -i
if sed --version 2>/dev/null | grep -q GNU; then
  sed -i 's/foo/bar/' file
else
  sed -i '' 's/foo/bar/' file
fi
```
Or skip the in-place edit and use a temp file:
```bash
sed 's/foo/bar/' file > file.tmp && mv file.tmp file
```

#### `declare -A` — not currently used. Document as forbidden in tools/README.md.

#### `date -d` — not currently used. Document the BSD form (`date -j -f '%Y-%m-%d' "$date_str"`) in tools/README.md if introduced.

### Preamble for Strategy 2

If the agent picks Strategy 2, here's the preamble template:

```bash
#!/usr/bin/env bash
# tools/file.sh — requires bash >= 4 and GNU grep on PATH

require_gnu_userland() {
  # Bash version check
  if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
    echo "Error: this script requires bash >= 4 (you have ${BASH_VERSION})." >&2
    echo "  macOS users: brew install bash" >&2
    echo "  Then invoke with: /opt/homebrew/bin/bash tools/file.sh" >&2
    exit 1
  fi

  # GNU grep check (BSD grep doesn't support -P)
  if ! echo "test" | grep -qP "te" 2>/dev/null; then
    echo "Error: this script requires GNU grep (your grep doesn't support -P)." >&2
    echo "  macOS users: brew install grep" >&2
    echo "  Then invoke with: PATH=\"/opt/homebrew/opt/grep/libexec/gnubin:\$PATH\" tools/file.sh" >&2
    exit 1
  fi
}

require_gnu_userland

# ... rest of script unchanged ...
```

### Shellcheck integration

Add to `.github/workflows/ci.yml`:

```yaml
  shellcheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run shellcheck
        uses: ludeeus/action-shellcheck@master
        with:
          scandir: ./tools
```

If `.pre-commit-config.yaml` exists, also add:
```yaml
  - repo: https://github.com/shellcheck-py/shellcheck-py
    rev: v0.10.0.1
    hooks:
      - id: shellcheck
```

---

## Test cases

1. **Strategy chosen and documented:** PR description names which strategy was picked and why (1 paragraph).
2. **No `mapfile` or `readarray` remains in `tools/*.sh`** if Strategy 1 — `grep -nE "mapfile|readarray" tools/*.sh` returns 0 matches.
3. **No `grep -P` or `grep -oP` remains in `tools/*.sh`** if Strategy 1 — `grep -nE "grep -[oP]*P" tools/*.sh` returns 0 matches.
4. **No `${var,,}` or `${var^^}` remains in `tools/*.sh`** if Strategy 1 — `grep -nE '\$\{[A-Z_]+\[.+\],,\}|\$\{[A-Z_]+,,\}' tools/*.sh` returns 0 matches.
5. **Preamble fires correctly** if Strategy 2 — manually test by `BASH_VERSINFO=(3 2)` override or by running under a stubbed bash. Document the test in the PR.
6. **Script runs end-to-end** against a test ticket file. Use a throwaway `docs/TICKETS/TICKET-TEST-portability.md` (delete before opening PR). Verify issue creation, board add, commit, push all succeed.
7. **Shellcheck passes** on all `tools/*.sh`. `shellcheck tools/*.sh` returns exit 0.
8. **CI shellcheck job exists and runs** on PR.
9. **`tools/README.md` exists** and documents required toolchain.
10. **`AGENTS.md` mentions local-env setup** in a discoverable section.

---

## Notes

- **The fragile part is testing on macOS.** The implementing agent runs in Linux. It cannot directly verify that the rewrites work on stock macOS bash 3.2 + BSD grep. Mitigation: every replacement in this ticket cites which constructs are POSIX vs bash-3.2-OK vs GNU-only. The agent is expected to be precise about this, not "it should work."
- **Why not just rewrite in Python:** `tools/file.sh` is 200 lines of `gh` CLI + git orchestration. Rewriting in Python means adopting `subprocess.run` patterns, handling escaping, re-doing the validation logic, and adding tests. That's a 4–6 hour ticket, not a 1.5 hour ticket, and it loses the "just read the script to understand the workflow" property. Bash is fine if it's portable bash. If the agent disagrees after reading the script and proposes a Python rewrite, **stop and open a discussion ticket** — don't unilaterally rewrite.
- **Why this ticket exists at all:** the previous chat hit `mapfile` and `grep -P` failures while filing TICKET-M6. Both were solved with `brew install` workarounds, but the workarounds aren't in any doc. The next agent or contributor on macOS would hit the same wall. Codify it now while the failure modes are fresh.
- **shellcheck is the long-term defense.** Once it's in CI, future GNU-isms get flagged automatically. The ticket's most durable output is shellcheck-in-CI, not the specific rewrites.
- **Assumption (verify before implementing):** `tools/regen_context.py` does not shell out to bash in a way that re-introduces these issues. If it does (e.g. `subprocess.run(["bash", "-c", "..."])`), the same portability rules apply to those inline strings.
- **Assumption:** there are no other `.sh` files in `tools/` beyond `file.sh`. If there are, they're in scope too. `ls tools/*.sh` to confirm.
- **Assumption:** Vivek's shell environment will not have `/opt/homebrew/bin` ahead of `/usr/bin` on PATH by default. If a future "Permanent fix in user shell" instruction is added (`brew shellenv` in `.zprofile`), that's a separate concern — this ticket assumes the worst-case PATH and either makes the script work anyway (Strategy 1) or errors loudly (Strategy 2).
