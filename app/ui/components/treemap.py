"""Allocation treemap for the Live Overview.

Tiles are sized by live EUR value and coloured by the selected window's return
(RD9's returns map) on a diverging green↔red scale centred at 0, with a fixed
symmetric clamp (±``RETURN_CLAMP_PCT``) so a single outlier can't wash out the
scale. Colours reuse the existing chart tokens (``CANDLE_UP`` / ``CANDLE_DOWN``
and the neutral grey) rather than inventing new hex values.

Switching the colour window re-colours from the cached returns map with no OHLC
refetch and no return recompute — the caller passes a pre-built returns map.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import plotly.graph_objects as go
import streamlit as st

from app.domain.money import Money
from app.domain.positions import LivePosition
from app.domain.returns import ReturnWindow
from app.ui.components._chart_styles import (
    CANDLE_DOWN,
    CANDLE_UP,
    CORRELATION_BUCKET_COLORS,
    base_layout,
)
from app.ui.format import format_eur, format_pct

# Symmetric clamp: cmin/cmax = ∓/± this percent. A module constant so one outlier
# (a +40% mover) doesn't compress every other tile to the same shade.
RETURN_CLAMP_PCT = Decimal("14")

# Diverging red↔neutral↔green scale built from existing tokens: CANDLE_DOWN (loss
# red) at the low end, the neutral grey at the centre, CANDLE_UP (gain green) at
# the high end. With cmid=0 the midpoint maps to a 0% return.
_NEUTRAL_COLOR = CORRELATION_BUCKET_COLORS["neutral"]
RETURN_COLORSCALE: list[list[float | str]] = [
    [0.0, CANDLE_DOWN],
    [0.5, _NEUTRAL_COLOR],
    [1.0, CANDLE_UP],
]


@dataclass(frozen=True)
class _Tile:
    ticker: str
    name: str
    value: Money
    weight_pct: float
    return_pct: Decimal | None


def _renderable_tiles(
    positions: dict[str, LivePosition],
    returns_map: dict[str, dict[ReturnWindow, Decimal | None]],
    window: ReturnWindow,
    name_lookup: dict[str, str],
) -> list[_Tile]:
    """Non-stale positions as tiles, weighted by share of total live EUR value.

    Stale positions (no ``live_value_eur``) are excluded — they can't be sized,
    consistent with how the positions table treats stale rows.
    """
    live = [
        p for p in positions.values()
        if not p.is_stale and p.live_value_eur is not None
    ]
    total = sum((p.live_value_eur.amount for p in live if p.live_value_eur), Decimal("0"))
    tiles: list[_Tile] = []
    for p in live:
        value = p.live_value_eur
        assert value is not None  # narrowed by the filter above
        weight = float(value.amount / total * 100) if total > 0 else 0.0
        ret = returns_map.get(p.ticker, {}).get(window)
        tiles.append(
            _Tile(
                ticker=p.ticker,
                name=name_lookup.get(p.ticker, ""),
                value=value,
                weight_pct=weight,
                return_pct=ret,
            )
        )
    return tiles


def build_treemap_figure(
    positions: dict[str, LivePosition],
    returns_map: dict[str, dict[ReturnWindow, Decimal | None]],
    window: ReturnWindow,
    *,
    name_lookup: dict[str, str],
    clamp_pct: Decimal = RETURN_CLAMP_PCT,
    height: int = 420,
) -> go.Figure | None:
    """Build the allocation treemap, or ``None`` when nothing is renderable.

    Size = live EUR value; colour = the ``window`` return clamped to ±``clamp_pct``.
    A ``None`` return for the window colours neutral (cmid=0) and shows "n/a" in the
    hover — never a fabricated 0%.
    """
    tiles = _renderable_tiles(positions, returns_map, window, name_lookup)
    if not tiles:
        return None

    labels = [t.ticker for t in tiles]
    names = [t.name for t in tiles]
    values = [float(t.value.amount) for t in tiles]
    # None return → cmid (0) so the tile lands on the neutral midpoint colour. The
    # raw (unclamped) value is fine here; cmin/cmax do the clamping at render time.
    colors = [float(t.return_pct) if t.return_pct is not None else 0.0 for t in tiles]

    hover: list[str] = []
    for t in tiles:
        ret_txt = (
            format_pct(t.return_pct, signed=True) if t.return_pct is not None else "n/a"
        )
        name_line = f"{t.name}<br>" if t.name else ""
        hover.append(
            f"<b>{t.ticker}</b><br>{name_line}"
            f"{format_eur(t.value)} · {t.weight_pct:.1f}% of portfolio<br>"
            f"{window.value} return: {ret_txt}"
        )

    fig = go.Figure(
        go.Treemap(
            labels=labels,
            parents=[""] * len(tiles),
            values=values,
            text=names,
            texttemplate="<b>%{label}</b><br>%{text}",
            hovertext=hover,
            hovertemplate="%{hovertext}<extra></extra>",
            marker={
                "colors": colors,
                "colorscale": RETURN_COLORSCALE,
                "cmin": float(-clamp_pct),
                "cmid": 0.0,
                "cmax": float(clamp_pct),
                "showscale": True,
                "colorbar": {"title": f"{window.value} %", "ticksuffix": "%"},
            },
        )
    )
    layout = base_layout(height=height, show_axes=False)
    fig.update_layout(**layout)
    return fig


def render_treemap(
    positions: dict[str, LivePosition],
    returns_map: dict[str, dict[ReturnWindow, Decimal | None]],
    window: ReturnWindow,
    *,
    name_lookup: dict[str, str],
    height: int = 420,
) -> None:
    """Render the allocation treemap, or a placeholder when nothing is renderable."""
    fig = build_treemap_figure(
        positions, returns_map, window, name_lookup=name_lookup, height=height
    )
    if fig is None:
        st.info("No live positions to display in the treemap.")
        return
    st.plotly_chart(fig, use_container_width=True)
