"""Analytics & Risk page shell: caption + tab routing.

Each of the five tabs lives in its own module and exposes ``render()``. This
shell owns only the layout — no computation.
"""

from __future__ import annotations

import streamlit as st

from app.ui.pages.analytics import (
    concentration,
    correlation,
    performance,
    sizer,
    technicals,
)


def render() -> None:
    st.caption(
        "Five lenses on your portfolio: performance, correlation, technicals,"
        " position sizing, concentration."
    )

    tab_labels = [
        "Performance",
        "Correlation",
        "Technicals",
        "Position Sizer",
        "Concentration",
    ]
    perf_tab, corr_tab, tech_tab, sizing_tab, conc_tab = st.tabs(
        tab_labels,
        key="analytics_tabs",
        default="Performance",
    )

    with perf_tab:
        performance.render()
    with corr_tab:
        correlation.render()
    with tech_tab:
        technicals.render()
    with sizing_tab:
        sizer.render()
    with conc_tab:
        concentration.render()
