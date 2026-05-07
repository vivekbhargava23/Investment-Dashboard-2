from __future__ import annotations

from decimal import Decimal

import streamlit as st

from app.domain.market_data import ChartPeriod, OhlcSeries, OhlcUnavailableError
from app.domain.money import Currency
from app.domain.tickers import UnsupportedTickerError, infer_currency_from_ticker
from app.ports.ticker_resolver import TickerMatch
from app.services.market_data import get_ohlc_history
from app.ui.components.charts import render_candlestick
from app.ui.components.ticker_searchbox import render_ticker_searchbox
from app.ui.wiring import get_ohlc_data_provider, get_repository, get_ticker_resolver

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


def _period_label(period: ChartPeriod) -> str:
    return _PERIOD_LABELS[period]


def _format_price(value: Decimal, currency: Currency) -> str:
    if currency == Currency.EUR:
        return f"€{value:,.2f}"
    if currency == Currency.JPY:
        return f"¥{value:,.0f}"
    return f"${value:,.2f}"


def _format_change(value: Decimal | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


@st.cache_data(ttl=15 * 60, show_spinner=False)
def _cached_research_series(ticker: str, period_value: str) -> OhlcSeries:
    """Small UI cache for prompt period switching on top of the shared service cache."""
    period = ChartPeriod(period_value)
    return get_ohlc_history(ticker, period, provider=get_ohlc_data_provider())


def _render_metrics(series: OhlcSeries) -> None:
    latest_col, change_col, period_col = st.columns(3)
    with latest_col:
        st.metric("Latest", _format_price(series.latest_close, series.currency))
    with change_col:
        st.metric(
            "Period change",
            _format_change(series.period_change_pct),
            delta=_format_change(series.period_change_pct),
            delta_color="normal",
        )
    with period_col:
        st.metric("Period", _period_label(series.period))


def _render_header(match: TickerMatch) -> None:
    st.markdown(f"### {match.symbol} — {match.name}")
    st.caption(f"{match.exchange} • {match.currency.value}")


def _render_actions(match: TickerMatch) -> None:
    col1, col2, _ = st.columns([1, 1, 3])
    with col1:
        st.button(
            "Simulate buy",
            disabled=True,
            help="Buy simulation is not available yet; the current simulator is sell-only.",
        )
    with col2:
        st.button(
            "+ Add to watchlist",
            disabled=True,
            help="Watchlist coming in a future ticket",
        )


def _portfolio_tickers() -> tuple[str, ...]:
    transactions = get_repository().load_all()
    seen: set[str] = set()
    tickers: list[str] = []
    for tx in transactions:
        ticker = tx.ticker.strip().upper()
        if ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    return tuple(tickers)


def _fallback_match(ticker: str) -> TickerMatch | None:
    try:
        currency = infer_currency_from_ticker(ticker)
    except UnsupportedTickerError:
        return None
    return TickerMatch(symbol=ticker, name=ticker, exchange="", currency=currency)


def _portfolio_matches() -> tuple[TickerMatch, ...]:
    resolver = get_ticker_resolver()
    matches: list[TickerMatch] = []
    for ticker in _portfolio_tickers():
        match = resolver.lookup(ticker) or _fallback_match(ticker)
        if match is not None:
            matches.append(match)
    return tuple(matches)


def render() -> None:
    st.markdown("# 📈 Research")
    st.caption("Type any ticker to see its chart, regardless of whether you own it.")

    resolver = get_ticker_resolver()
    portfolio_matches = _portfolio_matches()
    default_match = st.session_state.get("research_selected_match")
    if not isinstance(default_match, TickerMatch):
        default_match = None

    search_col, period_col = st.columns([0.7, 0.3])
    with search_col:
        match = render_ticker_searchbox(
            key="research_ticker",
            resolver=resolver,
            placeholder="Type a ticker or company name...",
            default_match=default_match,
            pinned_matches=portfolio_matches,
        )
    with period_col:
        periods = list(ChartPeriod)
        period = st.radio(
            "Period",
            options=periods,
            horizontal=True,
            key="research_period",
            index=periods.index(ChartPeriod.SIX_MONTH),
            format_func=_period_label,
        )

    if match is not None:
        st.session_state["research_selected_match"] = match
    else:
        match = default_match

    if match is None:
        st.info("Type a ticker symbol or company name above to begin.")
        return

    _render_header(match)

    try:
        series = _cached_research_series(match.symbol, period.value)
    except OhlcUnavailableError as exc:
        st.warning(f"Chart unavailable: {exc.reason}")
        _render_actions(match)
        return

    _render_metrics(series)
    render_candlestick(series, height=500)
    _render_actions(match)
