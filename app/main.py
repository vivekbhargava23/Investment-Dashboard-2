"""
app/main.py

Application entry point.
Run with: streamlit run app/main.py
"""

import streamlit as st

from app.config.settings import get_settings
from app.utils.logger import configure_logging

configure_logging()

_settings = get_settings()

st.set_page_config(
    page_title=_settings.app_title,
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="auto",
)

# Deferred imports — must follow set_page_config; pages use @st.cache_data at module scope
from app.ui.pages.lot_ledger import render as lot_ledger_render                  # noqa: E402
from app.ui.pages.manage_portfolio import render as manage_portfolio_render      # noqa: E402
from app.ui.pages.overview import render as overview_render                      # noqa: E402
from app.ui.pages.performance import render as performance_render                # noqa: E402
from app.ui.pages.tax_dashboard import render as tax_dashboard_render            # noqa: E402

pg = st.navigation([
    st.Page(overview_render,            title="Live Overview",       icon="📊", url_path="overview"),
    st.Page(lot_ledger_render,          title="Lot Ledger",          icon="📋", url_path="lot-ledger"),
    st.Page(tax_dashboard_render,       title="Tax Dashboard",       icon="🧾", url_path="tax"),
    st.Page(performance_render,         title="Performance",         icon="📈", url_path="performance"),
    st.Page(manage_portfolio_render,    title="Manage Portfolio",    icon="⚙️",  url_path="manage"),
])
pg.run()
