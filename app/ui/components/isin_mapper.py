"""Shared ISIN mapping UI component — ticker search + tax-kind selector.

Used by both the Import Workbench (manual-review panel) and the Mappings page.
"""
from __future__ import annotations

import streamlit as st

from app.domain.tax.classification import InstrumentKind
from app.ports.ticker_resolver import TickerMatch
from app.services.isin_remap import TickerAlreadyMappedError
from app.services.valuation import clear_caches
from app.ui.components.ticker_searchbox import render_ticker_searchbox
from app.ui.wiring import (
    get_company_provider,
    get_live_fx_provider,
    get_price_provider,
    get_ticker_resolver,
)

KIND_OPTIONS: list[InstrumentKind] = list(InstrumentKind)

KIND_LABEL: dict[InstrumentKind, str] = {
    InstrumentKind.AKTIE: "Aktie",
    InstrumentKind.AKTIENFONDS: "Aktienfonds (ETF)",
    InstrumentKind.MISCHFONDS: "Mischfonds",
    InstrumentKind.RENTENFONDS: "Rentenfonds",
    InstrumentKind.IMMOBILIENFONDS: "Immobilienfonds",
    InstrumentKind.IMMOBILIENFONDS_AUSLAND: "Immobilienfonds (Ausland)",
    InstrumentKind.SONSTIGE: "Sonstige",
    InstrumentKind.DIVIDENDE: "Dividende",
    InstrumentKind.ZINSEN: "Zinsen",
}


@st.cache_data(ttl=3600, show_spinner=False)
def suggest_kind(ticker: str) -> InstrumentKind | None:
    """Suggest InstrumentKind from yfinance quoteType. Returns None if unavailable."""
    try:
        qt = get_company_provider().get_quote_type(ticker)
        if qt == "EQUITY":
            return InstrumentKind.AKTIE
        if qt == "ETF":
            return InstrumentKind.AKTIENFONDS
        if qt == "MUTUALFUND":
            return InstrumentKind.MISCHFONDS
        return None
    except Exception:
        return None


def render_kind_selector(
    key: str,
    *,
    suggested: InstrumentKind | None = None,
) -> InstrumentKind | None:
    """Render the Tax kind selectbox. Returns the selected kind (may be None)."""
    options_with_none: list[InstrumentKind | None] = [None] + KIND_OPTIONS
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


# Ticking this passes ``allow_shared_ticker`` — the deliberate "these two ISINs
# are the same instrument" merge of ADR-014 rule 4.
SHARED_TICKER_LABEL = "Same instrument (ISIN change)"

SHARED_TICKER_HELP = "Only tick this when the ISIN changed but the instrument did not."


def shared_ticker_message(exc: TickerAlreadyMappedError) -> str:
    """The warning shown when a ticker is already another mapped ISIN's feed."""
    return (
        f"{exc.ticker} is already the feed for {exc.other_isin}. "
        f"Tick '{SHARED_TICKER_LABEL}' to merge on purpose."
    )


def invalidate_view_caches() -> None:
    """Drop every cached view after a mapping write.

    Positions, NAV and the price/FX feeds are all keyed on tickers, and a remap
    rewrites tickers in place (ADR-014 consequence 1).
    """
    st.cache_data.clear()
    clear_caches(get_price_provider(), get_live_fx_provider())
