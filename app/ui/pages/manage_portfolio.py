"""
app/ui/pages/manage_portfolio.py

Portfolio-level management: add new positions and edit global metadata.
Individual transaction management (BUY/SELL/Delete) is handled on the Lot Ledger page.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from app.core.position import Horizon, Position, ThesisStatus
from app.core.transaction import Transaction
from app.data.repository import load_portfolio, save_portfolio
from app.services.price_service import lookup_name
from app.utils.cache import clear_all
from app.utils.logger import get_logger

logger = get_logger(__name__)

_HORIZON_OPTIONS = [h.value for h in Horizon]
_STATUS_OPTIONS = [s.value for s in ThesisStatus]


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_company_name(ticker: str) -> str | None:
    """Cached company name lookup."""
    return lookup_name(ticker)


def render() -> None:
    st.title("Manage Portfolio")

    portfolio = load_portfolio()

    tab1, tab2 = st.tabs(["New Position", "Edit Metadata"])

    with tab1:
        _new_position(portfolio)
    with tab2:
        _edit_metadata(portfolio)


# -------------------------------------------------------------- new position

def _new_position(portfolio) -> None:
    st.subheader("Add New Position")

    existing_tickers = {p.ticker for p in portfolio.positions}

    # Ticker is outside the form for live name preview
    ticker = st.text_input(
        "Ticker (e.g. NVDA, RHM.DE)", 
        key="np_ticker_input",
        placeholder="NVDA"
    ).strip().upper()

    fetched_name: str | None = None
    if len(ticker) >= 2:
        fetched_name = _fetch_company_name(ticker)
        if fetched_name:
            st.success(fetched_name)

    with st.form("new_position_form"):
        name_override = st.text_input("Display name", value=fetched_name or ticker)
        tags_raw = st.text_input(
            "Tags (comma-separated, e.g. semiconductors, ai-compute)"
        )
        horizon = st.selectbox("Horizon", options=_HORIZON_OPTIONS, key="np_horizon")
        thesis_status = st.selectbox(
            "Thesis status", options=_STATUS_OPTIONS, key="np_status"
        )
        thesis_notes = st.text_area("Thesis notes", key="np_notes")

        st.divider()
        st.markdown("**First Transaction (Buy)**")
        trade_date = st.date_input(
            "Purchase date", value=date.today(), max_value=date.today(), key="np_date",
        )
        price = st.number_input(
            "Purchase price per share",
            min_value=0.01, value=100.00, step=0.01, format="%.2f", key="np_price",
        )
        shares = st.number_input(
            "Shares", min_value=0.001, value=1.000, step=0.001, format="%.3f", key="np_shares",
        )
        submitted = st.form_submit_button("Add Position", type="primary")

    if submitted:
        if not ticker:
            st.error("Ticker is required.")
        elif ticker in existing_tickers:
            st.error(f"{ticker} already exists in the portfolio.")
        else:
            display_name = name_override.strip() or fetched_name or ticker
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            txn = Transaction(
                ticker=ticker,
                trade_date=trade_date,
                trade_type="buy",
                shares=shares,
                price=price,
            )
            new_pos = Position(
                ticker=ticker,
                name=display_name,
                tags=tags,
                horizon=Horizon(horizon),
                thesis_status=ThesisStatus(thesis_status),
                thesis_notes=thesis_notes,
                transactions=[txn],
            )
            new_portfolio = portfolio.model_copy(
                update={"positions": portfolio.positions + [new_pos]}
            )
            save_portfolio(new_portfolio)
            clear_all()
            logger.info("position_added", ticker=ticker)
            st.success(f"Position {ticker} — {display_name} added.")
            st.rerun()


# ----------------------------------------------------------- edit metadata

def _edit_metadata(portfolio) -> None:
    st.subheader("Edit Position Metadata")

    tickers = [p.ticker for p in portfolio.positions]
    if not tickers:
        st.info("No positions in portfolio.")
        return

    ticker_labels = {p.ticker: f"{p.ticker} — {p.name}" for p in portfolio.positions}
    selected = st.selectbox(
        "Position",
        options=tickers,
        format_func=lambda t: ticker_labels[t],
        key="em_selected",
    )

    pos = portfolio.get_position(selected)
    if pos is None:
        return

    horizon_idx = _HORIZON_OPTIONS.index(pos.horizon.value) if pos.horizon else 0
    status_idx = _STATUS_OPTIONS.index(pos.thesis_status.value)

    with st.form("edit_metadata_form"):
        horizon = st.selectbox(
            "Horizon", options=_HORIZON_OPTIONS, index=horizon_idx, key="em_horizon"
        )
        thesis_status = st.selectbox(
            "Thesis status", options=_STATUS_OPTIONS, index=status_idx, key="em_status"
        )
        thesis_notes = st.text_area(
            "Thesis notes", value=pos.thesis_notes, key="em_notes"
        )
        tags_raw = st.text_input(
            "Tags (comma-separated)", value=", ".join(pos.tags), key="em_tags"
        )
        submitted = st.form_submit_button("Save Changes", type="primary")

    if submitted:
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        fresh = load_portfolio()
        fresh_pos = fresh.get_position(selected)
        if fresh_pos is None:
            return
        updated_pos = fresh_pos.model_copy(
            update={
                "horizon": Horizon(horizon),
                "thesis_status": ThesisStatus(thesis_status),
                "thesis_notes": thesis_notes,
                "tags": tags,
            }
        )
        new_positions = [
            updated_pos if p.ticker == selected else p for p in fresh.positions
        ]
        new_portfolio = fresh.model_copy(update={"positions": new_positions})
        save_portfolio(new_portfolio)
        clear_all()
        logger.info("position_metadata_updated", ticker=selected)
        st.success(f"{selected} metadata saved.")
        st.rerun()
