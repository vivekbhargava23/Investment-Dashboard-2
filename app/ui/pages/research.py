"""Research page — chart any ticker, owned or not."""

from __future__ import annotations

from decimal import Decimal

import streamlit as st

from app.domain.market_data import ChartPeriod, OhlcUnavailableError
from app.ports.ticker_resolver import TickerMatch
from app.services.market_data import get_ohlc_history
from app.ui.components.charts import render_candlestick
from app.ui.components.ticker_searchbox import render_ticker_searchbox
from app.ui.wiring import get_ohlc_data_provider, get_ticker_resolver

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

_EXAMPLE_TICKERS = ["AAPL", "NVDA", "RHM.DE", "5631.T", "VWCE.DE"]


def _format_price(amount: Decimal, currency_symbol: str) -> str:
    return f"{currency_symbol} {float(amount):,.2f}"


def render() -> None:
    st.markdown("# 📈 Research")
    st.caption("Type any ticker to see its chart, regardless of whether you own it.")

    resolver = get_ticker_resolver()
    ohlc_provider = get_ohlc_data_provider()

    # ── Input row ────────────────────────────────────────────────────────────
    col_search, col_period = st.columns([0.7, 0.3])
    with col_search:
        match: TickerMatch | None = render_ticker_searchbox(
            key="research_ticker", resolver=resolver
        )
    with col_period:
        period: ChartPeriod = st.radio(
            "Period",
            options=list(ChartPeriod),
            horizontal=True,
            key="research_period",
            index=4,
            format_func=lambda p: _PERIOD_LABELS[p],
            label_visibility="collapsed",
        )

    # ── Empty state ───────────────────────────────────────────────────────────
    if match is None:
        st.info("Type a ticker symbol or company name above to begin.")
        st.markdown("**Quick picks:**")
        cols = st.columns(len(_EXAMPLE_TICKERS))
        for col, symbol in zip(cols, _EXAMPLE_TICKERS):
            with col:
                if st.button(symbol, key=f"quick_{symbol}"):
                    found = resolver.lookup(symbol)
                    if found is not None:
                        label = (
                            f"{found.symbol} — {found.name}"
                            f" ({found.exchange}, {found.currency.value})"
                        )
                        st.session_state["research_ticker"] = (label, found)
                        st.rerun()
        return

    # ── Fetch OHLC ────────────────────────────────────────────────────────────
    series = None
    fetch_error: str | None = None
    try:
        series = get_ohlc_history(match.symbol, period, provider=ohlc_provider)
    except OhlcUnavailableError as e:
        fetch_error = e.reason

    # ── Header region ─────────────────────────────────────────────────────────
    st.markdown(f"### {match.symbol} — {match.name}")
    st.caption(f"{match.exchange} • {match.currency.value}")

    if series is not None:
        pct = series.period_change_pct
        pct_str = (
            f"+{float(pct):.2f}%" if pct is not None and pct >= Decimal("0")
            else f"{float(pct):.2f}%" if pct is not None
            else "—"
        )
        m1, m2, m3 = st.columns(3)
        m1.metric("Latest", _format_price(series.latest_close, series.currency.value))
        m2.metric(
            "Period change",
            pct_str,
            delta=pct_str,
            delta_color="normal",
        )
        m3.metric("Period", _PERIOD_LABELS[period])

    # ── Chart region ──────────────────────────────────────────────────────────
    if fetch_error is not None:
        st.warning(f"Chart unavailable: {fetch_error}")
    elif series is not None:
        render_candlestick(series, height=500)

    # ── Action row ────────────────────────────────────────────────────────────
    col1, col2, _ = st.columns([1, 1, 3])
    with col1:
        # TICKET-012 is merged; enable simulate-buy handoff via the sell simulator
        if st.button("Simulate buy", key="research_simulate_buy"):
            st.session_state["simulator_default_ticker"] = match.symbol
            st.session_state["current_page"] = "simulator"
            st.query_params["page"] = "simulator"
            st.rerun()
    with col2:
        st.button(
            "+ Add to watchlist",
            key="research_watchlist",
            disabled=True,
            help="Watchlist coming in a future ticket",
        )

    # TODO(TICKET-022c): 52w high/low from Ticker.info
