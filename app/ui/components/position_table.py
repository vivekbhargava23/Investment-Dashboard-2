"""
app/ui/components/position_table.py

Live position table: one row per position, all monetary values converted to EUR.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.core.portfolio import Portfolio
from app.services.price_service import convert_to_eur, get_currency, get_fx_rate
from app.utils.formatting import fmt_gain


_THESIS_COLOURS = {
    "intact": "🟢",
    "watch":  "🟡",
    "broken": "🔴",
}


def _fx_label(currency: str) -> str:
    """Return display string for the FX rate, e.g. '1.1718 USD/EUR'."""
    if currency == "EUR":
        return "—"
    rate = get_fx_rate(currency)
    if rate is None:
        return "unavailable"
    precision = ".4f" if currency == "USD" else ".2f"
    return f"{rate:{precision}} {currency}/EUR"


def _build_dataframe(portfolio: Portfolio) -> pd.DataFrame:
    rows = []

    # Pre-compute EUR values for weight calculation
    eur_values: dict[str, float | None] = {}
    for pos in portfolio.positions:
        if not pos.has_live_price:
            eur_values[pos.ticker] = None
            continue
        ccy = get_currency(pos.ticker)
        eur_values[pos.ticker] = convert_to_eur(pos.current_value, ccy)  # type: ignore[arg-type]

    total_eur = sum(v for v in eur_values.values() if v is not None) or None

    for pos in portfolio.positions:
        ccy = get_currency(pos.ticker)
        value_eur = eur_values[pos.ticker]
        cost_eur = convert_to_eur(pos.total_cost_basis, ccy)

        if value_eur is not None and cost_eur is not None:
            gain_eur = value_eur - cost_eur
            gain_pct = gain_eur / cost_eur if cost_eur else None
            gain_str = fmt_gain(gain_eur, gain_pct, symbol="€")
        else:
            gain_eur = None
            gain_str = "—"

        weight = (value_eur / total_eur * 100) if (value_eur is not None and total_eur) else None

        rows.append({
            "Ticker":    pos.ticker,
            "Name":      pos.name,
            "Ccy":       ccy,
            "FX Rate":   _fx_label(ccy),
            "Price":     pos.live_price,
            "Shares":    pos.total_shares,
            "Cost (€)":  cost_eur,
            "Value (€)": value_eur,
            "Gain (€)":  gain_str,
            "Weight":    round(weight, 1) if weight is not None else None,
            "Horizon":   pos.horizon.value if pos.horizon else "—",
            "Thesis":    _THESIS_COLOURS.get(pos.thesis_status.value, "") + " " + pos.thesis_status.value,
            "Lots":      pos.lot_count,
        })

    return pd.DataFrame(rows)


def render(portfolio: Portfolio) -> None:
    """Render the live position table. All monetary values are EUR-converted."""
    df = _build_dataframe(portfolio)

    # Derive pixel width from the longest FX Rate string so it never truncates.
    # ~9px per character + 24px padding; floor at 120px (header + short values).
    max_fx_chars = int(df["FX Rate"].str.len().max()) if not df.empty else 10
    fx_col_width = max(120, max_fx_chars * 9 + 24)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Ticker":    st.column_config.TextColumn("Ticker", width="small"),
            "Name":      st.column_config.TextColumn("Name", width="medium"),
            "Ccy":       st.column_config.TextColumn("Ccy", width="small"),
            "FX Rate":   st.column_config.TextColumn("FX Rate", width=fx_col_width),
            "Price":     st.column_config.NumberColumn("Price", format="%.2f", width="small"),
            "Shares":    st.column_config.NumberColumn("Shares", format="%.4f", width="small"),
            "Cost (€)":  st.column_config.NumberColumn("Cost (€)", format="%.2f", width="small"),
            "Value (€)": st.column_config.NumberColumn("Value (€)", format="%.2f", width="small"),
            "Gain (€)":  st.column_config.TextColumn("Gain (€)", width="medium"),
            "Weight":    st.column_config.NumberColumn("Weight %", format="%.1f%%", width="small"),
            "Horizon":   st.column_config.TextColumn("Horizon", width="small"),
            "Thesis":    st.column_config.TextColumn("Thesis", width="small"),
            "Lots":      st.column_config.NumberColumn("Lots", width="small"),
        },
    )
