"""Compatibility shim for the two pages TICKET-SYNC-7 is about to delete.

The real implementation moved to `instrument_card.py`, where the feed, the tax
kind and removal are three independent controls. The Import Workbench and the
ISIN Mappings page still import from here; both go away in the same ticket, and
this file with them.
"""
from __future__ import annotations

import streamlit as st

from app.domain.tax.classification import InstrumentKind
from app.ports.ticker_resolver import TickerMatch
from app.ui.components.instrument_card import (
    KIND_LABEL,
    KIND_OPTIONS,
    SHARED_TICKER_HELP,
    SHARED_TICKER_LABEL,
    invalidate_view_caches,
    shared_ticker_message,
    suggest_kind,
)
from app.ui.components.ticker_searchbox import render_ticker_searchbox
from app.ui.wiring import get_ticker_resolver

__all__ = [
    "KIND_LABEL",
    "KIND_OPTIONS",
    "SHARED_TICKER_HELP",
    "SHARED_TICKER_LABEL",
    "invalidate_view_caches",
    "render_isin_mapper_row",
    "render_kind_selector",
    "shared_ticker_message",
    "suggest_kind",
]


def render_kind_selector(
    key: str,
    *,
    suggested: InstrumentKind | None = None,
) -> InstrumentKind | None:
    """Render the Tax kind selectbox. Returns the selected kind (may be None)."""
    options_with_none: list[InstrumentKind | None] = [None, *KIND_OPTIONS]
    idx = options_with_none.index(suggested) if suggested in options_with_none else 0
    return st.selectbox(
        "Tax kind",
        options=options_with_none,
        index=idx,
        format_func=lambda k: "— pick a kind —" if k is None else KIND_LABEL.get(k, str(k)),
        key=key,
        label_visibility="collapsed",
    )


def render_isin_mapper_row(
    isin: str,
    description: str,
    *,
    key_prefix: str,
) -> tuple[TickerMatch | None, InstrumentKind | None]:
    """Render ticker searchbox + kind selector for one ISIN. Returns selected values."""
    selected_match: TickerMatch | None = render_ticker_searchbox(
        key=f"{key_prefix}_search_{isin}",
        resolver=get_ticker_resolver(),
        placeholder=f"Search for {description[:30] or 'this security'}…",
    )
    suggested = suggest_kind(selected_match.symbol) if selected_match else None
    selected_kind = render_kind_selector(
        key=f"{key_prefix}_kind_{isin}",
        suggested=suggested,
    )
    return selected_match, selected_kind
