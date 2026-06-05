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
    return "color: var(--text3)"


def _weight_bar_css(weight: object, gain: object, weight_max: float) -> str:
    """A coloured bar for the Weight cell, drawn as a left-anchored CSS gradient.

    The bar length scales to the largest weight; the colour tracks the position's
    gain — green when up, red when down, grey when stale (no gain). Returns ``""``
    for a blank weight (stale row)."""
    if weight is None or (isinstance(weight, float) and pd.isna(weight)):
        return ""
    try:
        w = float(weight)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    pct = min(100.0, w / weight_max * 100) if weight_max > 0 else 0.0

    if gain is None or (isinstance(gain, float) and pd.isna(gain)):
        color = "rgba(120, 120, 120, 0.45)"  # stale → neutral grey
    elif float(gain) >= 0:  # type: ignore[arg-type]
        color = "rgba(38, 166, 154, 0.45)"  # green
    else:
        color = "rgba(239, 83, 80, 0.45)"  # red
    return f"background: linear-gradient(90deg, {color} {pct:.1f}%, transparent {pct:.1f}%)"


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
    columns = list(df.columns)

    def _weight_styles(row: pd.Series) -> list[str]:
        # One CSS string per column; only the Weight cell gets the gain-tinted bar.
        bar = _weight_bar_css(row["Weight (%)"], row["Gain (€)"], weight_max)
        return [bar if col == "Weight (%)" else "" for col in columns]

    styler = df.style.map(_sign_color, subset=["Gain (€)", "Trend 30D (%)"]).apply(
        _weight_styles, axis=1
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
            "Weight (%)": st.column_config.NumberColumn(format="%.1f%%"),
            "Trend 30D (%)": st.column_config.NumberColumn(format="%+.1f%%"),
            "Lots": st.column_config.NumberColumn(format="%d"),
            "Sim": st.column_config.LinkColumn(display_text="⚡ Sim", width="small"),
        },
    )
