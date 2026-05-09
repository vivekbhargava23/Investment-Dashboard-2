"""Shared period radio-selector for chart pages (Research, Technicals)."""

from __future__ import annotations

import streamlit as st

from app.domain.market_data import ChartPeriod

_PERIOD_LABELS: dict[ChartPeriod, str] = {
    ChartPeriod.ONE_DAY: "1D",
    ChartPeriod.FIVE_DAY: "5D",
    ChartPeriod.ONE_MONTH: "1M",
    ChartPeriod.THREE_MONTH: "3M",
    ChartPeriod.SIX_MONTH: "6M",
    ChartPeriod.ONE_YEAR: "1Y",
    ChartPeriod.TWO_YEAR: "2Y",
    ChartPeriod.FIVE_YEAR: "5Y",
    ChartPeriod.YEAR_TO_DATE: "YTD",
}

# Subset used by the Technicals tab (no intraday or YTD)
TECHNICALS_PERIODS: list[ChartPeriod] = [
    ChartPeriod.ONE_MONTH,
    ChartPeriod.THREE_MONTH,
    ChartPeriod.SIX_MONTH,
    ChartPeriod.ONE_YEAR,
    ChartPeriod.TWO_YEAR,
    ChartPeriod.FIVE_YEAR,
]


def render_period_selector(
    key: str,
    *,
    options: list[ChartPeriod] | None = None,
    default: str = "6M",
) -> ChartPeriod:
    """Render a horizontal period radio and return the selected ChartPeriod.

    options: ordered list of ChartPeriod values to display; defaults to all periods.
    default: the label string (e.g. "6M") to pre-select.
    """
    period_options = options if options is not None else list(_PERIOD_LABELS.keys())

    default_period = next(
        (p for p in period_options if _PERIOD_LABELS.get(p) == default),
        period_options[0],
    )
    default_index = period_options.index(default_period)

    selected: ChartPeriod = st.radio(
        "Period",
        options=period_options,
        horizontal=True,
        key=key,
        index=default_index,
        format_func=lambda p: _PERIOD_LABELS[p],
        label_visibility="collapsed",
    )
    return selected
