"""
app/ui/pages/overview.py

Live Position Overview page.
Loads portfolio, injects live prices (cached 60s), renders summary + table.
"""

from __future__ import annotations

import streamlit as st

from app.config.settings import get_settings
from app.core.portfolio import Portfolio
from app.core.tax import TaxYear
from app.data.repository import load_portfolio, load_tax_year
from app.services.price_service import inject_prices
from app.ui.components import position_table, summary_bar

_settings = get_settings()


@st.cache_data(ttl=_settings.price_refresh_interval_seconds, show_spinner=False)
def _load_priced_portfolio() -> Portfolio:
    """Fetch live prices for all positions. Cached for price_refresh_interval_seconds."""
    return inject_prices(load_portfolio())


@st.cache_data(ttl=300, show_spinner=False)
def _load_tax_year() -> TaxYear | None:
    return load_tax_year()


def render() -> None:
    """Render the Live Position Overview page."""
    st.title("Live Position Overview")

    with st.spinner("Fetching live prices…"):
        portfolio = _load_priced_portfolio()

    tax_year = _load_tax_year()

    # ── summary strip ──────────────────────────────────────────────────────
    summary_bar.render(portfolio, tax_year)

    # ── position table ─────────────────────────────────────────────────────
    st.subheader("Positions")
    position_table.render(portfolio)

    # ── manual refresh ─────────────────────────────────────────────────────
    st.caption(f"Prices refresh automatically every {_settings.price_refresh_interval_seconds}s.")
    if st.button("↺ Refresh now"):
        from app.utils.cache import clear_all
        clear_all()
        st.rerun()
