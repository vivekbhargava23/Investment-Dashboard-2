# TICKET-RD4 — Split analytics.py + "explain this number" component

**Priority:** HIGH
**Milestone:** Dashboard Redesign
**Recommended model:** Sonnet — a mechanical package split plus a new reusable component with one wired usage.
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-06-04)
**Depends on:** —
**Consolidates:** TICKET-C5 (#110, split analytics.py) + the old RD4 (explain-this-number component). The split makes analytics editable per-tab; introducing the explain component during the split means one pass over the analytics code.

> **After this ticket merges, `analytics.py` is a per-tab package, and there is a reusable "metric that explains itself" component proven on one analytics metric.** Every later analytic adopts this component (`REDESIGN_STRATEGY.md` §5).

---

## Problem

`app/ui/pages/analytics.py` is ~1100 lines holding five tabs; editing one forces loading all five. Separately, analytics numbers (alpha, Herfindahl, Sharpe…) have no explanation, so the user neither trusts nor understands them.

## Acceptance criteria

### Split analytics into a package (was C5)

- [ ] Create `app/ui/pages/analytics/` with `__init__.py` (re-exports `render`), `_shell.py` (tab routing), and `performance.py`, `concentration.py`, `correlation.py`, `technicals.py`, `sizer.py`.
- [ ] Each `_render_*_tab` + its local helpers/constants move into the matching module as `render()`. No module exceeds ~300 lines. Delete the old `analytics.py`.
- [ ] Nav still routes "Analytics & Risk" to `app.ui.pages.analytics`; tab switching and session-state keys behave identically (pure layout change — no computation changes).

### Explain-this-number component (was RD4)

- [ ] New `app/ui/components/explainable_metric.py`: `ExplanationSpec(label, value_str, meaning, formula: list[str], inputs: dict[str,str], source_note)`, `render_explainable_metric(spec)` (value + meaning + a `how?` popover with formula + inputs table), and a pure `build_explain_prompt(spec) -> str`.
- [ ] An "Ask AI to explain this number" affordance that surfaces the assembled prompt (session-state key or copyable block) — **no inference backend in this ticket**; document as a follow-up.
- [ ] One reference usage: wire the concentration tab's **Herfindahl** metric through `render_explainable_metric` (formula + the actual weights).
- [ ] The component computes no finance math — it formats what callers pass (domain math stays in `app/domain/`).

## Files likely touched

- `app/ui/pages/analytics/` package (new) replacing `app/ui/pages/analytics.py`,
  `app/ui/main.py` (route unchanged — package `__init__` provides `render`),
  `app/ui/components/explainable_metric.py` (new),
  `tests/unit/ui/test_explainable_metric.py` (new).

## Out of scope

- ❌ The AI inference backend — affordance + prompt only.
- ❌ Retrofitting all metrics through the component — later tickets adopt it (RD7 first).
- ❌ Auditing/fixing the underlying math — done as each metric is wired through `how?`.
- ❌ Changing any analytics computation during the split.

## Tests

- [ ] `from app.ui.pages.analytics import render` still works; each tab renders; no tab module > ~300 lines.
- [ ] `build_explain_prompt` yields a complete, stable string; `ExplanationSpec` validates required fields.
- [ ] `pytest && ruff check . && mypy app/ && lint-imports` all pass.
