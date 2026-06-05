"""Live Overview positions table.

TICKET-RD2 rebuilt this on ``st.dataframe`` so the table sorts and searches
*client-side* — clicking a column header reorders instantly with no Streamlit
rerun (the previous query-param/link version repainted the whole page). This
mirrors the CSV-import workbench table. Because ``st.dataframe`` escapes all
content itself, the manual ``html.escape`` dance the HTML version needed
(TICKET-ROBUST-1) is no longer required.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.domain.positions import LivePosition, PortfolioSummary

# Column order for the displayed dataframe.
_COLUMNS = [
    "Ticker",
    "Name",
    "Price (€)",
    "Shares",
    "Cost (€)",
    "Value (€)",
    "Gain (€)",
    "Gain (%)",
    "Weight (%)",
    "Trend 30D (%)",
    "Lots",
    "Sim",
]


def build_positions_dataframe(
    positions: dict[str, LivePosition],
    summary: PortfolioSummary,
    *,
    trend_values: dict[str, float | None] | None = None,
    name_lookup: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Build the positions dataframe. Stale fields (no live price/value/gain) are
    left as ``None`` so they render blank and sort to the end."""
    trend_values = trend_values or {}
    name_lookup = name_lookup or {}
    total_value = float(summary.total_value_eur.amount)

    rows: list[dict[str, object]] = []
    for ticker, p in positions.items():
        value = float(p.live_value_eur.amount) if p.live_value_eur is not None else None
        gain = (
            float(p.unrealised_gain_eur.amount)
            if p.unrealised_gain_eur is not None
            else None
        )
        gain_pct = (
            float(p.unrealised_gain_pct)
            if p.unrealised_gain_pct is not None
            else None
        )
        shares = float(p.position.open_shares)
        price = value / shares if value is not None and shares else None
        weight = value / total_value * 100 if value is not None and total_value > 0 else None
        rows.append(
            {
                "Ticker": ticker,
                "Name": name_lookup.get(ticker, ticker),
                "Price (€)": price,
                "Shares": shares,
                "Cost (€)": float(p.position.cost_basis_eur.amount),
                "Value (€)": value,
                "Gain (€)": gain,
                "Gain (%)": gain_pct,
                "Weight (%)": weight,
                "Trend 30D (%)": trend_values.get(ticker),
                "Lots": len(p.position.open_lots),
                "Sim": f"/?page=simulator&ticker={ticker}",
            }
        )
    return pd.DataFrame(rows, columns=_COLUMNS)


def _sign_color(v: object) -> str:
    """Pandas Styler cell colour: green positive, red negative, muted zero/blank."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "color: var(--text3)"
    try:
        n = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if n > 0:
        return "color: #26a69a"
    if n < 0:
        return "color: #ef5350"
    return "color: #9aa0a6"


def render_positions_table(
    positions: dict[str, LivePosition],
    summary: PortfolioSummary,
    *,
    trend_values: dict[str, float | None] | None = None,
    name_lookup: dict[str, str] | None = None,
) -> None:
    """Render the positions table as an interactive, client-side-sortable grid."""
    df = build_positions_dataframe(
        positions, summary, trend_values=trend_values, name_lookup=name_lookup
    )
    if df.empty:
        st.info("No positions yet.")
        return

    weight_max = float(df["Weight (%)"].max()) if df["Weight (%)"].notna().any() else 100.0

    # Weight is a plain (neutral) progress bar — it encodes *size of holding only*,
    # never gain. Direction/magnitude of P/L lives in the Gain columns, coloured by
    # sign, so a big position with a small loss no longer reads as a big loss.
    styler = df.style.map(
        _sign_color, subset=["Gain (€)", "Gain (%)", "Trend 30D (%)"]
    )

    st.dataframe(
        styler,
        use_container_width=True,
        hide_index=True,
        # Size to the row count so the whole portfolio shows without an inner scrollbar.
        height=(len(df) + 1) * 35 + 3,
        column_config={
            "Price (€)": st.column_config.NumberColumn(format="%.2f"),
            "Shares": st.column_config.NumberColumn(format="%.4g"),
            "Cost (€)": st.column_config.NumberColumn(format="€%.2f"),
            "Value (€)": st.column_config.NumberColumn(format="€%.2f"),
            "Gain (€)": st.column_config.NumberColumn(format="€%+.2f"),
            "Gain (%)": st.column_config.NumberColumn(format="%+.1f%%"),
            "Weight (%)": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=max(weight_max, 1.0)
            ),
            "Trend 30D (%)": st.column_config.NumberColumn(format="%+.1f%%"),
            "Lots": st.column_config.NumberColumn(format="%d"),
            "Sim": st.column_config.LinkColumn(display_text="⚡ Sim", width="small"),
        },
    )
