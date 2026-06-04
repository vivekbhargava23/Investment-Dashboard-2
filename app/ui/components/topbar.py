import textwrap
from datetime import datetime

import streamlit as st

from app.domain.money import Currency
from app.services.market_data import clear_market_data_caches
from app.ui.components.ticker_searchbox import render_ticker_searchbox
from app.ui.focus import get_focus_ticker, set_focus_ticker
from app.ui.wiring import get_live_fx_provider, get_ohlc_data_provider, get_ticker_resolver

PAGE_TITLES: dict[str, str] = {
    "overview": "Live Overview",
    "analytics": "Analytics & Risk",
    "tax": "Tax Dashboard",
    "company": "Company Deep Dive",
    "simulator": "Sell Simulator",
    "manage": "Manage Portfolio",
    "mappings": "ISIN Mappings",
    "import_workbench": "Import CSV",
}

def _handle_refresh() -> None:
    clear_market_data_caches(get_ohlc_data_provider())
    st.cache_data.clear()
    st.rerun()

def render_topbar() -> None:
    current_page = st.session_state.get("current_page", "overview")
    title = PAGE_TITLES.get(current_page, "Investment Panel")

    try:
        rate = get_live_fx_provider().get_current_rate(Currency.EUR, Currency.USD)
        fx_str = f"{rate:.4f}"
    except Exception:
        fx_str = "—"

    time_str = datetime.now().strftime("%H:%M")

    col_title, col_focus, col_refresh = st.columns([0.45, 0.40, 0.15])

    with col_title:
        st.markdown(textwrap.dedent(f"""
            <div class="topbar-left">
                <h1>{title}</h1>
                <div class="topbar-meta">USD/EUR {fx_str} · {time_str}</div>
            </div>
        """).strip(), unsafe_allow_html=True)

    with col_focus:
        resolver = get_ticker_resolver()
        focus_sym = get_focus_ticker()
        default_match = resolver.lookup(focus_sym) if focus_sym else None
        match = render_ticker_searchbox(
            "topbar_focus_ticker",
            resolver,
            placeholder="Focus ticker…",
            default_match=default_match,
        )
        if match is not None:
            set_focus_ticker(match.symbol)

    with col_refresh:
        if st.button(  # noqa: E501
            "Refresh", key="topbar_refresh", use_container_width=True, on_click=_handle_refresh
        ):
            pass
