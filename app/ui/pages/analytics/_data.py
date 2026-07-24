"""Shared live-position/summary helpers for the analytics tabs.

The concentration and position-sizer tabs both need the current live positions
and a cached portfolio summary. They live here so both tabs share one cache
entry rather than computing the summary twice.
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from app.domain.positions import LivePosition, PortfolioSummary
from app.services.valuation import compute_portfolio_summary, get_live_positions_cached
from app.ui.wiring import get_live_fx_provider, get_price_provider, get_repository


def _get_live_positions() -> dict[str, LivePosition]:
    return get_live_positions_cached(
        repo=get_repository(),
        price_provider=get_price_provider(),
        fx_provider=get_live_fx_provider(),
        as_of=date.today(),
    )


@st.cache_data(ttl=60, show_spinner=False)
def _cached_concentration_summary(tx_sig: str, as_of_iso: str) -> PortfolioSummary:
    live_positions = _get_live_positions()
    return compute_portfolio_summary(live_positions, datetime.fromisoformat(as_of_iso))
