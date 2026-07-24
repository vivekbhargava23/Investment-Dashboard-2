"""Technicals tab of the Analytics & Risk page."""

from __future__ import annotations

from datetime import date

import streamlit as st

from app.services.analytics_technicals import (
    OhlcUnavailable,
    TechnicalsView,
    build_technicals_view,
)
from app.ui.components._chart_styles import SMA_50_STYLE, SMA_200_STYLE
from app.ui.components.charts import (
    Overlay,
    render_candlestick,
    render_rsi_panel,
)
from app.ui.components.period_selector import (
    TECHNICALS_PERIODS,
    render_aggregation_toggle,
    render_period_selector,
)
from app.ui.render import render_html
from app.ui.wiring import (
    get_ohlc_data_provider,
    get_price_provider,
    get_repository,
)

_TECHNICALS_EMPTY_STATE = (
    "No open positions to analyse. Add a position via Manage Portfolio."
)


def render() -> None:
    repo = get_repository()
    price_feed = get_price_provider()
    ohlc_provider = get_ohlc_data_provider()

    from app.domain.fifo import compute_positions as _compute_positions

    transactions = repo.load_all()
    positions = _compute_positions(transactions, date.today())
    open_tickers = sorted(t for t, p in positions.items() if p.open_shares > 0)

    if not open_tickers:
        st.info(_TECHNICALS_EMPTY_STATE)
        return

    default_ticker = st.session_state.get("technicals_ticker", open_tickers[0])
    if default_ticker not in open_tickers:
        default_ticker = open_tickers[0]

    selector_col, period_col, freq_col = st.columns([0.4, 0.4, 0.2])
    with selector_col:
        selected_ticker: str = st.selectbox(
            "Ticker",
            open_tickers,
            index=open_tickers.index(default_ticker),
            key="technicals_ticker",
        )
    with period_col:
        selected_period = render_period_selector(
            "technicals_period",
            options=TECHNICALS_PERIODS,
            default="6M",
        )
    with freq_col:
        selected_freq = render_aggregation_toggle("technicals_freq", selected_period)

    from app.ui.components.period_selector import _PERIOD_LABELS as _PL

    period_label = _PL.get(selected_period, "6M")

    try:
        view = build_technicals_view(
            ticker=str(selected_ticker),
            period=period_label,
            repo=repo,
            price_feed=price_feed,
            ohlc=ohlc_provider,
            as_of=date.today(),
            freq=selected_freq,
        )
    except OhlcUnavailable as exc:
        st.error(f"Could not fetch OHLC for {selected_ticker}: {exc.args[0]}")
        return
    except ValueError:
        st.info(_TECHNICALS_EMPTY_STATE)
        return

    _render_technicals_badges(view)
    _render_technicals_charts(view, freq=selected_freq)


def _render_technicals_badges(view: TechnicalsView) -> None:
    """Render the 5-badge strip: trend50, trend200, cross, RSI, live price."""
    hist = view.total_history_days

    # Badge 1: Trend 50 DMA
    if view.signals.trend_50 == "above":
        b1 = '<span class="badge badge-green">Above 50 DMA</span>'
    elif view.signals.trend_50 == "below":
        b1 = '<span class="badge badge-red">Below 50 DMA</span>'
    else:
        b1 = (
            f'<span class="badge badge-grey">'
            f"50 DMA: insufficient history ({hist} / 50)</span>"
        )

    # Badge 2: Trend 200 DMA
    if view.signals.trend_200 == "above":
        b2 = '<span class="badge badge-green">Above 200 DMA</span>'
    elif view.signals.trend_200 == "below":
        b2 = '<span class="badge badge-red">Below 200 DMA</span>'
    else:
        b2 = (
            f'<span class="badge badge-grey">'
            f"200 DMA: insufficient history ({hist} / 200)</span>"
        )

    # Badge 3: Cross
    cross = view.signals.cross
    days_ago = view.signals.cross_days_ago
    if cross == "golden":
        b3 = f'<span class="badge badge-green">Golden Cross ({days_ago}d ago)</span>'
    elif cross == "death":
        b3 = f'<span class="badge badge-red">Death Cross ({days_ago}d ago)</span>'
    elif cross == "none":
        b3 = '<span class="badge badge-grey">No recent cross</span>'
    else:
        b3 = '<span class="badge badge-grey">Cross: insufficient history</span>'

    # Badge 4: RSI
    rsi_level = view.signals.rsi_level
    rsi_val = view.signals.rsi_value
    if rsi_level == "overbought" and rsi_val is not None:
        b4 = f'<span class="badge badge-red">RSI {float(rsi_val):.0f} (overbought)</span>'
    elif rsi_level == "oversold" and rsi_val is not None:
        b4 = f'<span class="badge badge-green">RSI {float(rsi_val):.0f} (oversold)</span>'
    elif rsi_level == "neutral" and rsi_val is not None:
        b4 = f'<span class="badge badge-grey">RSI {float(rsi_val):.0f} (neutral)</span>'
    else:
        b4 = '<span class="badge badge-grey">RSI: insufficient history</span>'

    # Badge 5: Live price
    ccy = view.currency.value
    if view.live_price is None:
        b5 = '<span class="badge badge-grey">Live: unavailable</span>'
    elif view.signals.live_change_pct is not None:
        chg = float(view.signals.live_change_pct)
        sign = "+" if chg >= 0 else ""
        badge_cls = "badge-green" if chg >= 0 else "badge-red"
        b5 = (
            f'<span class="badge {badge_cls}">'
            f"Live: {ccy} {float(view.live_price):,.2f}"
            f" ({sign}{chg:.1f}%)</span>"
        )
    else:
        b5 = (
            f'<span class="badge badge-grey">'
            f"Live: {ccy} {float(view.live_price):,.2f} (—)</span>"
        )

    render_html(
        f'<div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px;">'
        f"{b1} {b2} {b3} {b4} {b5}"
        f"</div>"
    )


def _render_technicals_charts(view: TechnicalsView, *, freq: str | None = None) -> None:
    """Render the candlestick + overlay chart and the RSI panel."""
    from datetime import UTC
    from datetime import datetime as _dt

    from app.domain.market_data import OhlcSeries

    if not view.ohlc:
        st.info("No chart data available for this period.")
        return

    # Reconstruct OhlcSeries from the view's visible bars (needed by render_candlestick)
    from app.domain.market_data import ChartPeriod as _CP

    series = OhlcSeries(
        ticker=view.ticker,
        currency=view.currency,
        period=_CP.SIX_MONTH,  # period is cosmetic here (used for tick format)
        bars=tuple(view.ohlc),
        fetched_at=_dt.now(UTC),
    )

    # When using non-daily bars, the MA windows are in bars, not days
    ma_suffix = " DMA" if freq is None or freq == "day" else "-period MA"
    timestamps = [bar.timestamp for bar in view.ohlc]
    overlays: list[Overlay] = []
    if any(v is not None for v in view.sma_50):
        overlays.append(
            Overlay(name=f"50{ma_suffix}", x=timestamps, y=view.sma_50, style=SMA_50_STYLE)
        )
    if any(v is not None for v in view.sma_200):
        overlays.append(
            Overlay(name=f"200{ma_suffix}", x=timestamps, y=view.sma_200, style=SMA_200_STYLE)
        )

    st.markdown(f"**{view.ticker}** — candlestick + MA overlays")
    render_candlestick(series, height=400, overlays=overlays if overlays else None)

    if view.rsi is not None and view.rsi:
        rsi_dates = view.visible_dates[-len(view.rsi):]
        st.markdown("**RSI (14)**")
        render_rsi_panel(rsi_dates, view.rsi, height=120)
    else:
        st.caption(
            f"RSI: insufficient history "
            f"(need {14 + 1} days, have {view.total_history_days})"
        )
