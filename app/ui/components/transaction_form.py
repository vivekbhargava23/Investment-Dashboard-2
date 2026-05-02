"""
app/ui/components/transaction_form.py

Unified transaction entry component for BUY and SELL operations.
Includes live FIFO preview for sells and handles validation/persistence.
"""

from __future__ import annotations

from datetime import date
from typing import Callable

import streamlit as st

from app.core.position import Position
from app.core.transaction import Transaction
from app.data.repository import load_portfolio, save_portfolio
from app.services.price_service import fifo_sell_preview
from app.utils.cache import clear_all
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _recompute_tax_year() -> None:
    """Trigger a tax year recomputation. Imported here to avoid circulars."""
    from app.ui.pages.lot_ledger import _recompute_and_save_tax_year
    _recompute_and_save_tax_year()


def render(
    position: Position,
    existing_txn: Transaction | None = None,
    on_success: Callable | None = None,
    on_cancel: Callable | None = None,
    key_prefix: str = "txn",
) -> None:
    """
    Render a transaction entry/edit form.
    
    Args:
        position:     The Position object the transaction belongs to.
        existing_txn: If provided, the form loads this transaction for editing.
        on_success:   Callback after successful save.
        on_cancel:    Callback after clicking Cancel.
        key_prefix:   String prefix for widget keys to avoid collisions.
    """
    mode = "Edit" if existing_txn else "Add"
    st.markdown(f"#### {mode} Transaction — {position.ticker}")

    # 1. Transaction Type (BUY/SELL)
    # Outside the form so SELL mode can show a live preview on change.
    type_options = ["BUY", "SELL"]
    default_type_idx = 0
    if existing_txn:
        default_type_idx = 0 if existing_txn.trade_type == "buy" else 1

    trade_type = st.radio(
        "Type",
        options=type_options,
        index=default_type_idx,
        horizontal=True,
        key=f"{key_prefix}_type",
    )

    is_sell = (trade_type == "SELL")

    # 2. Input Fields
    # For SELL, we keep inputs outside the form for 'live' reactivity if possible,
    # but Streamlit's 'updating on keystrokes' for number_input is limited.
    # We'll use columns for layout.
    c1, c2, c3 = st.columns(3)
    
    with c1:
        trade_date = st.date_input(
            "Date",
            value=existing_txn.trade_date if existing_txn else date.today(),
            max_value=date.today(),
            key=f"{key_prefix}_date",
        )
    with c2:
        price = st.number_input(
            "Price per share",
            min_value=0.01,
            value=existing_txn.price if existing_txn else 100.00,
            step=0.01,
            format="%.2f",
            key=f"{key_prefix}_price",
        )
    with c3:
        max_shares = position.total_shares
        # If editing a SELL, the 'max' available shares is total_shares + existing_txn.shares
        if existing_txn and existing_txn.trade_type == "sell":
            max_shares += existing_txn.shares
            
        shares = st.number_input(
            f"Shares (max {max_shares:g})" if is_sell else "Shares",
            min_value=0.001,
            max_value=float(max_shares) if (is_sell and max_shares > 0) else None,
            value=existing_txn.shares if existing_txn else (min(1.000, float(max_shares)) if is_sell and max_shares > 0 else 1.000),
            step=0.001,
            format="%.3f",
            key=f"{key_prefix}_shares",
        )

    # 3. Live FIFO Preview (for SELL)
    can_submit = True
    if is_sell:
        if shares > 0 and position.open_lots:
            try:
                # If editing, we simulate the sale against the position AS IF the current txn didn't exist
                temp_pos = position
                if existing_txn:
                    remaining_txns = [t for t in position.transactions if t.id != existing_txn.id]
                    temp_pos = position.model_copy(update={"transactions": remaining_txns})
                
                pv = fifo_sell_preview(temp_pos, shares, price)
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
                can_submit = False
        elif shares > max_shares:
            st.error(f"Insufficient shares. Available: {max_shares:g}")
            can_submit = False

    # 4. Action Buttons
    btn_c1, btn_c2 = st.columns([1, 5])
    submit_label = f"{mode} Transaction"
    if btn_c1.button(submit_label, type="primary", disabled=not can_submit, key=f"{key_prefix}_submit"):
        _execute_save(
            position=position,
            txn_id=existing_txn.id if existing_txn else None,
            trade_date=trade_date,
            price=price,
            shares=shares,
            trade_type=trade_type.lower(),
        )
        if on_success:
            on_success()
        st.rerun()

    if btn_c2.button("Cancel", key=f"{key_prefix}_cancel"):
        if on_cancel:
            on_cancel()
        st.rerun()


def _execute_save(
    position: Position,
    txn_id: str | None,
    trade_date: date,
    price: float,
    shares: float,
    trade_type: str,
) -> None:
    """Persist the transaction to the portfolio JSON."""
    fresh = load_portfolio()
    fresh_pos = fresh.get_position(position.ticker)
    if fresh_pos is None:
        st.error(f"Position {position.ticker} not found.")
        return

    if txn_id:
        # Edit existing
        updated_txns = [
            t.model_copy(update={
                "trade_date": trade_date,
                "price": price,
                "shares": shares,
                "trade_type": trade_type,
            }) if t.id == txn_id else t
            for t in fresh_pos.transactions
        ]
        log_msg = "transaction_edited"
    else:
        # Add new
        new_txn = Transaction(
            ticker=position.ticker,
            trade_date=trade_date,
            trade_type=trade_type,  # type: ignore[arg-type]
            shares=shares,
            price=price,
        )
        updated_txns = fresh_pos.transactions + [new_txn]
        log_msg = "transaction_added"

    updated_pos = fresh_pos.model_copy(update={"transactions": updated_txns})
    new_positions = [
        updated_pos if p.ticker == position.ticker else p
        for p in fresh.positions
    ]
    save_portfolio(fresh.model_copy(update={"positions": new_positions}))
    
    if trade_type == "sell" or (txn_id and any(t.trade_type == "sell" for t in fresh_pos.transactions)):
        _recompute_tax_year()
        
    clear_all()
    logger.info(log_msg, ticker=position.ticker, date=str(trade_date), shares=shares)
    st.success(f"Transaction recorded for {position.ticker}.")
