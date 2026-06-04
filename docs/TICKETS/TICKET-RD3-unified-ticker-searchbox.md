# TICKET-RD3 — Unified ticker searchbox on all pickers

**Priority:** MEDIUM
**Milestone:** Dashboard Redesign
**Recommended model:** Sonnet — one wrapper component + four call-site swaps with tests.
**Estimated session length:** 1 – 1.5 hr
**Drafted by:** Vivek + Claude (chat 2026-06-04)
**Depends on:** RD0 (focus selector establishes the searchbox/resolver usage; avoids touching the overview chart picker twice)
**Consolidates:** TICKET-R3 (#103) — same objective; supersede that issue.

> **After this ticket merges, every ticker picker is a name-searchable searchbox, not a plain selectbox.** "Rheinmetall" finds `RHM.DE`, consistently across pages.

---

## Problem

`render_ticker_searchbox` is the canonical autocomplete, but four pickers still use plain `st.selectbox` (no company-name search, inconsistent UX): overview Position Chart (`overview.py`), Technicals tab and Position Sizer tab (`analytics.py`), and the Sell Simulator (`sell_simulator.py`).

## Acceptance criteria

- [ ] Add `render_owned_ticker_picker(key, owned_tickers, resolver, *, placeholder=…, default_ticker=None) -> str | None` to `ticker_searchbox.py`: resolver fuzzy-match filtered to owned tickers, empty query shows the full owned list (still usable as a dropdown), substring fallback on owned tickers.
- [ ] Replace the four `st.selectbox` pickers with the wrapper. Pre-seeding via `default_ticker` (e.g. `simulator_default_ticker` handoff) still works.
- [ ] `manage.py` `text_input("Ticker (autocomplete unavailable)")` fallback for the no-resolver case is preserved.
- [ ] Typing a company name surfaces matching owned tickers.

## Files likely touched

- `app/ui/components/ticker_searchbox.py` (wrapper + tests), `app/ui/pages/overview.py`,
  `app/ui/pages/analytics.py` (or the analytics package after RD4), `app/ui/components/sell_simulator.py`.

## Out of scope

- ❌ Non-ticker selectboxes (currency, benchmark dropdowns).
- ❌ Removing the `_build_ticker_labels` yfinance-Search loop in Sell Simulator (already addressed by the merged live-positions consolidation).

## Tests

- [ ] Empty query returns full owned list; name query surfaces the right symbol; `default_ticker` pre-seed works.
- [ ] `pytest && ruff check . && mypy app/ && lint-imports` all pass.

> **Note:** if RD4 (analytics split) lands first, the Technicals/Sizer pickers live in the new `app/ui/pages/analytics/` package — update those call sites there.
