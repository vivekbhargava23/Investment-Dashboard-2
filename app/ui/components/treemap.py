"""Allocation treemap for the Live Overview.

Tiles are sized by live EUR value and coloured by the selected window's return
(RD9's cached return-stats map) on a diverging green↔red scale centred at 0, with
a fixed symmetric clamp (±``RETURN_CLAMP_PCT``) so a single outlier can't wash out
the scale. Colours reuse the existing chart tokens (``CANDLE_UP`` / ``CANDLE_DOWN``
and the neutral grey) rather than inventing new hex values.

Each tile prints the window return; the hover adds the EUR value, weight %, and the
window's high/low (native price, candlestick-style). Switching the colour window
re-reads the cached stats map — no OHLC refetch and no return recompute.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import plotly.graph_objects as go
import streamlit as st

from app.domain.money import Money
from app.domain.positions import LivePosition
from app.domain.returns import ReturnWindow, WindowStats
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
    currency: str
    stats: WindowStats | None


def _return_pct(stats: WindowStats | None) -> Decimal | None:
    return stats.pct if stats is not None else None


def _renderable_tiles(
    positions: dict[str, LivePosition],
    stats_map: dict[str, dict[ReturnWindow, WindowStats | None]],
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
        assert p.live_price_native is not None  # non-stale ⇒ native price present
        weight = float(value.amount / total * 100) if total > 0 else 0.0
        tiles.append(
            _Tile(
                ticker=p.ticker,
                name=name_lookup.get(p.ticker, ""),
                value=value,
                weight_pct=weight,
                currency=p.live_price_native.currency.value,
                stats=stats_map.get(p.ticker, {}).get(window),
            )
        )
    return tiles


def _tile_label(ticker: str, name: str, ret_text: str) -> str:
    """In-tile text: bold ticker, name (if any), then the window return."""
    name_line = f"{name}<br>" if name else ""
    return f"<b>{ticker}</b><br>{name_line}{ret_text}"


def _tile_hover(tile: _Tile, window: ReturnWindow, ret_text: str) -> str:
    name_line = f"{tile.name}<br>" if tile.name else ""
    lines = [
        f"<b>{tile.ticker}</b><br>{name_line}",
        f"{format_eur(tile.value)} · {tile.weight_pct:.1f}% of portfolio<br>",
        f"{window.value} return: {ret_text}",
    ]
    if tile.stats is not None:
        lines.append(
            f"<br>{window.value} high {tile.currency} {tile.stats.high:,.2f}"
            f" · low {tile.currency} {tile.stats.low:,.2f}"
        )
    return "".join(lines)


def build_treemap_figure(
    positions: dict[str, LivePosition],
    stats_map: dict[str, dict[ReturnWindow, WindowStats | None]],
    window: ReturnWindow,
    *,
    name_lookup: dict[str, str],
    clamp_pct: Decimal = RETURN_CLAMP_PCT,
    height: int = 420,
) -> go.Figure | None:
    """Build the allocation treemap, or ``None`` when nothing is renderable.

    Size = live EUR value; colour = the ``window`` return clamped to ±``clamp_pct``.
    A ``None`` return for the window colours neutral (cmid=0), prints "n/a" in the
    tile, and shows "n/a" in the hover — never a fabricated 0%.
    """
    tiles = _renderable_tiles(positions, stats_map, window, name_lookup)
    if not tiles:
        return None

    labels = [t.ticker for t in tiles]
    values = [float(t.value.amount) for t in tiles]
    # None return → cmid (0) so the tile lands on the neutral midpoint colour. The
    # raw (unclamped) value is fine here; cmin/cmax do the clamping at render time.
    colors = [float(p) if (p := _return_pct(t.stats)) is not None else 0.0 for t in tiles]

    tile_texts: list[str] = []
    hover: list[str] = []
    for t in tiles:
        pct = _return_pct(t.stats)
        ret_text = format_pct(pct, signed=True) if pct is not None else "n/a"
        tile_texts.append(_tile_label(t.ticker, t.name, ret_text))
        hover.append(_tile_hover(t, window, ret_text))

    fig = go.Figure(
        go.Treemap(
            labels=labels,
            parents=[""] * len(tiles),
            values=values,
            text=tile_texts,
            texttemplate="%{text}",
            # Hover content goes through customdata — treemap does not expose a
            # %{hovertext} token, so the hover string is carried per-node here.
            customdata=hover,
            hovertemplate="%{customdata}<extra></extra>",
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
    stats_map: dict[str, dict[ReturnWindow, WindowStats | None]],
    window: ReturnWindow,
    *,
    name_lookup: dict[str, str],
    height: int = 420,
) -> None:
    """Render the allocation treemap, or a placeholder when nothing is renderable."""
    fig = build_treemap_figure(
        positions, stats_map, window, name_lookup=name_lookup, height=height
    )
    if fig is None:
        st.info("No live positions to display in the treemap.")
        return
    st.plotly_chart(fig, use_container_width=True)
