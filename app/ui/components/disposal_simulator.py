"""
app/ui/components/disposal_simulator.py

Pre-trade disposal simulator: enter shares to sell, see which lots exit (FIFO),
total gain in EUR, and Sparerpauschbetrag / tax impact.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.core.lot import dispose_fifo
from app.core.position import Position
from app.core.tax import ABGELTUNGSTEUER_RATE, TaxYear, estimate_disposal_tax
from app.services.price_service import convert_to_eur, get_currency
from app.utils.formatting import fmt_currency, fmt_gain, fmt_percent


def _lots_consumed_table(result, ccy: str) -> pd.DataFrame:
    rows = []
    for d in result.disposals:
        cost_eur = convert_to_eur(d.cost_basis, ccy)
        proceeds_eur = convert_to_eur(d.proceeds, ccy)
        if cost_eur is not None and proceeds_eur is not None:
            gain_eur = proceeds_eur - cost_eur
            gain_pct = gain_eur / cost_eur if cost_eur else None
            gain_str = fmt_gain(gain_eur, gain_pct, symbol="€")
        else:
            gain_str = "—"
        rows.append({
            "Purchase Date":  d.purchase_date.strftime("%-d %b %Y"),
            "Buy Price":      d.purchase_price,
            "Shares Out":     d.shares_disposed,
            "Cost (€)":       cost_eur,
            "Proceeds (€)":   proceeds_eur,
            "Lot Gain (€)":   gain_str,
        })
    return pd.DataFrame(rows)


def render(position: Position, tax_year: TaxYear | None = None) -> None:
    """
    Render the disposal simulator for one position.

    Args:
        position: Priced position to simulate selling from.
        tax_year: Current tax year state for allowance impact calculation.
    """
    st.subheader("Disposal Simulator")

    if not position.has_live_price:
        st.warning(f"No live price for {position.ticker} — cannot simulate disposal.")
        return

    ccy = get_currency(position.ticker)
    max_shares = position.total_shares

    shares_to_sell = st.number_input(
        "Shares to sell",
        min_value=0.0,
        max_value=float(max_shares),
        value=0.0,
        step=0.5,
        format="%.4g",
        help=f"Maximum: {max_shares:g} shares held across {position.lot_count} lot(s).",
    )

    if shares_to_sell <= 0:
        return

    try:
        result = dispose_fifo(position.open_lots, shares_to_sell, position.live_price)  # type: ignore[arg-type]
    except ValueError as exc:
        st.error(str(exc))
        return

    # ── Lots consumed ─────────────────────────────────────────────────
    st.markdown("**Lots consumed (FIFO order)**")
    st.dataframe(
        _lots_consumed_table(result, ccy),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Purchase Date": st.column_config.TextColumn("Purchase Date", width="small"),
            "Buy Price":     st.column_config.NumberColumn("Buy Price", format="%.2f", width="small"),
            "Shares Out":    st.column_config.NumberColumn("Shares Out", format="%.4f", width="small"),
            "Cost (€)":      st.column_config.NumberColumn("Cost (€)", format="%.2f", width="small"),
            "Proceeds (€)":  st.column_config.NumberColumn("Proceeds (€)", format="%.2f", width="small"),
            "Lot Gain (€)":  st.column_config.TextColumn("Lot Gain (€)", width="medium"),
        },
    )

    # ── Summary metrics ────────────────────────────────────────────────
    st.markdown("**Summary**")
    proceeds_eur = convert_to_eur(result.total_proceeds, ccy)
    cost_eur = convert_to_eur(result.total_cost_basis, ccy)
    gain_eur = (proceeds_eur - cost_eur) if (proceeds_eur is not None and cost_eur is not None) else None
    gain_pct = (gain_eur / cost_eur) if (gain_eur is not None and cost_eur) else None

    s_cols = st.columns(3)
    with s_cols[0]:
        st.metric("Proceeds", fmt_currency(proceeds_eur, symbol="€"))
    with s_cols[1]:
        st.metric("Cost basis", fmt_currency(cost_eur, symbol="€"))
    with s_cols[2]:
        st.metric(
            "Gain",
            fmt_currency(gain_eur, symbol="€", show_sign=True),
            delta=fmt_percent(gain_pct) if gain_pct is not None else None,
            delta_color="normal" if (gain_eur or 0) >= 0 else "inverse",
        )

    # ── Tax impact ─────────────────────────────────────────────────────
    if gain_eur is None:
        st.caption("FX rate unavailable — tax impact not calculated.")
        return

    st.markdown("**Sparerpauschbetrag & tax impact**")

    if tax_year is None:
        st.caption("No tax year data loaded — allowance impact not available.")
        return

    est = estimate_disposal_tax(tax_year, gain_eur)

    t_cols = st.columns(4)
    with t_cols[0]:
        st.metric(
            "Allowance before",
            fmt_currency(est.allowance_remaining_before, symbol="€"),
        )
    with t_cols[1]:
        st.metric(
            "Allowance consumed",
            fmt_currency(est.allowance_consumed, symbol="€"),
            delta=f"−{fmt_currency(est.allowance_consumed, symbol='€')} used" if est.allowance_consumed else "none used",
            delta_color="off",
        )
    with t_cols[2]:
        st.metric(
            "Allowance after",
            fmt_currency(est.allowance_remaining_after, symbol="€"),
        )
    with t_cols[3]:
        st.metric(
            "Tax owed",
            fmt_currency(est.tax_owed, symbol="€"),
            delta="tax-free" if est.tax_owed == 0 else f"{ABGELTUNGSTEUER_RATE:.3%} rate",
            delta_color="off",
        )

    if est.loss_pot_consumed > 0:
        st.caption(
            f"Loss pot absorbed {fmt_currency(est.loss_pot_consumed, symbol='€')} "
            f"(remaining after: {fmt_currency(est.loss_pot_remaining_after, symbol='€')})."
        )
