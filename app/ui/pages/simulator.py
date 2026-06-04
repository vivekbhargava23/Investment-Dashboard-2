"""Pre-trade Sell Simulator page."""

from __future__ import annotations

import streamlit as st

from app.ui.components.sell_simulator import render_sell_simulator
from app.ui.render import render_html


def render() -> None:
    render_html("""
        <div style="font-size: 13px; color: var(--text3); margin-bottom: 20px;">
            Preview the FIFO lot consumption, realised gain, and marginal tax impact of a
            hypothetical sell before recording it.
        </div>
    """)

    # Pre-fill ticker from session state (set by "Simulate sell" links on other pages)
    default_ticker: str | None = None
    if "simulator_default_ticker" in st.session_state:
        default_ticker = st.session_state.pop("simulator_default_ticker")

    # Also accept ticker from URL query params (from HTML table links). This uses
    # its own sim_ticker= param, kept separate from the global focus ticker=
    # param (TICKET-RD0) so the two never clobber each other.
    if default_ticker is None and "sim_ticker" in st.query_params:
        default_ticker = st.query_params["sim_ticker"]
        del st.query_params["sim_ticker"]

    render_sell_simulator(default_ticker=default_ticker)
