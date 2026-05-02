"""
app/ui/components/summary_bar.py

Top-of-page summary strip: EUR portfolio totals and tax allowance status.

Row 1 — financial totals (EUR-converted via live FX rates):
    Total Portfolio Value  |  Total Unrealised Gain
Row 2 — portfolio metadata and tax state:
    Positions  |  Thesis Status  |  Sparerpauschbetrag  |  Tax Headroom
"""

from __future__ import annotations

import streamlit as st

from app.core.portfolio import Portfolio
from app.core.tax import TaxYear
from app.services.price_service import portfolio_eur_totals
from app.utils.formatting import fmt_currency, fmt_percent


def render(portfolio: Portfolio, tax_year: TaxYear | None = None) -> None:
    """
    Render the summary metrics strip at the top of the overview page.

    Args:
        portfolio: Priced (or unpriced) portfolio.
        tax_year:  Optional current tax year state for allowance display.
    """
    # ── Row 1: EUR totals ──────────────────────────────────────────────────
    totals = portfolio_eur_totals(portfolio)

    row1 = st.columns(2)

    with row1[0]:
        if totals:
            value_eur, cost_eur, gain_eur = totals
            st.metric(
                label="Total Portfolio Value",
                value=fmt_currency(value_eur, symbol="€"),
                delta=f"{fmt_currency(cost_eur, symbol='€')} cost basis",
                delta_color="off",
            )
        else:
            st.metric(label="Total Portfolio Value", value="—", delta="prices loading")

    with row1[1]:
        if totals:
            value_eur, cost_eur, gain_eur = totals
            gain_pct = gain_eur / cost_eur if cost_eur else None
            st.metric(
                label="Total Unrealised Gain",
                value=fmt_currency(gain_eur, symbol="€", show_sign=True),
                delta=fmt_percent(gain_pct) if gain_pct is not None else "—",
                delta_color="normal" if gain_eur >= 0 else "inverse",
            )
        else:
            st.metric(label="Total Unrealised Gain", value="—")

    st.caption("All values converted to EUR at live FX rates (USD · JPY → EUR).")

    st.divider()

    # ── Row 2: portfolio metadata and tax state ────────────────────────────
    row2 = st.columns(4)

    with row2[0]:
        st.metric(label="Positions", value=portfolio.summary.position_count)

    with row2[1]:
        intact = sum(1 for p in portfolio.positions if p.thesis_status.value == "intact")
        watch  = sum(1 for p in portfolio.positions if p.thesis_status.value == "watch")
        broken = sum(1 for p in portfolio.positions if p.thesis_status.value == "broken")
        st.metric(
            label="Thesis Status",
            value=f"{intact} intact",
            delta=f"{watch} watch · {broken} broken" if (watch or broken) else "all intact",
            delta_color="inverse" if broken else ("off" if watch else "normal"),
        )

    with row2[2]:
        if tax_year:
            st.metric(
                label="Sparerpauschbetrag remaining",
                value=fmt_currency(tax_year.allowance_remaining, symbol="€"),
                delta=(
                    f"{fmt_currency(tax_year.allowance_used, symbol='€')} used"
                    f" of {fmt_currency(tax_year.sparerpauschbetrag, symbol='€')}"
                ),
                delta_color="off",
            )
        else:
            st.metric(label="Sparerpauschbetrag", value="—")

    with row2[3]:
        if tax_year:
            st.metric(
                label="Tax headroom",
                value=fmt_currency(tax_year.harvest_headroom, symbol="€"),
                delta="gain still realisable tax-free",
                delta_color="off",
            )
        else:
            st.metric(label="Tax headroom", value="—")

    if not portfolio.fully_priced:
        st.caption("⚠ Some prices unavailable — totals shown where data exists.")
