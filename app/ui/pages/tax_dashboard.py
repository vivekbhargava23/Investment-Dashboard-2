"""
app/ui/pages/tax_dashboard.py

Tax Dashboard page: YTD Sparerpauschbetrag usage, realised P&L, loss pot,
total tax exposure, and harvest opportunity calculator.
"""

from __future__ import annotations

import streamlit as st

from app.config.settings import get_settings
from app.core.portfolio import Portfolio
from app.core.tax import TaxYear
from app.data.repository import load_portfolio, load_tax_year
from app.services.price_service import inject_prices
from app.ui.components import harvest_table, tax_summary

_settings = get_settings()


@st.cache_data(ttl=_settings.price_refresh_interval_seconds, show_spinner=False)
def _load_priced_portfolio() -> Portfolio:
    return inject_prices(load_portfolio())


@st.cache_data(ttl=300, show_spinner=False)
def _load_tax_year() -> TaxYear | None:
    return load_tax_year()


def render() -> None:
    """Render the Tax Dashboard page."""
    st.title("Tax Dashboard")

    tax_year = _load_tax_year()

    if tax_year is None:
        st.warning("No tax year data found — add a `tax_year` block to portfolio.json.")
        return

    with st.spinner("Fetching live prices…"):
        portfolio = _load_priced_portfolio()

    # ── YTD summary: allowance, realised P&L, loss pot ────────────────────
    tax_summary.render(tax_year)

    st.divider()

    # ── Total exposure + harvest table ────────────────────────────────────
    harvest_table.render(tax_year, portfolio)

    # ── Refresh ───────────────────────────────────────────────────────────
    st.caption(f"Prices refresh automatically every {_settings.price_refresh_interval_seconds}s.")
    if st.button("↺ Refresh now"):
        st.cache_data.clear()
        st.rerun()
