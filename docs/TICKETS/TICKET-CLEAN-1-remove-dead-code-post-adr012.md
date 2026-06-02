# TICKET-CLEAN-1 — Remove dead code (post-ADR-012 worktree tooling, FX shim, wiring idiom)

**Status:** QUEUED
**Priority:** LOW
**Estimated session length:** 1 – 1.5 hr
**Drafted by:** Vivek + Claude (Cowork review 2026-06-02)
**Implemented by:** _pending_
**Recommended model:** Haiku — mechanical deletions and a one-line idiom swap, each verifiable by grep + the existing test/lint gate. No business logic. (Bump to Sonnet only if removing the FX shim turns out to have live callers that need rewiring.)
**Milestone:** Production hardening
**Depends on:** ADR-012 (worktrees retired) merged first, so the worktree tooling is genuinely dead.

> **Housekeeping pass.** Removes code that nothing should call anymore after the worktree retirement (ADR-012) and the caching review. Each removal is grep-gated — do not delete anything with a live caller; if one exists, rewire it to the canonical function in the same commit.

---

## Scope (delete only after confirming no live callers — grep first)

1. **Worktree tooling, dead after ADR-012.** `tools/run.sh` (ran commands inside a named
   worktree) and `tools/cleanup-worktrees.sh` (pruned merged worktrees). AGENTS.md no longer
   references either (Steps 5/7/9 were rewritten). Remove both scripts and their entries in
   `tools/README.md`. Grep the repo for `run.sh` / `cleanup-worktrees` first to confirm
   nothing else invokes them.

2. **The back-compat FX shim.** `app/ui/wiring.py::get_fx_provider` (wiring.py:64) news up a
   *second* `YfinanceLiveFxAdapter` — a separate instance with its own cache, distinct from
   `get_live_fx_provider()`. Its own docstring says "prefer get_live_fx_provider() /
   get_historical_fx_provider()". Grep for `get_fx_provider`; if callers exist, point each at
   `get_live_fx_provider` (live) or `get_historical_fx_provider` (historical) as appropriate,
   then delete the shim.

3. **Standardize the wiring singleton idiom.** `wiring.py` uses `@lru_cache(maxsize=1)` for
   ten providers and `@st.cache_resource` for one (`get_company_provider`, wiring.py:81+).
   Pick one and apply it consistently. `st.cache_resource` is the Streamlit-correct choice for
   cross-session singletons; converting the `lru_cache` ones to it (or vice-versa) removes a
   "why is this one different" trap. This is the one non-deletion change — keep it in its own
   commit so it's easy to review/revert.

## Acceptance criteria

- [ ] `tools/run.sh` and `tools/cleanup-worktrees.sh` removed; `tools/README.md` updated; repo grep shows no remaining references.
- [ ] `get_fx_provider` removed; any caller rewired to the canonical provider; grep shows no remaining references.
- [ ] `wiring.py` uses a single, consistent singleton-caching idiom across all providers.
- [ ] All tests pass; ruff / mypy / lint-imports clean. (No behaviour change — this is the safety net for a deletion-only ticket.)

### Manual smoke

- `streamlit run app/ui/main.py` still boots; Overview, Tax, Analytics, Company all render and live FX still shows in the top bar.
