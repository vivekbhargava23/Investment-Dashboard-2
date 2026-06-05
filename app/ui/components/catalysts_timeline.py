"""Catalysts timeline component (TICKET-PANEL-2).

Renders PANEL-1's catalyst events grouped into time bands, colour-coded by
category and weighted by impact, with a companion table below. Two modes:

- ``portfolio`` — the Overview's book-wide timeline. Each position event shows its
  ticker; ``scope == "portfolio"`` (macro) events are marked book-wide.
- ``position`` — a single ticker's drilldown (Company Deep Dive), where the ticker
  is already established context so it isn't repeated per row.

``date_confidence == "estimated"`` events render with a hollow dot, a ``~`` date
prefix and muted styling so an inferred date is never mistaken for a confirmed one
(ADR-013). All event-supplied text is HTML-escaped before it reaches the HTML grid
(TICKET-ROBUST-1).
"""

from __future__ import annotations

import html
from datetime import date
from typing import Literal

import pandas as pd
import streamlit as st

from app.domain.catalysts import CatalystEvent, TimeBand, time_band
from app.ui.components._chart_styles import CATALYST_CATEGORY_COLORS
from app.ui.render import render_html

Mode = Literal["portfolio", "position"]

# Display order + labels for the time bands the timeline groups by. The order is
# the scan order the design calls for: nearest-term first.
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


def _category_label(category: str) -> str:
    return _CATEGORY_LABELS.get(category, category.title())


def group_events_by_band(
    events: list[CatalystEvent], *, as_of: date
) -> list[tuple[TimeBand, list[CatalystEvent]]]:
    """Group events into non-empty time bands, ordered This week → Later.

    Events are date-ascending within each band. Empty bands are omitted so the
    timeline never renders a blank section.
    """
    buckets: dict[TimeBand, list[CatalystEvent]] = {band: [] for band, _ in _BAND_ORDER}
    for event in sorted(events, key=lambda e: e.date):
        buckets[time_band(event, as_of=as_of)].append(event)
    return [(band, buckets[band]) for band, _ in _BAND_ORDER if buckets[band]]


def build_catalysts_table(events: list[CatalystEvent], *, mode: Mode) -> pd.DataFrame:
    """Companion table sorted by date.

    Columns: Date · Event · (Ticker, portfolio mode only) · Category · Impact.
    """
    ordered = sorted(events, key=lambda e: e.date)
    rows: list[dict[str, str]] = []
    for event in ordered:
        row: dict[str, str] = {"Date": event.date.isoformat(), "Event": event.label}
        if mode == "portfolio":
            # Macro / book-wide events have no ticker; label them Portfolio.
            row["Ticker"] = event.ticker if event.ticker is not None else "Portfolio"
        row["Category"] = _category_label(event.category)
        row["Impact"] = event.impact.title()
        rows.append(row)
    columns = (
        ["Date", "Event"]
        + (["Ticker"] if mode == "portfolio" else [])
        + ["Category", "Impact"]
    )
    return pd.DataFrame(rows, columns=columns)


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
        f'<span class="cat-legend-today">today · {today}</span>'
        "</div>"
    )


def _event_html(event: CatalystEvent, *, mode: Mode) -> str:
    color = CATALYST_CATEGORY_COLORS.get(event.category, _FALLBACK_COLOR)
    estimated = event.date_confidence == "estimated"
    book_wide = event.scope == "portfolio"

    dot_class = "cat-dot estimated" if estimated else "cat-dot"
    # Estimated dots are hollow (border only); confirmed dots are filled.
    dot_style = f"border-color:{color}" if estimated else f"background:{color}"

    date_text = f"{event.date:%b} {event.date.day}"
    date_prefix = "~" if estimated else ""

    event_classes = f"catalyst-event impact-{event.impact}"
    if estimated:
        event_classes += " estimated"

    parts = [
        f'<span class="{dot_class}" style="{dot_style}"></span>',
        f'<span class="catalyst-date">{date_prefix}{html.escape(date_text)}</span>',
    ]
    # In portfolio mode a position event shows its ticker; in position mode the
    # ticker is already the page context, so it isn't repeated.
    if mode == "portfolio" and not book_wide and event.ticker:
        parts.append(f'<span class="catalyst-ticker">{html.escape(event.ticker)}</span>')
    parts.append(f'<span class="catalyst-label">{html.escape(event.label)}</span>')
    if book_wide:
        parts.append('<span class="catalyst-scope">Book-wide</span>')

    return f'<div class="{event_classes}">' + "".join(parts) + "</div>"


def _timeline_html(events: list[CatalystEvent], *, as_of: date, mode: Mode) -> str:
    bands: list[str] = []
    for band, band_events in group_events_by_band(events, as_of=as_of):
        rows = "".join(_event_html(e, mode=mode) for e in band_events)
        bands.append(
            '<div class="catalyst-band">'
            f'<div class="catalyst-band-title">{html.escape(_BAND_LABELS[band])}</div>'
            f'<div class="catalyst-events">{rows}</div>'
            "</div>"
        )
    return '<div class="catalysts-timeline">' + "".join(bands) + "</div>"


def render_catalysts_timeline(
    events: list[CatalystEvent],
    *,
    as_of: date,
    mode: Mode,
    updated: date | None = None,
) -> None:
    """Render the catalysts legend, banded timeline, and companion table.

    ``updated`` is the catalysts document's ``updated`` date; when given it is
    surfaced so staleness of the curated file is visible.
    """
    if not events:
        render_html('<div class="empty-note">No upcoming catalysts.</div>')
        return

    render_html(_legend_html(as_of))
    render_html(_timeline_html(events, as_of=as_of, mode=mode))
    if updated is not None:
        render_html(
            f'<div class="text-note">catalysts as of {html.escape(updated.isoformat())}</div>'
        )
    st.dataframe(
        build_catalysts_table(events, mode=mode),
        use_container_width=True,
        hide_index=True,
    )
