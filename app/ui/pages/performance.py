"""
app/ui/pages/performance.py

Performance charts page: portfolio value over time and individual position charts.
History is reconstructed from lot data and yfinance OHLCV prices.
"""

from __future__ import annotations

from datetime import date
import pandas as pd
import streamlit as st

from app.config.settings import get_settings
from app.core.portfolio import Portfolio
from app.data.repository import load_portfolio
from app.services.history_service import (
    PERIODS,
    get_portfolio_value_history,
    get_ticker_history,
)
from app.services.price_service import inject_prices
from app.ui.components import performance_chart

_settings = get_settings()


@st.cache_data(ttl=_settings.price_refresh_interval_seconds, show_spinner=False)
def _load_priced_portfolio() -> Portfolio:
    return inject_prices(load_portfolio())


@st.cache_data(ttl=300, show_spinner=False)
def _portfolio_history(period: str) -> pd.Series:
    """Cached portfolio value reconstruction. Period is the only cache key."""
    return get_portfolio_value_history(load_portfolio(), period)


@st.cache_data(ttl=300, show_spinner=False)
def _position_history(ticker: str, period: str, start: date | None = None) -> pd.Series:
    return get_ticker_history(ticker, period, start=start)


def render() -> None:
    """Render the Performance page."""
    st.title("Performance")

    # ── Period selector ───────────────────────────────────────────────────
    period = st.radio(
        "Period",
        options=PERIODS,
        index=PERIODS.index("1M"),
        horizontal=True,
        label_visibility="collapsed",
    )

    # ── Portfolio value chart ─────────────────────────────────────────────
    with st.spinner("Loading price history…"):
        pv_history = _portfolio_history(period)

    performance_chart.render_portfolio(pv_history, period)

    st.divider()

    # ── Individual position chart ─────────────────────────────────────────
    portfolio = _load_priced_portfolio()

    options = [pos.ticker for pos in portfolio.positions]
    selected = st.selectbox(
        "Position",
        options=options,
        format_func=lambda t: f"{t} — {portfolio.get_position(t).name}",  # type: ignore[union-attr]
    )

    position = portfolio.get_position(selected)
    if position is None:
        return

    from datetime import timedelta
    pos_start = (
        min(t.trade_date for t in position.transactions) - timedelta(days=7)
        if period == "MAX" and position.transactions else None
    )

    with st.spinner(f"Loading {selected} history…"):
        pos_history = _position_history(selected, period, start=pos_start)

    performance_chart.render_position(position, pos_history, period)

    # ── Refresh ───────────────────────────────────────────────────────────
    st.caption(f"Prices refresh automatically every {_settings.price_refresh_interval_seconds}s.")
    if st.button("↺ Refresh now"):
        from app.utils.cache import clear_all
        clear_all()
        st.rerun()
