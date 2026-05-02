"""
app/ui/components/harvest_table.py

Tax exposure and harvest opportunity calculator.

Total exposure: estimated Abgeltungsteuer if every position were closed today,
using net unrealised gain across the whole portfolio.

Harvest table: per-position unrealised gain in EUR sorted largest-first,
showing exactly how much of each gain fits in the remaining tax-free headroom
and what tax would be owed if that position were realised now.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.core.portfolio import Portfolio
from app.core.tax import ABGELTUNGSTEUER_RATE, TaxYear, estimate_disposal_tax
from app.services.price_service import convert_to_eur, get_currency
from app.utils.formatting import fmt_currency, fmt_gain, fmt_percent


_THESIS_COLOURS = {"intact": "🟢", "watch": "🟡", "broken": "🔴"}


def _unrealised_eur(portfolio: Portfolio) -> list[tuple[str, str, float]]:
    """
    Return (ticker, name, gain_eur) for every priced position.
    gain_eur is negative for positions showing a loss.
    """
    rows = []
    for pos in portfolio.positions:
        if not pos.has_live_price or pos.unrealised_gain is None:
            continue
        ccy = get_currency(pos.ticker)
        gain_eur = convert_to_eur(pos.unrealised_gain, ccy)
        if gain_eur is None:
            continue
        rows.append((pos, gain_eur))
    return rows


def render(tax_year: TaxYear, portfolio: Portfolio) -> None:
    """Render total tax exposure and the harvest opportunity table."""

    priced = _unrealised_eur(portfolio)

    # ── Total tax exposure ─────────────────────────────────────────────────
    st.subheader("Total Tax Exposure")
    st.caption(
        "Estimated Abgeltungsteuer if every position were closed at today's prices, "
        "given current YTD gains and remaining allowance."
    )

    if not priced:
        st.info("No priced positions — exposure cannot be calculated.")
    else:
        net_eur = sum(g for _, g in priced)
        est = estimate_disposal_tax(tax_year, net_eur)

        e_cols = st.columns(4)
        with e_cols[0]:
            st.metric(
                "Net Unrealised Gain",
                fmt_currency(net_eur, symbol="€", show_sign=True),
                delta_color="normal" if net_eur >= 0 else "inverse",
            )
        with e_cols[1]:
            st.metric(
                "Sheltered by Allowance + Loss Pot",
                fmt_currency(est.allowance_consumed + est.loss_pot_consumed, symbol="€"),
                delta_color="off",
            )
        with e_cols[2]:
            st.metric(
                "Taxable Gain",
                fmt_currency(est.taxable_gain, symbol="€"),
            )
        with e_cols[3]:
            st.metric(
                "Tax Owed",
                fmt_currency(est.tax_owed, symbol="€"),
                delta="tax-free" if est.tax_owed == 0 else f"{ABGELTUNGSTEUER_RATE:.3%} rate",
                delta_color="off",
            )

    st.divider()

    # ── Harvest opportunity ────────────────────────────────────────────────
    headroom = tax_year.harvest_headroom

    st.subheader("Harvest Opportunity")
    st.metric(
        "Tax-free headroom remaining",
        fmt_currency(headroom, symbol="€"),
        delta=(
            f"{fmt_currency(tax_year.allowance_remaining, symbol='€')} allowance"
            + (f" + {fmt_currency(tax_year.loss_pot_remaining, symbol='€')} loss pot"
               if tax_year.loss_pot_remaining > 0 else "")
        ),
        delta_color="off",
    )

    gains = sorted([(pos, g) for pos, g in priced if g > 0], key=lambda x: x[1], reverse=True)
    losses = [(pos, g) for pos, g in priced if g < 0]

    if not gains:
        st.info("No positions with unrealised gains to harvest.")
    else:
        st.caption(
            "Positions with unrealised gains, largest first. "
            "'Tax if realised' assumes this is the only trade from today."
        )

        rows = []
        for pos, gain_eur in gains:
            est = estimate_disposal_tax(tax_year, gain_eur)
            cost_basis_eur = convert_to_eur(pos.total_cost_basis, get_currency(pos.ticker))
            gain_pct = (gain_eur / cost_basis_eur) if cost_basis_eur else None
            rows.append({
                "Ticker":           pos.ticker,
                "Name":             pos.name,
                "Gain (€)":         gain_eur,
                "Gain %":           round(gain_pct * 100, 1) if gain_pct is not None else None,
                "Tax if Realised":  est.tax_owed,
                "Headroom Left (€)": max(0.0, headroom - gain_eur),
                "Horizon":          pos.horizon.value if pos.horizon else "—",
                "Thesis":           _THESIS_COLOURS.get(pos.thesis_status.value, "") + " " + pos.thesis_status.value,
            })

        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Ticker":           st.column_config.TextColumn("Ticker", width="small"),
                "Name":             st.column_config.TextColumn("Name", width="medium"),
                "Gain (€)":         st.column_config.NumberColumn("Gain (€)", format="€%.2f", width="small"),
                "Gain %":           st.column_config.NumberColumn("Gain %", format="%.1f%%", width="small"),
                "Tax if Realised":  st.column_config.NumberColumn("Tax if Realised (€)", format="€%.2f", width="small"),
                "Headroom Left (€)": st.column_config.NumberColumn("Headroom Left (€)", format="€%.2f", width="small"),
                "Horizon":          st.column_config.TextColumn("Horizon", width="small"),
                "Thesis":           st.column_config.TextColumn("Thesis", width="small"),
            },
        )

    if losses:
        st.caption(
            "Positions with unrealised losses — realising these adds to the loss pot, "
            "offsetting future gains: "
            + ", ".join(
                f"{pos.ticker} ({fmt_currency(g, symbol='€', show_sign=True)})"
                for pos, g in sorted(losses, key=lambda x: x[1])
            )
            + "."
        )
