"""
app/ui/pages/manage_portfolio.py

Portfolio management page: add transactions, new positions, delete transactions, edit metadata.
Standardised on the Transaction model. Mutating the transaction log triggers
a full FIFO replay to derive current holdings and realised gains.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from app.core.position import Horizon, Position, ThesisStatus
from app.core.transaction import Transaction
from app.data.repository import load_portfolio, load_tax_year, save_portfolio, save_tax_year
from app.services.price_service import (
    FifoPreview, convert_to_eur, fifo_sell_preview, get_currency,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

_HORIZON_OPTIONS = [h.value for h in Horizon]
_STATUS_OPTIONS = [s.value for s in ThesisStatus]


def _recompute_and_save_tax_year() -> None:
    """Rebuild tax_year from all in-year realised disposals and persist."""
    from app.core.tax import (
        DEFAULT_SPARERPAUSCHBETRAG,
        recompute_tax_year_from_realised_gains_eur,
    )

    portfolio = load_portfolio()
    existing = load_tax_year()
    year = existing.year if existing else date.today().year
    sparerpauschbetrag = (
        existing.sparerpauschbetrag if existing else DEFAULT_SPARERPAUSCHBETRAG
    )
    loss_pot = existing.loss_pot_carried_in if existing else 0.0

    gains_eur: list[float] = []
    for pos in portfolio.positions:
        ccy = get_currency(pos.ticker)
        for disposal in pos.realised_disposals:
            if disposal.trade_date.year == year:
                gain_eur = convert_to_eur(disposal.total_gain, ccy)
                if gain_eur is not None:
                    gains_eur.append(gain_eur)

    new = recompute_tax_year_from_realised_gains_eur(
        year=year,
        realised_gains_eur=gains_eur,
        sparerpauschbetrag=sparerpauschbetrag,
        loss_pot_carried_in=loss_pot,
    )
    save_tax_year(new)


def render() -> None:
    st.title("Manage Portfolio")

    portfolio = load_portfolio()

    tab1, tab2, tab3, tab4 = st.tabs(
        ["Add Transaction", "New Position", "Delete Transaction", "Edit Metadata"]
    )

    with tab1:
        _add_transaction(portfolio)
    with tab2:
        _new_position(portfolio)
    with tab3:
        _delete_transaction(portfolio)
    with tab4:
        _edit_metadata(portfolio)


# ----------------------------------------------------------- add transaction

def _add_transaction(portfolio) -> None:
    st.subheader("Add Transaction to Existing Position")

    tickers = [p.ticker for p in portfolio.positions]
    if not tickers:
        st.info("No positions in portfolio.")
        return

    ticker_labels = {p.ticker: f"{p.ticker} — {p.name}" for p in portfolio.positions}

    selected = st.selectbox(
        "Position",
        options=tickers,
        format_func=lambda t: ticker_labels[t],
        key="at_selected",
    )
    trade_type: str = st.radio(
        "Transaction type",
        options=["BUY", "SELL"],
        horizontal=True,
        key="at_type",
    )

    pos = portfolio.get_position(selected)

    if trade_type == "BUY":
        with st.form("form_add_buy"):
            tx_c1, tx_c2, tx_c3 = st.columns(3)
            with tx_c1:
                trade_date = st.date_input(
                    "Trade date", value=date.today(), max_value=date.today(), key="at_buy_date"
                )
            with tx_c2:
                price = st.number_input(
                    "Price per share",
                    min_value=0.01, value=100.00, step=0.01, format="%.2f", key="at_buy_price",
                )
            with tx_c3:
                shares = st.number_input(
                    "Shares", min_value=0.001, value=1.000, step=0.001, format="%.3f",
                    key="at_buy_shares",
                )
            submitted = st.form_submit_button("Add Buy", type="primary")

        if submitted:
            new_txn = Transaction(
                ticker=selected,
                trade_date=trade_date,
                trade_type="buy",
                shares=shares,
                price=price,
            )
            fresh = load_portfolio()
            fresh_pos = fresh.get_position(selected)
            if fresh_pos is None:
                st.error(f"Position {selected} not found.")
                return
            updated_pos = fresh_pos.model_copy(
                update={"transactions": fresh_pos.transactions + [new_txn]}
            )
            new_positions = [
                updated_pos if p.ticker == selected else p for p in fresh.positions
            ]
            save_portfolio(fresh.model_copy(update={"positions": new_positions}))
            st.cache_data.clear()
            logger.info("buy_added", ticker=selected, date=str(trade_date), shares=shares)
            st.success(
                f"Buy recorded for {selected}: {shares:g} shares @ {price:,.2f}"
                f" on {trade_date.strftime('%d %b %Y')}."
            )
            st.rerun()

    else:  # SELL
        max_shares = pos.total_shares if pos else 0.0
        if max_shares <= 0:
            st.warning(f"{selected} has no open shares to sell.")
            return

        sell_c1, sell_c2, sell_c3 = st.columns(3)
        with sell_c1:
            trade_date = st.date_input(
                "Trade date", value=date.today(), max_value=date.today(), key="at_sell_date"
            )
        with sell_c2:
            price = st.number_input(
                "Sale price per share",
                min_value=0.01, value=100.00, step=0.01, format="%.2f", key="at_sell_price",
            )
        with sell_c3:
            shares = st.number_input(
                f"Shares (max {max_shares:g})",
                min_value=0.001, max_value=float(max_shares),
                value=min(1.000, float(max_shares)),
                step=0.001, format="%.3f", key="at_sell_shares",
            )

        # Live FIFO preview
        pv: FifoPreview | None = None
        if shares > 0 and pos and pos.open_lots:
            try:
                pv = fifo_sell_preview(pos, shares, price)
                sign = "+" if pv.gain_eur >= 0 else ""
                color = "#4CAF50" if pv.gain_eur >= 0 else "#F44336"
                st.markdown(
                    f"**FIFO preview** — {pv.lots_consumed} lot(s) consumed · "
                    f"Proceeds **€{pv.proceeds_eur:,.2f}** · Cost **€{pv.cost_eur:,.2f}** · "
                    f"<span style='color:{color};font-weight:bold;'>"
                    f"Gain {sign}€{pv.gain_eur:,.2f}</span>",
                    unsafe_allow_html=True,
                )
            except ValueError as exc:
                st.error(str(exc))
                pv = None

        if st.button("Record Sale", type="primary", disabled=(pv is None), key="at_sell_submit"):
            new_txn = Transaction(
                ticker=selected,
                trade_date=trade_date,
                trade_type="sell",
                shares=shares,
                price=price,
            )
            fresh = load_portfolio()
            fresh_pos = fresh.get_position(selected)
            if fresh_pos is None:
                st.error(f"Position {selected} not found.")
                return
            updated_pos = fresh_pos.model_copy(
                update={"transactions": fresh_pos.transactions + [new_txn]}
            )
            new_positions = [
                updated_pos if p.ticker == selected else p for p in fresh.positions
            ]
            save_portfolio(fresh.model_copy(update={"positions": new_positions}))
            _recompute_and_save_tax_year()
            st.cache_data.clear()
            logger.info("sell_recorded", ticker=selected, date=str(trade_date), shares=shares)
            st.success(
                f"Sale recorded for {selected}: {shares:g} shares @ {price:,.2f}."
            )
            st.rerun()


# -------------------------------------------------------------- new position

def _new_position(portfolio) -> None:
    st.subheader("Add New Position")

    existing_tickers = {p.ticker for p in portfolio.positions}

    with st.form("new_position_form"):
        ticker = st.text_input("Ticker (e.g. NVDA, RHM.DE)").strip().upper()
        name = st.text_input("Display name (e.g. NVIDIA)")
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
        elif not name:
            st.error("Display name is required.")
        elif ticker in existing_tickers:
            st.error(f"{ticker} already exists in the portfolio.")
        else:
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
                name=name,
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
            st.cache_data.clear()
            logger.info("position_added", ticker=ticker)
            st.success(f"Position {ticker} — {name} added.")
            st.rerun()


# ---------------------------------------------------------- delete transaction

def _delete_transaction(portfolio) -> None:
    st.subheader("Delete a Transaction")

    tickers = [p.ticker for p in portfolio.positions]
    if not tickers:
        st.info("No positions in portfolio.")
        return

    ticker_labels = {p.ticker: f"{p.ticker} — {p.name}" for p in portfolio.positions}
    selected_ticker = st.selectbox(
        "Position",
        options=tickers,
        format_func=lambda t: ticker_labels[t],
        key="dt_ticker",
    )

    pos = portfolio.get_position(selected_ticker)
    if pos is None:
        return

    def _txn_label(txn: Transaction) -> str:
        return (
            f"[{txn.trade_type.upper()}] "
            f"{txn.trade_date.strftime('%d %b %Y')}"
            f" — {txn.shares:g} shares @ {txn.price:,.2f}"
        )

    # Sort transactions by date descending for easier deletion of recent ones
    sorted_txns = sorted(pos.transactions, key=lambda t: t.trade_date, reverse=True)
    txn_ids = [t.id for t in sorted_txns]
    txn_labels = {t.id: _txn_label(t) for t in sorted_txns}

    selected_txn_id = st.selectbox(
        "Transaction",
        options=txn_ids,
        format_func=lambda tid: txn_labels[tid],
        key="dt_txn",
    )

    if len(pos.transactions) == 1:
        st.warning(
            "This is the only transaction on this position — "
            "deleting it will remove the entire position."
        )

    confirm = st.checkbox("Confirm deletion", key="dt_confirm")
    if st.button("Delete Transaction", disabled=not confirm, type="primary"):
        fresh = load_portfolio()
        fresh_pos = fresh.get_position(selected_ticker)
        if fresh_pos is None:
            return

        remaining = [t for t in fresh_pos.transactions if t.id != selected_txn_id]
        if remaining:
            updated_pos = fresh_pos.model_copy(update={"transactions": remaining})
            new_positions = [
                updated_pos if p.ticker == selected_ticker else p
                for p in fresh.positions
            ]
            msg = f"Transaction deleted from {selected_ticker}."
        else:
            new_positions = [
                p for p in fresh.positions if p.ticker != selected_ticker
            ]
            msg = f"Last transaction deleted — position {selected_ticker} removed from portfolio."

        new_portfolio = fresh.model_copy(update={"positions": new_positions})
        save_portfolio(new_portfolio)
        _recompute_and_save_tax_year()
        st.cache_data.clear()
        logger.info(
            "transaction_deleted", ticker=selected_ticker, txn_id=selected_txn_id,
            position_removed=(not remaining),
        )
        st.success(msg)
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
        st.cache_data.clear()
        logger.info("position_metadata_updated", ticker=selected)
        st.success(f"{selected} metadata saved.")
        st.rerun()
