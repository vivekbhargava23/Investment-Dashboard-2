# TICKET-THESIS-1 — Thesis status & horizon as editable data, not hardcoded UI dicts

**Status:** IN_PROGRESS
**Priority:** MEDIUM
**Estimated session length:** 2 – 3 hr
**Drafted by:** Vivek + Claude (Cowork review 2026-06-02)
**Implemented by:** _pending_
**Recommended model:** Sonnet — well-scoped and mirrors the existing `isin_map` data+repo pattern, with clear acceptance criteria. (Escalate to Opus only if you also want a full in-app editing UI rather than a hand/Mappings-edited data file — that's a bigger surface.)
**Milestone:** Data correctness
**Depends on:** None.

> **After this ticket merges, a holding's thesis and horizon come from data, not from a dict baked into a UI file.** Today an unknown ticker silently shows "intact / H2" — confidently wrong. This moves the classification to an editable data file (the ADR-006 principle, same as ISIN mappings) and renders "unknown" honestly.

---

## Problem

`app/ui/pages/overview.py:29–38` hardcodes two ticker→value dictionaries **in the UI layer**:

```python
_PLACEHOLDER_THESIS_STATUS: dict[str, ...] = {"NVDA": "intact", "RHM.DE": "intact", ...}
_PLACEHOLDER_HORIZON: dict[str, ...] = {"NVDA": "H1", "ETN": "H1", ...}
```

This violates two project rules: ARCHITECTURE.md "UI layer: no business logic / no
`if`-branching on business logic in UI", and ADR-006 "instrument classification is
user-editable data, not source code". Concretely, every lookup uses `.get(ticker,
"intact")` / `.get(ticker, "H2")`, so **any holding not in the dict is silently reported as
an intact, H2 position** — wrong, and invisible.

These values are read in several places (find them all — comprehensive):

- The KPI "Thesis Status" counts (overview.py:264–275).
- The per-ticker thesis pills (overview.py:277–280).
- The positions-table "Horizon" and "Thesis" columns (overview.py:107–108, via
  `render_thesis_badge` in `app/ui/components/badges.py`).
- Any other page that surfaces thesis/horizon — audit `analytics.py`, `tax.py`, and
  `components/badges.py` callers before finishing.

## Solution

Mirror the existing ISIN-map pattern (it's the in-repo precedent for "classification as
data"):

1. **Data file** `data/thesis.json` (gitignored-allowlisted like `isin_map.json` — see
   `.gitignore` `!data/isin_map.json`), shape e.g.
   `{ "version": 1, "entries": { "NVDA": {"thesis": "intact", "horizon": "H1"} } }`.
   Seed it from the current placeholder dicts so behaviour is unchanged for known tickers.
2. **Domain model + port + adapter** following `app/domain/isin_map.py` +
   `app/ports/isin_map.py` + `app/adapters/isin_map/repo.py`. Keep the domain model frozen
   Pydantic, no I/O.
3. **Wiring** `get_thesis_repo()` in `app/ui/wiring.py`.
4. **Render honestly:** unknown ticker → thesis `"unknown"` / horizon `"—"`, with a distinct
   neutral badge (extend `render_thesis_badge` to accept an `"unknown"` state). Never default
   a missing holding to "intact".
5. Remove `_PLACEHOLDER_THESIS_STATUS` / `_PLACEHOLDER_HORIZON` from `overview.py`.

## Acceptance criteria

- [ ] `data/thesis.json` exists, seeded from today's placeholder values; load/save via a typed repo + port + adapter mirroring `isin_map`.
- [ ] `overview.py` reads thesis/horizon from the repo; the two hardcoded dicts are gone.
- [ ] An unknown ticker renders an explicit "unknown"/"—" badge — not "intact"/"H2".
- [ ] Every site that read the old dicts now reads the data source (grep for `thesis`/`horizon` across `app/ui/` returns no hardcoded ticker maps).
- [ ] Domain stays pure; `lint-imports` clean. All tests pass; ruff / mypy clean.

### Manual smoke

- Add a holding not in `thesis.json` → Overview shows it as "unknown", not a false "intact".
- Edit `data/thesis.json` to flip a ticker to "broken" → the pill, the count, and the table cell all update.
