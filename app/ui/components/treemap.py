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

from app.domain.money import Currency, Money
from app.domain.positions import LivePosition
from app.domain.returns import ReturnWindow, WindowStats
from app.ui.components._chart_styles import (
    RETURN_CLAMP_PCT,
    RETURN_COLORSCALE,
    base_layout,
)
from app.ui.format import format_eur, format_pct

# RETURN_CLAMP_PCT / RETURN_COLORSCALE are the shared return scale (see
# _chart_styles); re-exported here so existing treemap importers keep working and
# so the heatmap (RD11) provably colours on the same scale.
__all__ = [
    "RETURN_CLAMP_PCT",
    "RETURN_COLORSCALE",
    "build_treemap_figure",
    "render_treemap",
]


@dataclass(frozen=True)
class _Tile:
    ticker: str
    name: str
    value: Money
    weight_pct: float
    eur_per_native: Decimal  # current FX rate used to show the high/low in EUR
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
        # EUR-per-native for the high/low: 1 for EUR positions; the live FX rate
        # (already EUR-per-native) otherwise. Shown at current FX, matching how the
        # rest of the page's live EUR figures are derived.
        if p.live_price_native.currency == Currency.EUR or p.current_fx_rate is None:
            eur_per_native = Decimal("1")
        else:
            eur_per_native = p.current_fx_rate
        tiles.append(
            _Tile(
                ticker=p.ticker,
                name=name_lookup.get(p.ticker, ""),
                value=value,
                weight_pct=weight,
                eur_per_native=eur_per_native,
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
        high_eur = Money(amount=tile.stats.high * tile.eur_per_native, currency=Currency.EUR)
        low_eur = Money(amount=tile.stats.low * tile.eur_per_native, currency=Currency.EUR)
        lines.append(
            f"<br>{window.value} high {format_eur(high_eur)} · low {format_eur(low_eur)}"
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
    # base_layout(show_axes=False) sets hovermode=False, which disables hovering
    # entirely. A treemap hovers per-tile, so force "closest" to re-enable it.
    layout["hovermode"] = "closest"
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
