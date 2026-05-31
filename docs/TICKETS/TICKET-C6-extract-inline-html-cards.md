# TICKET-C6 — Replace inline-HTML cards with CSS-class components

**Status:** QUEUED
**Priority:** LOW
**Estimated session length:** 1 hr
**Drafted by:** Vivek + Claude Chat (2026-05-31)
**Implemented by:** TBD
**Milestone:** UI polish

---

## Problem

`overview.py` and `tax.py` build KPI cards and positions tables with `render_html(f"""<div style="...">""")` blocks — large f-string HTML with inline CSS. This bypasses `app/ui/styles/dark.css`, makes restyling painful (search-and-replace across files), and resists re-use (the same metric card shape exists in both pages with subtly different inline styles).

## Solution

Extract two reusable components into `app/ui/components/`:

### Component 1 — `metric_card` (extend existing)

`app/ui/components/metric_card.py` already exists. Extend it to cover both pages' KPI tile shapes:

```python
def render_metric_card(
    *,
    label: str,
    value: str,
    sub_value: str | None = None,
    sub_color: Literal["green", "red", "grey", "default"] = "default",
    size: Literal["sm", "md", "lg"] = "md",
) -> None: ...
```

Single HTML template inside the component; uses CSS classes from `dark.css`. Pages call `render_metric_card(label=..., value=..., sub_value=...)` instead of building inline HTML.

### Component 2 — `positions_table`

`app/ui/components/positions_table.py` (new):

- Builds the positions table currently inlined in `overview.py::_build_positions_table_html`.
- Accepts: `live_positions`, `summary`, `trend_data`, `name_lookup` (same args the current function takes).
- Returns: nothing — calls `st.markdown(html, unsafe_allow_html=True)` internally.
- HTML body uses CSS classes; styles move to `dark.css`.

### CSS migration

`app/ui/styles/dark.css` gains classes:

- `.metric-card`, `.metric-card.sm`, `.metric-card.lg`
- `.metric-label`, `.metric-value`, `.metric-sub`
- `.metric-sub.green`, `.metric-sub.red`, `.metric-sub.grey`
- `.positions-table`, `.positions-table th`, `.positions-table td`, `.positions-table .gain-positive`, `.positions-table .gain-negative`

The current inline `style="..."` attributes are deleted from the f-strings.

### Call site changes

- `overview.py`: the four KPI tiles + tax-summary tile call `render_metric_card`. The positions table call uses `render_positions_table`.
- `tax.py`: Sparerpauschbetrag tile, tax-headroom tile, and others call `render_metric_card`.

## Acceptance criteria

- [ ] `metric_card.py` covers both pages' tile shapes.
- [ ] `positions_table.py` extracted and reused.
- [ ] All KPI tiles and the positions table render identically to the current pages (pixel-diff acceptable within font-rendering noise).
- [ ] No `style="..."` inline attributes remain in `overview.py` or `tax.py` (grep clean).
- [ ] All new styles live in `dark.css`.
- [ ] All tests pass; ruff / mypy / lint-imports clean.

### Manual smoke

- Open Live Overview. KPI tiles, tax tile, positions table look identical to before.
- Open Tax page. Sparerpauschbetrag, tax-headroom tiles look identical.
- Change a CSS variable in `dark.css` (e.g. `--text3` to red). All affected tiles update consistently across both pages.

## Out of scope

- Restyling — this is a pure refactor; visual output stays the same.
- Extracting the live-status badges (`● LIVE`, `● PARTIAL`) — separate refactor if needed.
- Migrating the same inline patterns from any analytics tab — that's covered by TICKET-C5's split + a follow-up if needed.

## Notes

- The existing `metric-card` CSS class is referenced in `overview.py` inline styles — verify it's defined in `dark.css` first; extend rather than create from scratch.
- Use Streamlit's `unsafe_allow_html=True` is unavoidable for custom HTML. The migration moves *style* out of f-strings, not HTML structure.
