"""Concentration tab of the Analytics & Risk page.

The Herfindahl KPI is wired through ``render_explainable_metric`` (TICKET-RD4)
as the reference usage of the explain-this-number component: it shows the
formula and the actual per-position weights that feed the score.
"""

from __future__ import annotations

import html
from datetime import datetime
from decimal import Decimal

import streamlit as st

from app.domain.analytics_views import ConcentrationView
from app.services.analytics_concentration import (
    BAR_SCALE_MAX_PCT,
    HHI_GREEN_LT,
    HHI_RED_GTE,
    MAX_POSITION_WEIGHT_PCT,
    TOP_1_GREEN_LT_PCT,
    TOP_1_RED_GTE_PCT,
    TOP_3_GREEN_LT_PCT,
    TOP_3_RED_GTE_PCT,
    compute_concentration_view,
)
from app.ui.cache_keys import transactions_signature
from app.ui.components.charts import render_currency_donut, render_weight_bar_chart
from app.ui.components.explainable_metric import (
    ExplanationSpec,
    render_explainable_metric,
)
from app.ui.components.metric_card import render_metric_card
from app.ui.components.weight_bar import render_weight_bar
from app.ui.format import format_eur, format_pct
from app.ui.pages.analytics._data import _cached_concentration_summary, _get_live_positions
from app.ui.render import render_html
from app.ui.wiring import get_repository

_CONCENTRATION_EMPTY_STATE = "No positions yet — add transactions in Manage Portfolio."


def render() -> None:
    transactions = get_repository().load_all()
    sig = transactions_signature(transactions)
    now_iso = datetime.now().isoformat()
    live_positions = _get_live_positions()
    summary = _cached_concentration_summary(sig, now_iso)
    view = compute_concentration_view(list(live_positions.values()), summary)
    _render_concentration_view(view)


def _render_concentration_view(view: ConcentrationView) -> None:
    if not view.rows:
        st.info(_CONCENTRATION_EMPTY_STATE)
        return

    stale_count = sum(1 for row in view.rows if row.staleness_reason is not None)
    if stale_count:
        st.warning(
            f"{stale_count} positions have stale or missing data — affecting weights below"
        )

    _render_concentration_kpis(view)

    chart_col, donut_col = st.columns([1, 1])
    with chart_col:
        render_weight_bar_chart(
            view.weights_by_ticker,
            max_position_pct=MAX_POSITION_WEIGHT_PCT,
        )
    with donut_col:
        render_currency_donut(view.currency_split)

    render_html(_build_concentration_table_html(view))


def _render_concentration_kpis(view: ConcentrationView) -> None:
    cols = st.columns(3)
    with cols[0]:
        render_metric_card(
            "Top-1",
            format_pct(view.top_1_pct),
            value_class=_threshold_class(
                view.top_1_pct,
                green_lt=TOP_1_GREEN_LT_PCT,
                red_gte=TOP_1_RED_GTE_PCT,
            ),
            tooltip="Largest single position by current market value",
        )
    with cols[1]:
        render_metric_card(
            "Top-3",
            format_pct(view.top_3_pct),
            value_class=_threshold_class(
                view.top_3_pct,
                green_lt=TOP_3_GREEN_LT_PCT,
                red_gte=TOP_3_RED_GTE_PCT,
            ),
            tooltip="Combined weight of the three largest positions",
        )
    with cols[2]:
        render_explainable_metric(_herfindahl_explanation(view))


def _herfindahl_explanation(view: ConcentrationView) -> ExplanationSpec:
    """Build the explain-this-number spec for the Herfindahl (HHI) KPI.

    The component computes no finance math: it formats the score and the actual
    per-position weights the domain layer already produced.
    """
    value_str = str(view.herfindahl.quantize(Decimal("1")))
    inputs = {
        ticker: format_pct(weight_pct)
        for ticker, weight_pct in sorted(
            view.weights_by_ticker,
            key=lambda item: (-item[1], item[0]),
        )
    }
    return ExplanationSpec(
        label="Herfindahl",
        value_str=value_str,
        value_class=_threshold_class(
            view.herfindahl,
            green_lt=HHI_GREEN_LT,
            red_gte=HHI_RED_GTE,
        ),
        meaning="Concentration score on a 0–10000 scale (10000 = one holding).",
        formula=[
            "HHI = Σ (weightᵢ %)²",
            "over every open position i.",
        ],
        inputs=inputs,
        source_note=(
            "Weights use current market value. "
            f"Green < {int(HHI_GREEN_LT)}, red ≥ {int(HHI_RED_GTE)}."
        ),
    )


def _threshold_class(value: Decimal, *, green_lt: Decimal, red_gte: Decimal) -> str:
    if value < green_lt:
        return "gain-positive"
    if value >= red_gte:
        return "gain-negative"
    return "gain-amber"


def _build_concentration_table_html(view: ConcentrationView) -> str:
    rows: list[str] = []
    for row in view.rows:
        value = format_eur(row.value_eur, signed=False).replace("€", "")
        weight_bar = render_weight_bar(row.weight_pct, scale_max=BAR_SCALE_MAX_PCT)
        stale_label = (
            f'<span style="color: var(--text3);">{row.staleness_reason}</span>'
            if row.staleness_reason is not None
            else '<span class="gain-positive">live</span>'
        )
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(row.ticker)}</strong></td>"
            f'<td style="color: var(--text2);">{html.escape(row.name)}</td>'
            f'<td style="color: var(--text3);">{row.currency.value}</td>'
            f'<td class="font-mono text-right">{value}</td>'
            f'<td class="font-mono">{weight_bar}</td>'
            f'<td>{stale_label}</td>'
            "</tr>"
        )

    table_style = (
        "width: 100%; border-collapse: collapse; text-align: left; "
        "font-size: 13px;"
    )
    header_style = (
        "border-bottom: 1px solid var(--border); color: var(--text3); "
        "text-transform: uppercase; font-size: 10px; letter-spacing: 0.05em;"
    )
    return (
        '<div class="metric-card" style="padding: 0; overflow-x: auto;">'
        f'<table class="positions-table" style="{table_style}">'
        '<thead>'
        f'<tr style="{header_style}">'
        '<th style="padding: 8px 4px;">Ticker</th>'
        '<th style="padding: 8px 4px;">Name</th>'
        '<th style="padding: 8px 4px;">CCY</th>'
        '<th style="padding: 8px 4px; text-align: right;">Value (€)</th>'
        '<th style="padding: 8px 4px;">Weight</th>'
        '<th style="padding: 8px 4px;">Status</th>'
        "</tr>"
        "</thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )
