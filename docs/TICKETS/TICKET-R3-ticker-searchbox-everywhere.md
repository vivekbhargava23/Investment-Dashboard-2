# TICKET-R3 — Use ticker searchbox on all ticker-pickers

**Status:** QUEUED
**Priority:** MEDIUM
**Estimated session length:** 1 hr
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Milestone:** UI polish

---

## Problem

`render_ticker_searchbox` (`app/ui/components/ticker_searchbox.py`) is the canonical autocomplete component, used on Research, Manage, Mappings, and Company. Four other pages still use plain `st.selectbox` for ticker picking, even when the picker is over a known list of owned tickers — which means no company-name search ("RHM" works, "Rheinmetall" doesn't) and inconsistent UX between pages:

- `app/ui/pages/overview.py:346` — Position Chart picker.
- `app/ui/pages/analytics.py:622` — Technicals tab picker.
- `app/ui/pages/analytics.py:822` — Position Sizer picker.
- `app/ui/components/sell_simulator.py:236` — Sell Simulator picker.

## Solution

Add a thin wrapper component `render_owned_ticker_picker` in `ticker_searchbox.py` that constrains the searchbox to an owned-ticker set while keeping name-search:

```python
def render_owned_ticker_picker(
    key: str,
    owned_tickers: list[str],
    resolver: TickerResolver,
    *,
    placeholder: str = "Pick or search a position…",
    default_ticker: str | None = None,
) -> str | None:
    """Searchbox restricted to owned tickers; returns selected symbol or None."""
```

Internally it uses `st_searchbox` with a callback that:

1. Runs the resolver's `resolve(query)` to get fuzzy matches.
2. Filters to symbols in `owned_tickers`.
3. Falls back to a substring match on `owned_tickers` themselves so an empty query still shows the full list as a dropdown.

Replace the four `st.selectbox` call sites with this wrapper. Pre-seeding (`default_ticker` from session state / link handoffs like `simulator_default_ticker`) preserves current behaviour.

## Acceptance criteria

- [ ] `render_owned_ticker_picker` added to `ticker_searchbox.py` with unit tests.
- [ ] Empty query shows the full owned-ticker list (so the picker is still usable like a dropdown).
- [ ] Typing a company name (e.g. "Rheinmetall") surfaces matching owned tickers (e.g. `RHM.DE`).
- [ ] Overview Position Chart, Technicals tab, Position Sizer tab, and Sell Simulator all use the wrapper.
- [ ] Pre-seeding via `default_ticker` still works (Tax → Simulator handoff via `simulator_default_ticker` keeps functioning).
- [ ] `manage.py:274` fallback `text_input("Ticker (autocomplete unavailable)")` is preserved for the no-resolver case.
- [ ] All tests pass; ruff / mypy / lint-imports clean.

### Manual smoke

- Overview Position Chart: type "rhein" → `RHM.DE` appears → chart renders.
- Technicals: same.
- Sell Simulator: type "apple" → `AAPL` appears → form populates.
- Position Sizer: same.

## Out of scope

- Replacing the `selectbox` for non-ticker fields (currency, benchmark dropdowns).
- Removing the `_build_ticker_labels` yfinance-Search loop in Sell Simulator — see TICKET-R5 (live-positions consolidation can supply names cheaper).

## Notes

- Assumes `streamlit_searchbox` widget keys are unique per page. Keep the existing key convention (`overview_chart_ticker`, `technicals_ticker`, `sim_ticker_select`, `sizer_ticker`) and use suffix `_searchbox` to avoid colliding with existing session-state keys.
- Assumes `get_ticker_resolver()` is reachable from each call site; it already is via `wiring.py`.
