"""
app/ui/components/tax_summary.py

Year-to-date German tax summary strip: allowance tracker, realised P&L, loss pot.
Does not require a priced portfolio — driven entirely by TaxYear state.
"""

from __future__ import annotations

import streamlit as st

from app.core.tax import TaxYear
from app.utils.formatting import fmt_currency


def render(tax_year: TaxYear) -> None:
    """Render the YTD tax summary: allowance, realised P&L, and loss pot."""

    # ── Sparerpauschbetrag tracker ─────────────────────────────────────────
    st.subheader("Sparerpauschbetrag")

    used_pct = min(1.0, tax_year.allowance_used / tax_year.sparerpauschbetrag)
    bar_text = (
        f"{fmt_currency(tax_year.allowance_used, symbol='€')} used "
        f"of {fmt_currency(tax_year.sparerpauschbetrag, symbol='€')} annual allowance"
    )
    st.progress(used_pct, text=bar_text)

    a_cols = st.columns(3)
    with a_cols[0]:
        st.metric("Used", fmt_currency(tax_year.allowance_used, symbol="€"))
    with a_cols[1]:
        st.metric(
            "Remaining",
            fmt_currency(tax_year.allowance_remaining, symbol="€"),
            delta="fully used" if tax_year.allowance_remaining == 0 else "still available",
            delta_color="inverse" if tax_year.allowance_remaining == 0 else "off",
        )
    with a_cols[2]:
        st.metric("Annual Allowance", fmt_currency(tax_year.sparerpauschbetrag, symbol="€"))

    st.divider()

    # ── Realised P&L YTD ──────────────────────────────────────────────────
    st.subheader(f"Realised P&L — {tax_year.year} YTD")

    p_cols = st.columns(3)
    with p_cols[0]:
        st.metric(
            "Gross Gains",
            fmt_currency(tax_year.realised_gains, symbol="€"),
            delta="+gains" if tax_year.realised_gains > 0 else "none yet",
            delta_color="normal" if tax_year.realised_gains > 0 else "off",
        )
    with p_cols[1]:
        st.metric(
            "Gross Losses",
            fmt_currency(tax_year.realised_losses, symbol="€"),
            delta="-losses" if tax_year.realised_losses > 0 else "none yet",
            delta_color="inverse" if tax_year.realised_losses > 0 else "off",
        )
    with p_cols[2]:
        net = tax_year.net_gain
        st.metric(
            "Net Gain",
            fmt_currency(net, symbol="€", show_sign=True),
            delta_color="normal" if net >= 0 else "inverse",
        )

    st.divider()

    # ── Loss pot ──────────────────────────────────────────────────────────
    st.subheader("Loss Pot")

    absorbed = max(0.0, tax_year.loss_pot_carried_in - tax_year.loss_pot_remaining)

    l_cols = st.columns(3)
    with l_cols[0]:
        st.metric("Carried In from Prior Years", fmt_currency(tax_year.loss_pot_carried_in, symbol="€"))
    with l_cols[1]:
        st.metric(
            "Absorbed by YTD Gains",
            fmt_currency(absorbed, symbol="€"),
            delta="offset against gains" if absorbed > 0 else "none absorbed",
            delta_color="off",
        )
    with l_cols[2]:
        st.metric(
            "Remaining",
            fmt_currency(tax_year.loss_pot_remaining, symbol="€"),
            delta="offsets future gains" if tax_year.loss_pot_remaining > 0 else "none remaining",
            delta_color="off",
        )
