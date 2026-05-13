import textwrap
from datetime import datetime

import streamlit as st

from app.domain.money import Currency
from app.services.valuation import clear_caches
from app.ui.wiring import get_fx_provider, get_price_provider

PAGE_TITLES: dict[str, str] = {
    "overview": "Live Overview",
    "analytics": "Analytics & Risk",
    "performance": "Performance",
    "tax": "Tax Dashboard",
    "research": "Research",
    "company": "Company Deep Dive",
    "decision": "Decision Gates",
    "behaviour": "Behavioural Ledger",
    "lots": "Lot Ledger",
    "simulator": "Sell Simulator",
    "manage": "Manage Portfolio",
}

def _handle_refresh() -> None:
    clear_caches(get_price_provider(), get_fx_provider())
    st.cache_data.clear()
    st.rerun()

def render_topbar() -> None:
    current_page = st.session_state.get("current_page", "overview")
    title = PAGE_TITLES.get(current_page, "Investment Panel")
    
    try:
        rate = get_fx_provider().get_current_rate(Currency.EUR, Currency.USD)
        fx_str = f"{rate:.4f}"
    except Exception:
        fx_str = "—"
        
    time_str = datetime.now().strftime("%H:%M")
    
    # We use columns to allow a Streamlit button for the Refresh action
    # while keeping the layout consistent with the mockup.
    col1, col2 = st.columns([0.8, 0.2])
    
    with col1:
        st.markdown(textwrap.dedent(f"""
            <div class="topbar-left">
                <h1>{title}</h1>
                <div class="topbar-meta">USD/EUR {fx_str} · {time_str}</div>
            </div>
        """).strip(), unsafe_allow_html=True)
    
    with col2:
        if st.button("Refresh", key="topbar_refresh", use_container_width=False, on_click=_handle_refresh):  # noqa: E501
            pass
