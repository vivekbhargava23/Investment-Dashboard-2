"""Correlation tab of the Analytics & Risk page."""

from __future__ import annotations

import html
from datetime import date
from decimal import Decimal

import streamlit as st

from app.services.analytics_correlation import (
    CLUSTER_THRESHOLD,
    CorrelationView,
    build_correlation_view,
    diversification_bucket,
)
from app.ui.components._chart_styles import CORRELATION_COLORSCALES
from app.ui.components.charts import render_correlation_heatmap
from app.ui.components.metric_card import render_metric_card
from app.ui.render import render_html
from app.ui.wiring import (
    get_live_fx_provider,
    get_ohlc_data_provider,
    get_price_provider,
    get_repository,
)

_CORRELATION_EMPTY_STATE = (
    "Need at least 2 positions with sufficient history to compute correlations."
)
_CORRELATION_HELP_TEXT = (
    "**Avg ρ** is the average pairwise correlation between this position and every "
    "other included position in the selected window. The diagonal "
    "self-correlation is excluded.\n\n"
    "— Lower or negative → moves more independently (stronger diversifier)  \n"
    "— Higher → moves with the rest of the portfolio (weaker diversifier)\n\n"
    "**Thresholds:** <0.20 high, <0.40 moderate, <0.60 low, >=0.60 very low."
)
_CORRELATION_COLORSCALE_DEFAULT = "Financial (red–neutral–green)"


def render() -> None:
    if "correlation_window" not in st.session_state:
        st.session_state["correlation_window"] = 30
    if (
        "correlation_color_scheme" not in st.session_state
        or st.session_state["correlation_color_scheme"] not in CORRELATION_COLORSCALES
    ):
        st.session_state["correlation_color_scheme"] = _CORRELATION_COLORSCALE_DEFAULT

    st.subheader("Pairwise correlation")
    window_days = st.radio(
        "Window",
        [30, 60, 90],
        horizontal=True,
        key="correlation_window",
        format_func=lambda value: f"{value}D",
    )

    view = build_correlation_view(
        repo=get_repository(),
        price_feed=get_price_provider(),
        fx_feed=get_live_fx_provider(),
        ohlc=get_ohlc_data_provider(),
        as_of=date.today(),
        window_days=int(window_days),
    )

    if len(view.included_tickers) >= 2:
        _render_correlation_kpis(view)

    _render_correlation_view(view)


def _render_correlation_kpis(view: CorrelationView) -> None:
    mean_corr = _mean_pairwise_correlation(view)
    max_pair = _max_correlation_pair(view)
    min_pair = _min_correlation_pair(view)
    cluster_count = len(view.clusters)

    cols = st.columns(4)
    with cols[0]:
        render_metric_card(
            "Mean ρ",
            f"{float(mean_corr):.4f}" if mean_corr is not None else "—",
            value_class=_corr_value_class(mean_corr),
            tooltip="Average pairwise correlation across included positions (diagonal excluded)",
        )
    with cols[1]:
        if max_pair:
            a, b, val = max_pair
            render_metric_card(
                "Highest Pair",
                f"{float(val):.2f}",
                sub_value=f"{a} · {b}",
                value_class="gain-negative" if val >= Decimal("0.6") else "gain-amber",
                tooltip=f"Most correlated pair in the portfolio: {a} ↔ {b}",
            )
        else:
            render_metric_card("Highest Pair", "—", value_class="gain-neutral")
    with cols[2]:
        if min_pair:
            a, b, val = min_pair
            render_metric_card(
                "Lowest Pair",
                f"{float(val):.2f}",
                sub_value=f"{a} · {b}",
                value_class="gain-positive" if val < Decimal("0.2") else "gain-neutral",
                tooltip=f"Least correlated pair in the portfolio: {a} ↔ {b}",
            )
        else:
            render_metric_card("Lowest Pair", "—", value_class="gain-neutral")
    with cols[3]:
        render_metric_card(
            "Clusters",
            "None" if cluster_count == 0 else str(cluster_count),
            value_class="gain-positive" if cluster_count == 0 else "gain-negative",
            tooltip=f"Groups of ≥3 positions with pairwise ρ > {CLUSTER_THRESHOLD}",
        )


def _render_correlation_view(
    view: CorrelationView,
    *,
    color_scheme: str | None = None,
) -> None:
    if view.skipped:
        skipped = "; ".join(
            f"{item.ticker} ({item.available_days} days available, "
            f"window requires {item.required_days})"
            for item in view.skipped
        )
        st.warning(f"Skipped: {skipped}")

    if len(view.included_tickers) < 2:
        st.info(_CORRELATION_EMPTY_STATE)
        return

    active_scheme = color_scheme if color_scheme is not None else st.session_state.get(
        "correlation_color_scheme", _CORRELATION_COLORSCALE_DEFAULT
    )
    render_correlation_heatmap(
        view.matrix,
        colorscale=_correlation_colorscale(active_scheme),
    )

    _, scheme_col = st.columns([10, 1])
    with scheme_col:
        with st.popover("🎨"):
            st.radio(
                "Color scheme",
                options=list(CORRELATION_COLORSCALES.keys()),
                key="correlation_color_scheme",
                label_visibility="collapsed",
            )

    heading_col, info_col = st.columns([10, 1])
    with heading_col:
        st.subheader("Average correlation to portfolio")
    with info_col:
        with st.popover("ⓘ", use_container_width=False):
            st.markdown(_CORRELATION_HELP_TEXT)

    _render_correlation_table(view)

    for cluster in view.clusters:
        members = ", ".join(cluster)
        st.warning(
            f"{len(cluster)} positions move together (avg corr > {CLUSTER_THRESHOLD}): "
            f"{members}. They may not be acting as independent diversifiers."
        )


def _build_correlation_table_html(view: CorrelationView) -> str:
    table_style = (
        "width: 100%; border-collapse: collapse; text-align: left; font-size: 13px;"
    )
    header_style = (
        "border-bottom: 1px solid var(--border); color: var(--text3); "
        "text-transform: uppercase; font-size: 10px; letter-spacing: 0.05em;"
    )
    rows: list[str] = []
    for ticker, avg_corr in sorted(
        view.avg_correlation.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        bucket_label, _ = diversification_bucket(avg_corr)
        css_class = bucket_label.replace(" ", "-")
        badge_html = (
            f'<span class="badge diversification-badge {css_class}">'
            f"{html.escape(bucket_label)}</span>"
        )
        corr_str = f"{float(avg_corr.quantize(Decimal('0.0001'))):.4f}"
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(ticker)}</strong></td>"
            f'<td class="font-mono text-right">{corr_str}</td>'
            f"<td>{badge_html}</td>"
            "</tr>"
        )
    return (
        '<div class="metric-card" style="padding: 0; overflow-x: auto;">'
        f'<table class="positions-table" style="{table_style}">'
        "<thead>"
        f'<tr style="{header_style}">'
        '<th style="padding: 8px 4px;">Ticker</th>'
        '<th style="padding: 8px 4px; text-align: right;">Avg ρ</th>'
        '<th style="padding: 8px 4px;">Diversification</th>'
        "</tr>"
        "</thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _render_correlation_table(view: CorrelationView) -> None:
    render_html(_build_correlation_table_html(view))


def _corr_value_class(corr: Decimal | None) -> str:
    if corr is None:
        return "gain-neutral"
    if corr < Decimal("0.2"):
        return "gain-positive"
    if corr < Decimal("0.6"):
        return "gain-amber"
    return "gain-negative"


def _mean_pairwise_correlation(view: CorrelationView) -> Decimal | None:
    tickers = view.included_tickers
    if len(tickers) < 2:
        return None
    vals: list[Decimal] = []
    for i, a in enumerate(tickers):
        for b in tickers[i + 1 :]:
            vals.append(view.matrix[a][b])
    return sum(vals, Decimal("0")) / Decimal(len(vals))


def _max_correlation_pair(view: CorrelationView) -> tuple[str, str, Decimal] | None:
    tickers = view.included_tickers
    if len(tickers) < 2:
        return None
    best: tuple[str, str, Decimal] | None = None
    for i, a in enumerate(tickers):
        for b in tickers[i + 1 :]:
            val = view.matrix[a][b]
            if best is None or val > best[2]:
                best = (a, b, val)
    return best


def _min_correlation_pair(view: CorrelationView) -> tuple[str, str, Decimal] | None:
    tickers = view.included_tickers
    if len(tickers) < 2:
        return None
    worst: tuple[str, str, Decimal] | None = None
    for i, a in enumerate(tickers):
        for b in tickers[i + 1 :]:
            val = view.matrix[a][b]
            if worst is None or val < worst[2]:
                worst = (a, b, val)
    return worst


def _correlation_colorscale(scheme: str | None) -> list[list[float | str]]:
    return CORRELATION_COLORSCALES.get(
        scheme or "",
        CORRELATION_COLORSCALES[_CORRELATION_COLORSCALE_DEFAULT],
    )
