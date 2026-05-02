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
from app.services.ticker_search import resolve_unknown_ticker, search_tickers
from app.utils.cache import clear_all
from app.utils.logger import get_logger

logger = get_logger(__name__)

_HORIZON_OPTIONS = [h.value for h in Horizon]
_STATUS_OPTIONS = [s.value for s in ThesisStatus]


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

    # Ticker Search / Autocomplete
    search_query = st.text_input(
        "Search Ticker or Name", 
        key="np_search_input",
        placeholder="e.g. NVIDIA, ASML, RHM.DE"
    ).strip()

    search_results = search_tickers(search_query) if search_query else []
    
    selected_ticker = ""
    default_name = ""

    if search_results:
        options = [f"{e['ticker']} — {e['name']}" for e in search_results]
        selected_option = st.selectbox(
            "Select from results",
            options=options,
            key="np_search_select"
        )
        selected_ticker = selected_option.split(" — ")[0]
        default_name = selected_option.split(" — ")[1]
    elif search_query:
        # Check if the query itself is a valid-looking ticker
        if len(search_query) >= 1:
            st.info(f"'{search_query}' not in local catalogue. You can enter it manually below.")
            selected_ticker = search_query.upper()

    with st.form("new_position_form", clear_on_submit=True):
        st.markdown("#### Details")
        c1, c2 = st.columns(2)
        with c1:
            ticker = st.text_input("Ticker Symbol", value=selected_ticker).strip().upper()
        with c2:
            name = st.text_input("Display Name", value=default_name)
            
        tags_raw = st.text_input(
            "Tags (comma-separated, e.g. semiconductors, ai-compute)"
        )
        
        c3, c4 = st.columns(2)
        with c3:
            horizon = st.selectbox("Horizon", options=_HORIZON_OPTIONS, key="np_horizon")
        with c4:
            thesis_status = st.selectbox(
                "Thesis status", options=_STATUS_OPTIONS, key="np_status"
            )
        thesis_notes = st.text_area("Thesis notes", key="np_notes")

        st.divider()
        st.markdown("**First Transaction (Buy)**")
        tx_c1, tx_c2, tx_c3 = st.columns(3)
        with tx_c1:
            trade_date = st.date_input(
                "Purchase date", value=date.today(), max_value=date.today(), key="np_date",
            )
        with tx_c2:
            price = st.number_input(
                "Price per share",
                min_value=0.01, value=100.00, step=0.01, format="%.2f", key="np_price",
            )
        with tx_c3:
            shares = st.number_input(
                "Shares", min_value=0.001, value=1.000, step=0.001, format="%.3f", key="np_shares",
            )
            
        submitted = st.form_submit_button("Add Position", type="primary")

    if submitted:
        if not ticker:
            st.error("Ticker is required.")
            return
        
        if ticker in existing_tickers:
            st.error(f"{ticker} already exists in the portfolio.")
            return

        # Attempt to resolve name if still missing
        display_name = name.strip()
        if not display_name:
            resolved = resolve_unknown_ticker(ticker)
            display_name = resolved["name"] if resolved else ticker

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
