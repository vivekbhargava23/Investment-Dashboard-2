"""Catalysts timeline component (TICKET-PANEL-2).

Renders PANEL-1's catalyst events as a horizontal, left-to-right timeline: a
Plotly scatter where each event is a category-coloured marker placed inside its
time zone (This week / This month / Next 3 months / Later), sized by impact and
drawn hollow when its date is ``estimated`` (ADR-013). Book-wide (``scope ==
"portfolio"``) events sit on their own lane above the per-holding lane. Detail
lives in the **hover** — there is no companion table.

Two modes:

- ``portfolio`` — the Overview's book-wide timeline; position markers are labelled
  with their ticker.
- ``position`` — a single ticker's drilldown (Company Deep Dive); the ticker is
  page context, so markers aren't re-labelled.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date
from typing import Literal

import plotly.graph_objects as go
import streamlit as st

from app.domain.catalysts import CatalystEvent, TimeBand, time_band
from app.ui.components._chart_styles import (
    AXIS_COLOR,
    CATALYST_CATEGORY_COLORS,
    CHART_BG,
)
from app.ui.render import render_html

Mode = Literal["portfolio", "position"]

# Display order + labels for the time zones the timeline lays out left → right.
_BAND_ORDER: tuple[tuple[TimeBand, str], ...] = (
    ("this_week", "This week"),
    ("this_month", "This month"),
    ("next_3_months", "Next 3 months"),
    ("later", "Later"),
)
_BAND_LABELS: dict[TimeBand, str] = dict(_BAND_ORDER)

_CATEGORY_LABELS: dict[str, str] = {
    "earnings": "Earnings",
    "macro": "Macro",
    "product": "Product",
    "regulatory": "Regulatory",
    "dividend": "Dividend",
    "lockup": "Lockup",
}

# Fallback colour for any (future) category missing from the token map.
_FALLBACK_COLOR = "#8c8c84"

# Impact → marker size: high reads loudest, low quietest.
_IMPACT_SIZE: dict[str, int] = {"high": 22, "med": 15, "low": 10}

# Lanes (y): book-wide events sit above the per-holding lane.
_LANE_POSITION = 0.0
_LANE_BOOKWIDE = 1.0


def _category_label(category: str) -> str:
    return _CATEGORY_LABELS.get(category, category.title())


def group_events_by_band(
    events: list[CatalystEvent], *, as_of: date
) -> list[tuple[TimeBand, list[CatalystEvent]]]:
    """Group events into non-empty time bands, ordered This week → Later.

    Events are date-ascending within each band. Empty bands are omitted so the
    timeline never renders a blank zone.
    """
    buckets: dict[TimeBand, list[CatalystEvent]] = {band: [] for band, _ in _BAND_ORDER}
    for event in sorted(events, key=lambda e: e.date):
        buckets[time_band(event, as_of=as_of)].append(event)
    return [(band, buckets[band]) for band, _ in _BAND_ORDER if buckets[band]]


@dataclass(frozen=True)
class _Point:
    """A single plotted marker."""

    x: float
    y: float
    color: str
    size: int
    symbol: str  # "circle" (confirmed) | "circle-open" (estimated)
    text: str  # on-marker label (ticker in portfolio mode), or ""
    hover: str


def _hover_text(event: CatalystEvent) -> str:
    estimated = event.date_confidence == "estimated"
    date_str = f"{event.date:%b} {event.date.day}, {event.date.year}"
    prefix = "~" if estimated else ""
    who = (
        event.ticker
        if (event.scope == "position" and event.ticker)
        else "Portfolio"
    )
    conf = " · estimated" if estimated else ""
    # Escaped so a label can't smuggle Plotly hover markup.
    return "<br>".join(
        [
            f"{prefix}{html.escape(date_str)}",
            f"{html.escape(who)} · {html.escape(event.label)}",
            f"{html.escape(_category_label(event.category))} · "
            f"{html.escape(event.impact.title())}{conf}",
        ]
    )


def build_timeline_points(
    events: list[CatalystEvent], *, as_of: date, mode: Mode
) -> list[_Point]:
    """Compute one marker per event.

    Bands lay out left → right; within a band each lane (book-wide / per-holding)
    spreads its events evenly so markers don't overlap. ``x`` is a banded ordinal,
    not a to-scale date — near-term events stay legible instead of clustering.
    """
    points: list[_Point] = []
    for band_index, (_, band_events) in enumerate(
        group_events_by_band(events, as_of=as_of)
    ):
        lanes: dict[float, list[CatalystEvent]] = {
            _LANE_BOOKWIDE: [e for e in band_events if e.scope == "portfolio"],
            _LANE_POSITION: [e for e in band_events if e.scope != "portfolio"],
        }
        for lane_y, lane_events in lanes.items():
            count = len(lane_events)
            for i, event in enumerate(lane_events):
                x = band_index + (i + 1) / (count + 1)
                estimated = event.date_confidence == "estimated"
                book_wide = event.scope == "portfolio"
                text = (
                    event.ticker
                    if (mode == "portfolio" and not book_wide and event.ticker)
                    else ""
                )
                points.append(
                    _Point(
                        x=x,
                        y=lane_y,
                        color=CATALYST_CATEGORY_COLORS.get(
                            event.category, _FALLBACK_COLOR
                        ),
                        size=_IMPACT_SIZE.get(event.impact, 12),
                        symbol="circle-open" if estimated else "circle",
                        text=text,
                        hover=_hover_text(event),
                    )
                )
    return points


def build_catalysts_timeline_figure(
    events: list[CatalystEvent], *, as_of: date, mode: Mode
) -> go.Figure | None:
    """Build the horizontal timeline figure, or ``None`` when there are no events."""
    points = build_timeline_points(events, as_of=as_of, mode=mode)
    if not points:
        return None

    bands = group_events_by_band(events, as_of=as_of)
    band_count = len(bands)

    fig = go.Figure(
        go.Scatter(
            x=[p.x for p in points],
            y=[p.y for p in points],
            mode="markers+text",
            text=[p.text for p in points],
            textposition="top center",
            textfont={"size": 10, "color": AXIS_COLOR},
            marker={
                "color": [p.color for p in points],
                "size": [p.size for p in points],
                "symbol": [p.symbol for p in points],
                # The ring carries the colour for hollow (estimated) markers and is a
                # quiet same-colour border for filled (confirmed) ones.
                "line": {"width": 2, "color": [p.color for p in points]},
            },
            customdata=[p.hover for p in points],
            hovertemplate="%{customdata}<extra></extra>",
            cliponaxis=False,
        )
    )

    # Alternating zone backgrounds + a label per band so the axis reads as
    # This week → Later without a to-scale date axis.
    shapes: list[dict[str, object]] = []
    annotations: list[dict[str, object]] = []
    for band_index, (band, _) in enumerate(bands):
        if band_index % 2 == 1:
            shapes.append(
                {
                    "type": "rect",
                    "xref": "x",
                    "yref": "paper",
                    "x0": band_index,
                    "x1": band_index + 1,
                    "y0": 0,
                    "y1": 1,
                    "fillcolor": "rgba(0,0,0,0.03)",
                    "line": {"width": 0},
                    "layer": "below",
                }
            )
        annotations.append(
            {
                "x": band_index + 0.5,
                "y": 1.0,
                "xref": "x",
                "yref": "paper",
                "yanchor": "bottom",
                "text": _BAND_LABELS[band].upper(),
                "showarrow": False,
                "font": {"size": 10, "color": AXIS_COLOR},
            }
        )

    # "Now" marker at the left edge.
    shapes.append(
        {
            "type": "line",
            "xref": "x",
            "yref": "paper",
            "x0": 0,
            "x1": 0,
            "y0": 0,
            "y1": 1,
            "line": {"color": AXIS_COLOR, "width": 1, "dash": "dot"},
        }
    )

    lane_labels = (
        {_LANE_POSITION: "Holdings", _LANE_BOOKWIDE: "Book-wide"}
        if mode == "portfolio"
        else {_LANE_POSITION: "This holding", _LANE_BOOKWIDE: "Book-wide"}
    )
    fig.update_layout(
        height=240,
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        margin={"l": 80, "r": 20, "t": 26, "b": 10},
        showlegend=False,
        hovermode="closest",
        shapes=shapes,
        annotations=annotations,
        xaxis={
            "range": [-0.05, band_count],
            "showgrid": False,
            "zeroline": False,
            "showticklabels": False,
            "fixedrange": True,
        },
        yaxis={
            "range": [-0.6, 1.6],
            "tickvals": [_LANE_POSITION, _LANE_BOOKWIDE],
            "ticktext": [lane_labels[_LANE_POSITION], lane_labels[_LANE_BOOKWIDE]],
            "showgrid": False,
            "zeroline": False,
            "color": AXIS_COLOR,
            "fixedrange": True,
        },
    )
    return fig


def _legend_html(as_of: date) -> str:
    items = "".join(
        f'<span class="cat-legend-item">'
        f'<span class="cat-dot" style="background:{color}"></span>'
        f"{html.escape(_category_label(category))}</span>"
        for category, color in CATALYST_CATEGORY_COLORS.items()
    )
    today = html.escape(as_of.isoformat())
    return (
        '<div class="catalysts-legend">'
        f"{items}"
        '<span class="cat-legend-item">'
        '<span class="cat-dot cat-dot-estimated"></span>estimated</span>'
        f'<span class="cat-legend-today">today · {today}</span>'
        "</div>"
    )


def render_catalysts_timeline(
    events: list[CatalystEvent],
    *,
    as_of: date,
    mode: Mode,
    updated: date | None = None,
) -> None:
    """Render the catalysts legend and horizontal timeline.

    ``updated`` is the catalysts document's ``updated`` date; when given it is
    surfaced so staleness of the curated file is visible. Event detail lives in the
    marker hover — there is no companion table.
    """
    fig = build_catalysts_timeline_figure(events, as_of=as_of, mode=mode)
    if fig is None:
        render_html('<div class="empty-note">No upcoming catalysts.</div>')
        return

    render_html(_legend_html(as_of))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    if updated is not None:
        render_html(
            f'<div class="text-note">catalysts as of {html.escape(updated.isoformat())}</div>'
        )
