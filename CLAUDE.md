# CLAUDE.md

Read and follow `AGENTS.md` in this directory. It contains all project rules,
rituals, and constraints. Treat it as your system instructions for this repo.

Everything in `AGENTS.md` applies to you. "The implementation agent" means you.

## Validation gate

Run the full validation chain (pytest + ruff + mypy + lint-imports, inside the
`investment-dashboard` conda env) with the single command:

```bash
bash scripts/gate.sh
```

Always use this script. Do **not** invoke the checks as a chained
`source ... && conda activate ... && pytest && ruff ... ` command. The chained form
embeds `$(conda info --base)` command substitution, which forces a permission prompt
on every run; `scripts/gate.sh` is a static invocation that is pre-approved in
`.claude/settings.local.json`. The script runs all four checks (no fail-fast) and
exits non-zero if any fail — same Step 7 semantics as `AGENTS.md`.
