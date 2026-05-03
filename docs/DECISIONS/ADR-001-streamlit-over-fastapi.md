# ADR-001 — Streamlit over FastAPI + React

**Status:** Accepted
**Date:** 2026-05-03
**Decided by:** Vivek + Claude (chat session)

## Context

The previous build was Streamlit-based and accumulated cruft until it stopped working. The temptation when rebuilding is to "do it properly" with FastAPI + React + a real frontend. The mockup is also visually polished enough that React would be a natural fit.

## Decision

**We are sticking with Streamlit** for this rebuild.

## Reasoning

1. **Single user, no auth needed.** The whole reason FastAPI + React exists is multi-user, multi-device, public-facing apps. None of those apply.
2. **Iteration speed matters more than polish.** This is a personal tool that needs to evolve as the investment thesis evolves. Streamlit's reload-on-save loop is unbeatable for this.
3. **The mockup is achievable in Streamlit.** With custom CSS injected via `st.markdown(unsafe_allow_html=True)` and careful component composition, the dark-mode investor look is a 1-day job, not a week.
4. **The bottleneck is the domain layer, not the UI.** FIFO correctness, FX timing, tax invariants — these are where the real engineering happens. UI is the easy 20%.
5. **The previous build's cruft was not Streamlit's fault.** It was a discipline failure (no tests, no separation of concerns, scope creep). The new architecture solves that regardless of UI framework.

## Consequences

- **Pro:** Fast iteration, single language, no separate frontend deploy, no CORS, no auth boilerplate.
- **Pro:** Streamlit Cloud deploy is one-click if we ever want it remote.
- **Con:** Not a CV showpiece for "modern frontend skills." Acceptable — the FIFO engine and 4-layer architecture are the technical signals.
- **Con:** Some interactions (drag-to-reorder, real-time updates) are awkward. Acceptable — none are needed for the core use case.

## Reversal cost

If we ever want to switch: services and domain layers stay 100% intact. Only `app/ui/` is rewritten. Estimated rebuild: 2 weeks. Low.

## Alternatives considered

- **FastAPI + React/Next:** rejected — 3× the build effort for marginal benefit.
- **FastAPI + HTMX + Tailwind:** considered seriously. Rejected because adding a second deployable surface (backend + frontend templates) for a single-user app is overhead without payoff.
- **Pure Jupyter notebook:** rejected — no UI for daily use.
