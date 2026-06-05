# TICKET-PANEL-1 — Catalysts data layer (model, port, JSON adapter, rules, seed)

**Priority:** HIGH
**Milestone:** Investment Panel
**Recommended model:** Sonnet — mirrors the existing `thesis_map` data layer (model + port + JSON adapter) plus pure categorisation helpers and a service. Clear tests, low blast radius.
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (Cowork session 2026-06-05)
**Depends on:** ADR-013 (must be Accepted first — establishes the data file, ownership, and rules).
**Implements:** ADR-013.

> **After this ticket merges, the app can load `data/catalysts.json` — a Cowork-maintained list of dated, categorised, impact-rated events — through a clean domain/port/adapter/service stack, with no rendering yet.** PANEL-2 renders it.

---

## Problem

Per ADR-013, catalysts are a curated L3 decision-support data file (like `thesis.json`),
maintained by the chat surface and read-only in the app. We need the data layer: domain
models, the categorisation rules as pure functions, a port, a JSON adapter, a loader/merge
service, and a seed file — built before any UI so PANEL-2 has something to render.

## Acceptance criteria

### Domain (pure — `app/domain/catalysts.py`)

- [ ] `CatalystEvent` (Pydantic v2, `frozen=True`): `ticker: str | None`, `date: date`,
      `label: str`, `category: CatalystCategory`, `impact: Impact`, `scope: Scope`,
      `date_confidence: DateConfidence`, `source: str = ""`, `notes: str = ""`.
- [ ] Literals: `CatalystCategory = earnings | macro | product | regulatory | dividend | lockup`;
      `Impact = high | med | low`; `Scope = position | portfolio`;
      `DateConfidence = confirmed | estimated`.
- [ ] `CatalystsDocument` (`frozen=True`): `version: int = 1`, `updated: date | None = None`,
      `events: list[CatalystEvent] = []`.
- [ ] Pure helpers (no I/O, no `datetime.now()`):
      - `upcoming(events, *, as_of, within_days=None) -> list[CatalystEvent]` — events on/after
        `as_of`, sorted by date, optionally capped to a horizon.
      - `for_ticker(events, ticker) -> list[CatalystEvent]` — position events for that ticker
        **plus** all `scope == "portfolio"` events.
      - `time_band(event, *, as_of) -> TimeBand` where `TimeBand = this_week | this_month |
        next_3_months | later` (the bands the timeline groups by).
- [ ] Categorisation helpers encoding ADR-013's rules, for reproducible curation/testing:
      - `categorise(label, *, hint=None) -> CatalystCategory` (keyword rules: "earnings/results"
        → earnings; "FOMC/CPI/ECB/jobs" → macro; "keynote/launch/GTC/Computex/WWDC" → product;
        "export control/antitrust/FDA/tariff/ruling" → regulatory; "ex-div/dividend" → dividend;
        "lockup/index/rebalance" → lockup).
      - `default_impact(category, *, is_decision=False) -> Impact` (earnings→high;
        regulatory→high if decision else med; macro→med; product→med/low; dividend/lockup→low).
      These are advisory helpers; explicit values in the JSON always win.

### Port + Adapter

- [ ] `app/ports/catalysts.py::CatalystsRepository` Protocol: `load() -> CatalystsDocument`,
      `save(doc) -> None` (mirror `ports/thesis_map.py`).
- [ ] `app/adapters/catalysts/repo.py::JsonCatalystsRepository` mirroring
      `adapters/thesis_map/repo.py`: missing file → empty `CatalystsDocument()`; atomic
      temp-file + `os.replace` write; `model_validate` on load.
- [ ] Wiring: a `get_catalysts_repo()` provider in `app/ui/wiring.py` pointing at
      `data/catalysts.json` (path via the same config mechanism as the thesis repo).

### Service

- [ ] `app/services/catalysts.py::get_portfolio_catalysts(held_tickers, *, as_of, repo, within_days=None) -> list[CatalystEvent]`:
      loads the doc, keeps events whose `ticker` is in `held_tickers` **or** `scope ==
      "portfolio"`, filters to upcoming (`>= as_of`), sorts by date.
- [ ] `app/services/catalysts.py::get_position_catalysts(ticker, *, as_of, repo) -> list[CatalystEvent]`
      for the per-position view (uses `for_ticker` + `upcoming`).

### Seed data

- [ ] `data/catalysts.json` seeded with **real, verifiable** events for current holdings,
      each with a `source` and honest `date_confidence`. Confirmed dates marked `confirmed`;
      anything inferred marked `estimated`. **No fabricated-as-certain dates** (METHODOLOGY).
- [ ] Include at least the portfolio-wide macro events (next FOMC, next CPI, ECB) as
      `ticker: null, scope: "portfolio"`.

## Files likely touched

- `app/domain/catalysts.py` (new), `app/ports/catalysts.py` (new),
- `app/adapters/catalysts/__init__.py` + `repo.py` (new),
- `app/services/catalysts.py` (new), `app/ui/wiring.py` (provider),
- `data/catalysts.json` (new seed),
- `tests/unit/domain/test_catalysts.py`, `tests/integration/test_catalysts_repo.py` (new).

## Out of scope

- ❌ Any rendering / timeline UI — PANEL-2.
- ❌ An auto-fetch adapter for earnings/economic calendars — explicitly deferred in ADR-013.
- ❌ The app writing `catalysts.json` at runtime — it is read-only in the app; curation happens
      in Cowork via PR.

## Test cases

1. `for_ticker(events, "NVDA")` returns NVDA position events **and** every portfolio-scope
   event, and nothing for other tickers' position events.
2. `upcoming(events, as_of=2026-06-05)` drops past events and sorts ascending by date.
3. `time_band` buckets a date 3 days out as `this_week`, 20 days as `this_month`, 60 days as
   `next_3_months`, 200 days as `later`, for a fixed `as_of`.
4. `categorise("Q1 FY27 earnings")` → `earnings`; `categorise("FOMC decision")` → `macro`;
   `categorise("Computex keynote")` → `product`; `categorise("BIS export-control review")` →
   `regulatory`.
5. `JsonCatalystsRepository.load()` on a missing path returns an empty document; round-trips a
   saved document byte-for-stable via `model_dump(mode="json")`.
6. `get_portfolio_catalysts(["NVDA"], as_of=…)` includes NVDA events + macro events, excludes a
   `MSFT` position event.
7. Seed `data/catalysts.json` validates against `CatalystsDocument` and every event has a
   non-empty `source`.
8. `pytest && ruff check . && mypy app/ && lint-imports` all pass.

## Notes

- **Verified template (2026-06-05):** `app/ports/thesis_map.py`, `app/domain/thesis_map.py`
  (frozen Pydantic `ThesisMapDocument`/`ThesisEntry`), and `app/adapters/thesis_map/repo.py`
  (atomic write, missing-file→empty) are the exact patterns to mirror. `data/thesis.json`
  (`{"version":1,"entries":{...}}`) is the sibling precedent for `data/catalysts.json`.
- Domain hard rules: `Decimal` not needed here (no money); but **no `datetime.now()`** — every
  function takes `as_of`. Keep `app/domain/catalysts.py` free of I/O and streamlit.
- `import-linter` will enforce the dependency direction (domain imports nothing app-internal).
- The held-ticker set for `get_portfolio_catalysts` should come from live positions in the UI
  (PANEL-2), so the service takes `held_tickers` as a parameter (no globals).
