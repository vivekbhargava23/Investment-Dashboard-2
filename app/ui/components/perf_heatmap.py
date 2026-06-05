"""Performance heatmap for the Live Overview.

Rows are labelled ``TICKER (Company W.W%)`` where ``W.W%`` is the position's share
of total live value (one decimal). A grid of every held ticker (rows) against each
return window (columns: 1D / 5D /
1M / 3M / 6M / 1Y / 2Y / 5Y / YTD), each cell coloured by that window's return on
the **same** diverging green↔red scale and ±``RETURN_CLAMP_PCT`` clamp as the
treemap (RD10) — the scale lives in ``_chart_styles`` so the two can't drift. The
return % is printed in-cell; ``None`` cells show an em dash on the neutral colour,
never a fabricated 0%.

Rows are sorted by **current holding fraction** (live EUR value) descending — the
largest position on top — with stale (no live value) holdings last, consistent with
the positions table's stale-last rule. The returns come from RD9's cached stats map
(the same one the treemap reads) — no second OHLC fetch.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

import plotly.graph_objects as go
import streamlit as st

from app.domain.positions import LivePosition
from app.domain.returns import ALL_WINDOWS, ReturnWindow, WindowStats
from app.ui.components._chart_styles import (
    AXIS_COLOR,
    CHART_BG,
    RETURN_CLAMP_PCT,
    RETURN_COLORSCALE,
)
from app.ui.format import format_pct

# In-cell / axis text colour. Dark slate reads on every cell colour across the
# scale (loss red, neutral grey, gain green).
_CELL_TEXT_COLOR = "#111827"


@dataclass(frozen=True)
class _Row:
    ticker: str
    label: str  # e.g. "MU (Micron 10.0%)", "MU (10.0%)", or "MU"
    value: Decimal | None  # live EUR value (holding size); None when stale → last
    pcts: dict[ReturnWindow, Decimal | None]


def _row_label(ticker: str, name: str, weight_pct: Decimal | None) -> str:
    """Row label: ticker plus, in parens, the company name and holding weight.

    Weight is the position's share of total live value, one decimal place (e.g.
    ``MU (Micron 10.0%)``). A stale holding has no weight → name only, or just the
    ticker when neither name nor weight is available.
    """
    parts: list[str] = []
    if name:
        parts.append(name)
    if weight_pct is not None:
        parts.append(f"{weight_pct:.1f}%")
    inner = " ".join(parts)
    return f"{ticker} ({inner})" if inner else ticker


def _rows(
    positions: dict[str, LivePosition],
    stats_map: dict[str, dict[ReturnWindow, WindowStats | None]],
    windows: Sequence[ReturnWindow],
    name_lookup: dict[str, str],
) -> list[_Row]:
    """One row per held ticker, sorted by holding size (live EUR value) desc.

    Stale holdings (no live value) can't be sized, so they sort last — the same
    stale-last rule the positions table uses.
    """
    valued: list[tuple[LivePosition, Decimal | None, dict[ReturnWindow, Decimal | None]]] = []
    for p in positions.values():
        window_stats = stats_map.get(p.ticker, {})
        pcts = {
            w: (stat.pct if (stat := window_stats.get(w)) is not None else None)
            for w in windows
        }
        value = p.live_value_eur.amount if p.live_value_eur is not None else None
        valued.append((p, value, pcts))

    # Weight is share of total live value; stale (valueless) holdings are excluded
    # from the denominator, consistent with how the treemap sizes tiles.
    total = sum((v for _, v, _ in valued if v is not None), Decimal("0"))
    rows: list[_Row] = []
    for p, value, pcts in valued:
        weight = (value / total * 100) if (value is not None and total > 0) else None
        label = _row_label(p.ticker, name_lookup.get(p.ticker, ""), weight)
        rows.append(_Row(p.ticker, label, value, pcts))

    def sort_key(row: _Row) -> tuple[bool, Decimal]:
        # Primary key puts stale (valueless) holdings last; secondary sorts the
        # rest by holding size descending — the biggest position on top.
        return (row.value is None, -(row.value if row.value is not None else Decimal("0")))

    rows.sort(key=sort_key)
    return rows


def build_heatmap_figure(
    positions: dict[str, LivePosition],
    stats_map: dict[str, dict[ReturnWindow, WindowStats | None]],
    *,
    name_lookup: dict[str, str],
    windows: Sequence[ReturnWindow] = ALL_WINDOWS,
    clamp_pct: Decimal = RETURN_CLAMP_PCT,
    height: int | None = None,
) -> go.Figure | None:
    """Build the performance heatmap, or ``None`` when there are no holdings.

    Rows are sorted by holding size (live EUR value) descending. Colour = each
    cell's window return clamped to ±``clamp_pct`` on the shared ``RETURN_COLORSCALE``
    (``zmid=0``). A ``None`` return colours neutral (0.0 on the scale lands on the
    midpoint), prints ``—`` in the cell, and says ``n/a`` in the hover — never a
    fabricated 0%.
    """
    rows = _rows(positions, stats_map, windows, name_lookup)
    if not rows:
        return None

    window_labels = [w.value for w in windows]
    z: list[list[float]] = []
    text: list[list[str]] = []
    customdata: list[list[str]] = []
    for row in rows:
        z_row: list[float] = []
        text_row: list[str] = []
        hover_row: list[str] = []
        for w in windows:
            pct = row.pcts.get(w)
            # None → 0.0 lands on the neutral midpoint colour (cmid). The text, not
            # the colour, is what tells None apart from a real 0% return.
            z_row.append(float(pct) if pct is not None else 0.0)
            ret_text = format_pct(pct, signed=True) if pct is not None else "—"
            text_row.append(ret_text)
            hover_text = ret_text if pct is not None else "n/a"
            hover_row.append(f"{row.ticker} · {w.value}: {hover_text}")
        z.append(z_row)
        text.append(text_row)
        customdata.append(hover_row)

    fig = go.Figure(
        go.Heatmap(
            x=window_labels,
            y=[row.label for row in rows],
            z=z,
            text=text,
            texttemplate="%{text}",
            textfont={"size": 11, "color": _CELL_TEXT_COLOR},
            customdata=customdata,
            hovertemplate="%{customdata}<extra></extra>",
            colorscale=RETURN_COLORSCALE,
            zmin=float(-clamp_pct),
            zmid=0.0,
            zmax=float(clamp_pct),
            xgap=2,
            ygap=2,
            colorbar={"title": "Return %", "ticksuffix": "%"},
        )
    )
    # Height grows with the number of holdings so rows stay legible.
    fig_height = height if height is not None else max(160, 34 * len(rows) + 70)
    fig.update_layout(
        height=fig_height,
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        xaxis={
            "side": "top",
            "showgrid": False,
            "zeroline": False,
            "color": AXIS_COLOR,
            "fixedrange": True,
            "automargin": True,
        },
        yaxis={
            # First row (best return) at the top.
            "autorange": "reversed",
            "showgrid": False,
            "zeroline": False,
            "color": AXIS_COLOR,
            "fixedrange": True,
            "automargin": True,
        },
        hovermode="closest",
    )
    return fig


def render_heatmap(
    positions: dict[str, LivePosition],
    stats_map: dict[str, dict[ReturnWindow, WindowStats | None]],
    *,
    name_lookup: dict[str, str],
    height: int | None = None,
) -> None:
    """Render the performance heatmap, or a placeholder when there are no holdings."""
    fig = build_heatmap_figure(
        positions,
        stats_map,
        name_lookup=name_lookup,
        height=height,
    )
    if fig is None:
        st.info("No holdings to display in the performance heatmap.")
        return
    st.plotly_chart(fig, use_container_width=True)
