# ADR-013 — Catalysts as Cowork-maintained data (`catalysts.json`)

**Status:** Proposed (2026-06-05)
**Date:** 2026-06-05
**Drafted by:** Vivek + Claude (Cowork session 2026-06-05)
**Related:** Extends [ADR-006](ADR-006-instrument-classification-as-data.md) (classification-as-data) to a second decision-support data file. Originates from the Claude Design redesign bundle (`dashboard-10-may`, Behavioral Ledger → Catalysts tab).

---

## Context

The Claude Design redesign of the dashboard includes a **Catalysts timeline**: upcoming
dated events per holding (earnings, macro prints, product launches, regulatory decisions),
plotted on a time axis and colour-coded by category. Vivek wants this on the Overview page,
portfolio-wide, so clusters ("three earnings dates in late May") are visible at a glance.

The open question this ADR settles is **where catalyst data comes from and who owns it.**
Two options were considered:

1. **Live adapter** — fetch earnings/economic calendars from a market-data provider at
   render time. Rejected for now: the existing providers (yfinance/finnhub) give patchy,
   inconsistent forward-calendar coverage; macro events (FOMC/CPI/ECB) aren't per-ticker;
   and categorisation/impact judgement isn't something the feed provides. This would
   reintroduce the "documented approximation" failure mode METHODOLOGY warns about.

2. **Curated data file maintained by the chat surface (Cowork).** The three-surface model
   in METHODOLOGY already treats the chat surface as where judgement lives. A Cowork chat
   can search the web for confirmed dates, apply categorisation rules, and write a small
   JSON file that the app reads. The app stays offline-capable and deterministic.

This mirrors the precedent already set by `thesis.json` (ADR-006): a small, human/AI-curated
JSON decision-support file, read-only at the domain layer, versioned in git.

## Decision

**Catalysts are stored in `data/catalysts.json`, a curated decision-support (L3) data file
maintained by the Cowork chat surface and read — never written — by the application.**

### Ownership and update flow

- The **Cowork chat surface** is the writer. In a chat, Claude searches for confirmed event
  dates, applies the categorisation rules below, and produces an updated `catalysts.json`.
- Updates land through the **normal PR flow** (data-only diff, easy for Vivek to eyeball),
  not by the app writing the file at runtime. Cadence is ad-hoc ("refresh catalysts for X").
- The application (services + UI) **only reads** the file. This keeps the L1/L2/L3 boundary
  intact: if `catalysts.json` is missing or stale, valuation and the book of record are
  unaffected.

### Layering (unchanged architecture, new instances of existing patterns)

- **Domain** (`app/domain/catalysts.py`): pure Pydantic models (`CatalystEvent`,
  `CatalystsDocument`) and pure categorisation/filtering functions. No I/O, no
  `datetime.now()` — `as_of` is passed in explicitly (per the domain hard rules).
- **Port** (`app/ports/catalysts.py`): `CatalystsRepository` Protocol with `load()` /
  `save()`, mirroring `ports/thesis_map.py`.
- **Adapter** (`app/adapters/catalysts/`): `JsonCatalystsRepository`, mirroring
  `adapters/thesis_map/repo.py` (atomic temp-file write, missing-file → empty document).
- **Service** (`app/services/catalysts.py`): loads the document, merges portfolio-wide
  (`scope: "portfolio"`, `ticker: null`) events onto each held ticker, filters to held
  positions, and sorts by date.
- **UI**: renders the timeline; caching via `st.cache_data` (the file is tiny — read once
  per session).

### Schema

```json
{
  "version": 1,
  "updated": "2026-06-05",
  "events": [
    {
      "ticker": "NVDA",
      "date": "2026-05-28",
      "label": "Q1 FY27 earnings",
      "category": "earnings",
      "impact": "high",
      "scope": "position",
      "date_confidence": "confirmed",
      "source": "investor.nvidia.com",
      "notes": ""
    },
    {
      "ticker": null,
      "date": "2026-06-12",
      "label": "FOMC decision",
      "category": "macro",
      "impact": "med",
      "scope": "portfolio",
      "date_confidence": "confirmed",
      "source": "federalreserve.gov",
      "notes": ""
    }
  ]
}
```

Field semantics:

- `ticker` — held ticker the event belongs to, or `null` for portfolio-wide events.
- `category` — one of `earnings | macro | product | regulatory | dividend | lockup`.
- `impact` — `high | med | low` (drives the timeline dot size).
- `scope` — `position` (one holding) or `portfolio` (applies to all holdings; macro).
- `date_confidence` — `confirmed` (a real published date) or `estimated` (a best guess,
  rendered visually distinct so it is never mistaken for a filing date). This is the
  honesty mechanism that keeps us out of the "fake-data" trap; no event is silently
  presented as certain.
- `source` — where the date came from (URL or short note), for auditability.

### Categorisation rules (the curation contract)

These rules are how the chat surface assigns `category` and `impact` consistently. They are
also encoded as pure helper functions in `app/domain/catalysts.py` so categorisation is
reproducible and testable, not ad-hoc per chat.

| Category | What it captures | Typical `scope` | Typical `impact` |
|---|---|---|---|
| `earnings` | Quarterly/annual results on the company's fiscal calendar | position | high |
| `macro` | FOMC, CPI, ECB, jobs report, Jackson Hole | portfolio (`ticker: null`) | med |
| `product` | Keynotes, launches, GTC/Computex/WWDC, conferences | position | low–med |
| `regulatory` | Export controls, antitrust, FDA, tariffs, EU rulings | position | high on a decision date, med on a hearing |
| `dividend` | Ex-dividend / payment dates | position | low |
| `lockup` | Lock-up expiries, index add/remove, rebalances | position | low (med if the holding is large) |

Impact heuristic: **does this date plausibly reprice the stock?** Decisions and earnings are
`high`; scheduled prints are `med`; calendar noise is `low`.

## Consequences

**Positive**

- The app stays offline-capable and deterministic; no flaky forward-calendar feed.
- Judgement (categorisation, impact, what's worth listing) lives where judgement belongs —
  the chat surface — and is captured as data, consistent with ADR-006.
- The timeline degrades gracefully: missing file → empty timeline, never a crash.
- `date_confidence` makes uncertainty explicit, satisfying the METHODOLOGY ban on silent
  approximations.

**Negative / costs**

- Freshness is manual: catalysts are only as current as the last curation chat. Mitigated
  by the `updated` timestamp surfaced in the UI so staleness is visible.
- A new data file to keep in sync with the held set (events for sold-out tickers become
  dead weight). The service filters to held positions on read, so dead entries are inert
  but should be pruned periodically.

**Follow-up**

- A later ADR may revisit an auto-fetch adapter for the mechanical subset (earnings dates,
  ex-dates, FOMC) layered *under* the curated file, if a provider with reliable coverage is
  adopted. Out of scope here.

## Implementation tickets

- **TICKET-PANEL-1** — catalysts data layer (domain model, port, JSON adapter,
  categorisation helpers, seed `data/catalysts.json`).
- **TICKET-PANEL-2** — catalysts timeline UI on the Overview page (portfolio-wide) and the
  per-position variant.
