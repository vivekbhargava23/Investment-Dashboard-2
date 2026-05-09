"""Analytics page — five-tab shell. Tab bodies are filled in by TICKET-A1 through A5."""

import streamlit as st


def render() -> None:
    st.markdown("# 📊 Analytics")
    st.caption(
        "Five lenses on your portfolio: performance, correlation, technicals,"
        " position sizing, concentration."
    )

    perf_tab, corr_tab, tech_tab, sizing_tab, conc_tab = st.tabs(
        ["Performance", "Correlation", "Technicals", "Position Sizer", "Concentration"]
    )

    with perf_tab:
        st.info("Coming in TICKET-A1")
    with corr_tab:
        st.info("Coming in TICKET-A2")
    with tech_tab:
        st.info("Coming in TICKET-A3")
    with sizing_tab:
        st.info("Coming in TICKET-A4")
    with conc_tab:
        st.info("Coming in TICKET-A5")
