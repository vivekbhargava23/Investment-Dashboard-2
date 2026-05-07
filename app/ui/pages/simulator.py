"""Pre-trade Sell Simulator page."""

from __future__ import annotations

import streamlit as st

from app.ui.components.sell_simulator import render_sell_simulator
from app.ui.render import render_html


def render() -> None:
    render_html("""
        <div style="font-size: 22px; font-weight: 700; color: var(--text); margin-bottom: 4px;">
            Pre-trade Sell Simulator
        </div>
        <div style="font-size: 13px; color: var(--text3); margin-bottom: 20px;">
            Preview the FIFO lot consumption, realised gain, and marginal tax impact of a
            hypothetical sell before recording it.
        </div>
    """)

    # Pre-fill ticker from session state (set by "Simulate sell" links on other pages)
    default_ticker: str | None = None
    if "simulator_default_ticker" in st.session_state:
        default_ticker = st.session_state.pop("simulator_default_ticker")

    # Also accept ticker from URL query params (from HTML table links)
    if default_ticker is None and "ticker" in st.query_params:
        default_ticker = st.query_params["ticker"]
        del st.query_params["ticker"]

    render_sell_simulator(default_ticker=default_ticker)
