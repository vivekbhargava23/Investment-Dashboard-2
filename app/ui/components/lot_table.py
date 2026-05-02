"""
app/ui/components/lot_table.py

Per-lot detail table for a single position, sorted in FIFO disposal order (oldest first).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app.core.position import Position
from app.services.price_service import convert_to_eur, get_currency
from app.utils.formatting import fmt_gain


def _days_held(purchase_date: date) -> int:
    return (date.today() - purchase_date).days


def _build_dataframe(position: Position) -> pd.DataFrame:
    ccy = get_currency(position.ticker)
    sorted_lots = sorted(position.open_lots, key=lambda lot: lot.purchase_date)

    rows = []
    for i, lot in enumerate(sorted_lots, start=1):
        cost_eur = convert_to_eur(lot.cost_basis, ccy)

        if position.has_live_price:
            value_eur = convert_to_eur(position.live_price * lot.shares, ccy)  # type: ignore[operator]
        else:
            value_eur = None

        if value_eur is not None and cost_eur is not None:
            gain_eur = value_eur - cost_eur
            gain_pct = gain_eur / cost_eur if cost_eur else None
            gain_str = fmt_gain(gain_eur, gain_pct, symbol="€")
        else:
            gain_str = "—"

        rows.append({
            "FIFO #":    i,
            "Date":      lot.purchase_date.strftime("%-d %b %Y"),
            "Price":     lot.purchase_price,
            "Ccy":       ccy,
            "Shares":    lot.shares,
            "Cost (€)":  cost_eur,
            "Value (€)": value_eur,
            "Gain (€)":  gain_str,
            "Days":      _days_held(lot.purchase_date),
        })

    return pd.DataFrame(rows)


def render(position: Position) -> None:
    """Render the per-lot table for one position in FIFO disposal order."""
    df = _build_dataframe(position)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "FIFO #":    st.column_config.NumberColumn("FIFO #", width="small"),
            "Date":      st.column_config.TextColumn("Purchase Date", width="small"),
            "Price":     st.column_config.NumberColumn("Purchase Price", format="%.2f", width="small"),
            "Ccy":       st.column_config.TextColumn("Ccy", width="small"),
            "Shares":    st.column_config.NumberColumn("Shares", format="%.4f", width="small"),
            "Cost (€)":  st.column_config.NumberColumn("Cost (€)", format="%.2f", width="small"),
            "Value (€)": st.column_config.NumberColumn("Value (€)", format="%.2f", width="small"),
            "Gain (€)":  st.column_config.TextColumn("Gain (€)", width="medium"),
            "Days":      st.column_config.NumberColumn("Days Held", width="small"),
        },
    )

    if not position.has_live_price:
        st.caption("⚠ No live price — Value and Gain unavailable.")
