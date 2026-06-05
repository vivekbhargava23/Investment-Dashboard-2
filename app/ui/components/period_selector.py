"""Shared period radio-selector and aggregation toggle for chart pages."""

from __future__ import annotations

import streamlit as st

from app.domain.market_data import AggregationFreq, ChartPeriod
from app.domain.returns import ALL_WINDOWS, ReturnWindow

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


def render_return_window_selector(key: str, *, default: str = "1M") -> ReturnWindow:
    """Render a horizontal radio over the RD9 return windows.

    The windows mirror the app-wide ``ChartPeriod`` labels (1D / 5D / 1M / 3M / 6M
    / 1Y / 2Y / 5Y / YTD), but ``ReturnWindow`` is a distinct close-to-close return
    metric anchored on ``as_of`` — so this is a dedicated selector rather than
    ``render_period_selector``. ``default`` is the label string (e.g. "1M") to
    pre-select.
    """
    options = list(ALL_WINDOWS)
    default_window = next((w for w in options if w.value == default), options[0])
    selected: ReturnWindow = st.radio(
        "Colour period",
        options=options,
        horizontal=True,
        key=key,
        index=options.index(default_window),
        format_func=lambda w: w.value,
        label_visibility="collapsed",
    )
    return selected


# Aggregation freqs available per period. Intraday periods (1D/5D) only support
# "Auto" because coarser weekly/monthly buckets add no value on 1-5 day charts.
_AVAILABLE_FREQS: dict[ChartPeriod, list[AggregationFreq]] = {
    ChartPeriod.ONE_DAY: [],
    ChartPeriod.FIVE_DAY: ["day"],
    ChartPeriod.ONE_MONTH: ["day", "week"],
    ChartPeriod.THREE_MONTH: ["day", "week"],
    ChartPeriod.SIX_MONTH: ["day", "week"],
    ChartPeriod.ONE_YEAR: ["day", "week"],
    ChartPeriod.TWO_YEAR: ["day", "week"],
    ChartPeriod.FIVE_YEAR: ["day", "week", "month"],
    ChartPeriod.YEAR_TO_DATE: ["day", "week", "month"],
}

_FREQ_LABELS: dict[AggregationFreq, str] = {
    "day": "Day",
    "week": "Week",
    "month": "Month",
}


def render_aggregation_toggle(key: str, period: ChartPeriod) -> AggregationFreq | None:
    """Render an aggregation toggle and return the selected freq or None for Auto.

    Options shown depend on the period; options that produce fewer than ~3 bars
    (or don't make sense for intraday data) are hidden.
    Returns None when "Auto" is selected (default behaviour).
    """
    available = _AVAILABLE_FREQS.get(period, [])
    options: list[AggregationFreq | None] = [None] + list(available)
    labels: dict[AggregationFreq | None, str] = {None: "Auto"}
    labels.update({f: _FREQ_LABELS[f] for f in available})

    selected: AggregationFreq | None = st.radio(
        "Aggregation",
        options=options,
        horizontal=True,
        key=key,
        index=0,
        format_func=lambda f: labels[f],
        label_visibility="collapsed",
    )
    return selected
