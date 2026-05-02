"""
app/ui/components/performance_chart.py

Plotly chart renderers for the Performance page.

Portfolio chart:   filled area line — total EUR value over time.
Position chart:    price line in native currency + green dot buy markers +
                   red dot sell markers (when disposal records are available).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.core.position import Position
from app.services.price_service import get_currency
from app.utils.formatting import fmt_currency


_CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=0, r=0, t=32, b=0),
    hovermode="x unified",
    xaxis=dict(showgrid=False, zeroline=False),
    yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.15)", zeroline=False),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
)

_CURRENCY_SYMBOL = {"EUR": "€", "USD": "$", "JPY": "¥"}


def render_portfolio(history: pd.Series, period: str) -> None:
    """
    Render the portfolio total value chart as a filled area line in EUR.

    Args:
        history: pd.Series indexed by Timestamp, values in EUR.
        period:  Selected period label shown in the caption.
    """
    if history.empty:
        st.info("No price history available for this period. Markets may be closed.")
        return

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=history.index,
        y=history.values,
        mode="lines",
        name="Portfolio (€)",
        line=dict(color="#2196F3", width=2),
        fill="tozeroy",
        fillcolor="rgba(33, 150, 243, 0.10)",
        hovertemplate="<b>%{x|%d %b %Y}</b><br>€%{y:,.0f}<extra></extra>",
    ))

    start_val = history.iloc[0]
    end_val = history.iloc[-1]
    change = end_val - start_val
    change_pct = change / start_val * 100 if start_val else 0
    sign = "+" if change >= 0 else ""

    fig.update_layout(
        **_CHART_LAYOUT,
        title=dict(
            text=f"Portfolio Value (EUR) — {period}  "
                 f"<span style='font-size:14px;color:{'#4CAF50' if change >= 0 else '#F44336'}'>"
                 f"{sign}{fmt_currency(change, symbol='€', show_sign=True)} "
                 f"({sign}{change_pct:.1f}%)</span>",
            font=dict(size=16),
        ),
        yaxis_tickprefix="€",
        yaxis_tickformat=",.0f",
    )

    st.plotly_chart(fig, use_container_width=True)


def render_position(
    position: Position,
    history: pd.Series,
    period: str,
) -> None:
    """
    Render a single position's price history with buy and sell markers.

    Buy lots  → green ▲ triangle-up markers.
    Sell lots → orange ▼ triangle-down markers (derived from position.sell_lots).

    Args:
        position: Position object (for name, lots, currency).
        history:  pd.Series of Close prices indexed by Timestamp.
        period:   Selected period label.
    """
    if history.empty:
        st.info(f"No price history available for {position.ticker} in the {period} window.")
        return

    ccy = get_currency(position.ticker)
    sym = _CURRENCY_SYMBOL.get(ccy, ccy)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=history.index,
        y=history.values,
        mode="lines",
        name=position.ticker,
        line=dict(color="#FF9800", width=2),
        hovertemplate=f"<b>%{{x|%d %b %Y}}</b><br>{sym}%{{y:,.2f}}<extra></extra>",
    ))

    chart_start = history.index[0]
    chart_end = history.index[-1]

    def _snap(tx_date: date) -> tuple[pd.Timestamp, float] | None:
        """Return (snapped_ts, price) for tx_date, or None if outside chart range."""
        ts = pd.Timestamp(tx_date)
        if ts < chart_start or ts > chart_end:
            return None
        available = history[history.index <= ts]
        if available.empty:
            available = history[history.index >= ts]
        if available.empty:
            return None
        return available.index[-1], float(available.iloc[-1])

    # Buy markers — green ▲
    buy_x, buy_y, buy_text = [], [], []
    for txn in sorted(position.transactions, key=lambda t: t.trade_date):
        if txn.trade_type.upper() != "BUY":
            continue
        snapped = _snap(txn.trade_date)
        if snapped:
            buy_x.append(snapped[0])
            buy_y.append(snapped[1])
            buy_text.append(
                f"BUY {txn.shares:g} × {sym}{txn.price:,.2f}"
                f"<br>{txn.trade_date.strftime('%d %b %Y')}"
            )

    if buy_x:
        fig.add_trace(go.Scatter(
            x=buy_x, y=buy_y, mode="markers", name="Bought", showlegend=False,
            marker=dict(color="#4CAF50", size=20, symbol="triangle-up",
                        line=dict(color="white", width=1.5)),
            hovertemplate="<b>%{text}</b><extra></extra>",
            text=buy_text,
        ))

    # Sell markers — red ▼
    sell_x, sell_y, sell_text = [], [], []
    for txn in sorted(position.transactions, key=lambda t: t.trade_date):
        if txn.trade_type.upper() != "SELL":
            continue
        snapped = _snap(txn.trade_date)
        if snapped:
            sell_x.append(snapped[0])
            sell_y.append(snapped[1])
            sell_text.append(
                f"SELL {txn.shares:g} × {sym}{txn.price:,.2f}"
                f"<br>{txn.trade_date.strftime('%d %b %Y')}"
            )

    if sell_x:
        fig.add_trace(go.Scatter(
            x=sell_x, y=sell_y, mode="markers", name="Sold", showlegend=False,
            marker=dict(color="#F44336", size=20, symbol="triangle-down",
                        line=dict(color="white", width=1.5)),
            hovertemplate="<b>%{text}</b><extra></extra>",
            text=sell_text,
        ))

    fig.update_layout(
        **_CHART_LAYOUT,
        showlegend=False,
        title=dict(
            text=f"{position.name} ({position.ticker}) — {period} · {ccy}",
            font=dict(size=16),
        ),
        yaxis_tickprefix=sym,
        yaxis_tickformat=",.2f",
    )
    # Force X-axis to the full data range
    fig.update_xaxes(range=[chart_start, chart_end])

    st.plotly_chart(fig, use_container_width=True)

    if position.has_live_price:
        avg = position.average_cost
        live = position.live_price
        diff = (live - avg) / avg * 100 if avg else 0
        sign = "+" if diff >= 0 else ""
        st.caption(
            f"Avg cost {sym}{avg:,.2f} · Live {sym}{live:,.2f} · "
            f"{sign}{diff:.1f}% vs avg cost"
        )
