"""Position Sizer tab of the Analytics & Risk page."""

from __future__ import annotations

import html
from datetime import datetime
from decimal import Decimal
from typing import Literal, cast

import streamlit as st

from app.domain.analytics_views import SizerView
from app.services.analytics_sizer import (
    BAR_SCALE_MAX_PCT as SIZER_BAR_SCALE_MAX_PCT,
)
from app.services.analytics_sizer import (
    DEFAULT_RISK_PCT,
    DEFAULT_STOP_PCT,
    DEFAULT_TARGET_WEIGHT_PCT,
    compute_sizer_view,
)
from app.services.analytics_sizer import (
    MAX_POSITION_WEIGHT_PCT as SIZER_MAX_POSITION_WEIGHT_PCT,
)
from app.ui.cache_keys import transactions_signature
from app.ui.components.weight_bar import render_weight_bar
from app.ui.format import format_eur, format_pct, format_shares
from app.ui.pages.analytics._data import _cached_concentration_summary, _get_live_positions
from app.ui.render import render_html
from app.ui.wiring import get_repository

_SIZER_EMPTY_STATE = "No positions yet — add transactions in Manage Portfolio to enable sizing."


def render() -> None:
    transactions = get_repository().load_all()
    sig = transactions_signature(transactions)
    now_iso = datetime.now().isoformat()
    live_positions = _get_live_positions()
    if not live_positions:
        st.info(_SIZER_EMPTY_STATE)
        return

    summary = _cached_concentration_summary(sig, now_iso)
    sorted_tickers = sorted(live_positions)
    default_ticker = st.session_state.get("sizer_ticker", sorted_tickers[0])
    selected_index = (
        sorted_tickers.index(default_ticker) if default_ticker in sorted_tickers else 0
    )

    input_col, result_col = st.columns([1, 1])
    with input_col:
        selected_ticker = st.selectbox(
            "Ticker",
            sorted_tickers,
            index=selected_index,
            key="sizer_ticker",
        )
        direction = st.radio(
            "Direction",
            ["buy", "sell"],
            horizontal=True,
            key="sizer_direction",
            format_func=lambda value: str(value).title(),
        )
        risk_pct = Decimal(
            str(
                st.number_input(
                    "Risk %",
                    min_value=0.1,
                    max_value=5.0,
                    step=0.1,
                    value=float(DEFAULT_RISK_PCT),
                )
            )
        )
        stop_pct = Decimal(
            str(
                st.number_input(
                    "Stop Loss %",
                    min_value=1.0,
                    max_value=30.0,
                    step=0.5,
                    value=float(DEFAULT_STOP_PCT),
                )
            )
        )
        target_weight_pct = Decimal(
            str(
                st.number_input(
                    "Target Weight %",
                    min_value=1.0,
                    max_value=40.0,
                    step=0.5,
                    value=float(DEFAULT_TARGET_WEIGHT_PCT),
                )
            )
        )

        view = compute_sizer_view(
            positions=list(live_positions.values()),
            summary=summary,
            selected_ticker=str(selected_ticker),
            direction=cast(Literal["buy", "sell"], direction),
            risk_pct=risk_pct,
            stop_pct=stop_pct,
            target_weight_pct=target_weight_pct,
        )
        _render_current_position_card(view)

    with result_col:
        _render_sizer_view(view)


def _render_sizer_view(view: SizerView) -> None:
    if view.degraded_reason is not None:
        if view.risk_based is None:
            st.error(view.degraded_reason)
            return
        st.warning(view.degraded_reason)

    if (
        view.risk_based is None
        or view.weight_based is None
        or view.post_trade is None
    ):
        return

    render_html(_build_risk_result_card_html(view))
    render_html(_build_weight_result_card_html(view))
    render_html(_build_post_trade_preview_html(view))


def _render_current_position_card(view: SizerView) -> None:
    current = view.current
    status = current.staleness or "live"
    render_html(
        '<div class="metric-card">'
        '<div class="metric-label">Current Position</div>'
        f'<div class="metric-value">{html.escape(current.ticker)}</div>'
        '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; '
        'margin-top: 12px; font-size: 13px;">'
        f"<div>Weight<br><strong>{format_pct(current.weight_pct)}</strong></div>"
        f"<div>Value<br><strong>{format_eur(current.market_value_eur)}</strong></div>"
        f"<div>Last<br><strong>{html.escape(str(current.last_price_native))}</strong></div>"
        f"<div>EUR<br><strong>{format_eur(current.last_price_eur)}</strong></div>"
        f"<div>Lots<br><strong>{current.open_lot_count}</strong></div>"
        f"<div>Status<br><strong>{html.escape(status)}</strong></div>"
        "</div></div>"
    )


def _build_risk_result_card_html(view: SizerView) -> str:
    result = view.risk_based
    assert result is not None
    return (
        '<div class="metric-card" style="border-left: 3px solid var(--green);">'
        '<div class="metric-label">Method 1 — Risk-Based</div>'
        f'<div class="metric-value">{format_shares(result.shares)}</div>'
        f'<div class="metric-delta">Trade value {format_eur(result.trade_value_eur)}</div>'
        '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; '
        'margin-top: 12px; font-size: 13px;">'
        f"<div>Risk<br><strong>{format_eur(result.risk_eur)}</strong></div>"
        f"<div>Risk %<br><strong>{format_pct(result.risk_pct_input)}</strong></div>"
        f"<div>Stop<br><strong>{html.escape(str(result.stop_price_native))}</strong></div>"
        "</div></div>"
    )


def _build_weight_result_card_html(view: SizerView) -> str:
    result = view.weight_based
    assert result is not None
    return (
        '<div class="metric-card" style="border-left: 3px solid var(--blue);">'
        '<div class="metric-label">Method 2 — Weight-Based</div>'
        f'<div class="metric-value">{format_shares(result.shares)}</div>'
        f'<div class="metric-delta">Delta {format_eur(result.delta_eur, signed=True)}</div>'
        '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; '
        'margin-top: 12px; font-size: 13px;">'
        f"<div>Current<br><strong>{format_pct(result.current_weight_pct)}</strong></div>"
        f"<div>Target<br><strong>{format_pct(result.target_weight_pct)}</strong></div>"
        "</div></div>"
    )


def _build_post_trade_preview_html(view: SizerView) -> str:
    preview = view.post_trade
    assert preview is not None
    marker_pct = min(
        Decimal("100"),
        SIZER_MAX_POSITION_WEIGHT_PCT / SIZER_BAR_SCALE_MAX_PCT * Decimal("100"),
    )
    bar = render_weight_bar(
        preview.new_weight_pct,
        scale_max=SIZER_BAR_SCALE_MAX_PCT,
        danger_threshold=SIZER_MAX_POSITION_WEIGHT_PCT,
        label=format_pct(preview.new_weight_pct),
    )
    return (
        '<div class="metric-card">'
        '<div class="metric-label">New Weight After Method 1</div>'
        f'<div class="metric-value">{format_pct(preview.new_weight_pct)}</div>'
        f'<div class="metric-delta">Current {format_pct(preview.current_weight_pct)}</div>'
        '<div style="position: relative; margin-top: 12px;">'
        f"{bar}"
        f'<div title="35% cap" style="position: absolute; left: {marker_pct}%; '
        'top: 18px; width: 2px; height: 12px; background: var(--red);"></div>'
        "</div></div>"
    )
