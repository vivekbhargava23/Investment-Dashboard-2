from datetime import date
from decimal import Decimal

import pydantic
import streamlit as st

from app.domain.fifo import SellExceedsOpenSharesError, compute_positions
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.ports.fx_feed import FxRateUnavailableError
from app.services.valuation import clear_caches
from app.ui.wiring import get_fx_provider, get_price_provider, get_repository


def _format_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")

def _propose_transactions_for_validation(existing: list[Transaction], new: Transaction) -> list[Transaction]:
    return [*existing, new]

def _propose_transactions_for_edit(existing: list[Transaction], edited_tx: Transaction) -> list[Transaction]:
    return [tx if tx.id != edited_tx.id else edited_tx for tx in existing]

def _filter_by_ticker_substring(transactions: list[Transaction], query: str) -> list[Transaction]:
    if not query:
        return transactions
    q = query.lower()
    return [tx for tx in transactions if q in tx.ticker.lower()]

def render_feedback() -> None:
    feedback = st.session_state.form_feedback
    if feedback:
        status, msg = feedback
        if status == "success":
            st.success(msg)
        elif status == "error":
            st.error(msg)
        elif status == "warning":
            st.warning(msg)
        st.session_state.form_feedback = None

def _get_fx_rate_default(trade_date: date, currency: Currency) -> float:
    if currency == Currency.EUR:
        return 1.0
    try:
        rate = get_fx_provider().get_historical_rate(Currency.EUR, Currency.USD, trade_date)
        return float(rate)
    except FxRateUnavailableError:
        return 0.92

def render_transaction_form(form_key: str, default_tx: Transaction | None = None) -> None:
    is_edit = default_tx is not None
    header = "Editing transaction" if is_edit else "Add Transaction"
    
    if not is_edit:
        st.markdown(f"<h2>{header}</h2>", unsafe_allow_html=True)
    
    with st.form(key=form_key, clear_on_submit=not is_edit):
        col1, col2, col3 = st.columns(3)
        with col1:
            ticker_val = default_tx.ticker if default_tx else ""
            ticker_input = st.text_input("Ticker", value=ticker_val, placeholder="e.g. NVDA, RHM.DE")
        with col2:
            type_val = default_tx.type.value.capitalize() if default_tx else "Buy"
            type_input = st.radio("Type", ["Buy", "Sell"], index=0 if type_val == "Buy" else 1, horizontal=True)
        with col3:
            date_val = default_tx.trade_date if default_tx else date.today()
            date_input = st.date_input("Trade date", value=date_val, max_value=date.today(), min_value=date(2000, 1, 1))

        col4, col5, col6 = st.columns(3)
        with col4:
            shares_val = float(default_tx.shares) if default_tx else 1.0
            shares_input = st.number_input("Shares", min_value=0.0001, step=0.0001, format="%.4f", value=shares_val)
        with col6:
            currency_val = default_tx.price_native.currency.value if default_tx else "EUR"
            currency_input = st.selectbox("Currency", ["EUR", "USD"], index=0 if currency_val == "EUR" else 1)
        with col5:
            price_val = float(default_tx.price_native.amount) if default_tx else 0.01
            price_input = st.number_input(f"Price (per share, {currency_input})", min_value=0.01, step=0.01, format="%.4f", value=price_val)
            
        col7, col8, col9 = st.columns([1, 1, 1]) # changed to fit 3 cols, notes spans 2-3 natively but we'll do it differently
        
        # Determine FX rate default
        fx_default = 1.0
        if is_edit and default_tx:
            fx_default = float(default_tx.fx_rate_eur)
        else:
            # We fetch based on current session state for date and currency
            # Since date/currency are only read on submit for forms, this is a compromise
            trade_date_for_fx = date.today()
            if isinstance(date_input, date):
                trade_date_for_fx = date_input
            
            curr = Currency(currency_input) if isinstance(currency_input, str) else Currency.EUR
            fx_default = _get_fx_rate_default(trade_date_for_fx, curr)

        with col7:
            fx_val = float(default_tx.fx_rate_eur) if default_tx else fx_default
            fx_disabled = currency_input == "EUR"
            if fx_disabled:
                fx_val = 1.0
            fx_input = st.number_input("FX rate (EUR per 1 native)", min_value=0.0001, step=0.0001, format="%.6f", value=fx_val, disabled=fx_disabled)
        with col8:
            fees_val = float(default_tx.fees_native.amount) if default_tx and default_tx.fees_native else 0.0
            fees_input = st.number_input("Fees (optional)", min_value=0.0, step=0.01, format="%.4f", value=fees_val)
        with col9:
            notes_val = default_tx.notes if default_tx and default_tx.notes else ""
            notes_input = st.text_input("Notes (optional)", value=notes_val)

        submit_cols = st.columns([1, 1])
        with submit_cols[0]:
            submit_label = "Save changes" if is_edit else "Submit"
            submitted = st.form_submit_button(submit_label)
        with submit_cols[1]:
            canceled = False
            if is_edit:
                canceled = st.form_submit_button("Cancel")

        if canceled:
            st.session_state.editing_tx_id = None
            st.rerun()

        if submitted:
            # validation
            ticker = ticker_input.strip().upper()
            if not ticker:
                st.session_state.form_feedback = ("error", "Ticker cannot be empty")
                st.rerun()

            curr = Currency(currency_input)
            fx_rate = Decimal(str(fx_input)) if curr == Currency.USD else Decimal("1")
            
            try:
                price_money = Money(amount=Decimal(str(price_input)), currency=curr)
                fees_money = Money(amount=Decimal(str(fees_input)), currency=curr) if fees_input > 0 else None
                
                # Check date_input is valid type (Streamlit sometimes returns tuple if date range, but here it's single date)
                td = date_input if isinstance(date_input, date) else date_input[0]
                
                tx_type = TransactionType(type_input.lower())
                
                if is_edit and default_tx:
                    new_tx = Transaction(
                        id=default_tx.id,
                        type=tx_type,
                        ticker=ticker,
                        trade_date=td,
                        shares=Decimal(str(shares_input)),
                        price_native=price_money,
                        fees_native=fees_money,
                        fx_rate_eur=fx_rate,
                        notes=notes_input if notes_input else None,
                    )
                else:
                    new_tx = Transaction(
                        type=tx_type,
                        ticker=ticker,
                        trade_date=td,
                        shares=Decimal(str(shares_input)),
                        price_native=price_money,
                        fees_native=fees_money,
                        fx_rate_eur=fx_rate,
                        notes=notes_input if notes_input else None,
                    )
                
                repo = get_repository()
                existing_txs = repo.load_all()
                
                if is_edit and default_tx:
                    # Validate edit doesn't break FIFO
                    proposed = _propose_transactions_for_edit(existing_txs, new_tx)
                    try:
                        compute_positions(proposed)
                    except SellExceedsOpenSharesError as err:
                        st.session_state.form_feedback = ("error", f"Edit invalid: {str(err)}")
                        st.rerun()
                    
                    repo.update(new_tx)
                    st.cache_data.clear()
                    st.session_state.editing_tx_id = None
                    st.session_state.form_feedback = ("success", f"Updated {new_tx.type.value} of {new_tx.shares} {new_tx.ticker}")
                else:
                    if tx_type == TransactionType.SELL:
                        proposed = _propose_transactions_for_validation(existing_txs, new_tx)
                        try:
                            compute_positions(proposed)
                        except SellExceedsOpenSharesError:
                            current_positions = compute_positions(existing_txs)
                            open_shares = current_positions[ticker].open_shares if ticker in current_positions else Decimal("0")
                            st.session_state.form_feedback = ("error", f"Cannot sell {new_tx.shares} of {ticker} — you only have {open_shares} open shares.")
                            st.rerun()
                    
                    repo.add(new_tx)
                    st.cache_data.clear()
                    clear_caches(get_price_provider(), get_fx_provider())
                    st.session_state.form_feedback = ("success", f"Added {new_tx.type.value} of {new_tx.shares} {new_tx.ticker}")
                
                st.rerun()
                
            except pydantic.ValidationError as e:
                st.session_state.form_feedback = ("error", f"Validation error: {e}")
                st.rerun()
            except Exception as e:
                st.session_state.form_feedback = ("error", f"Error: {e}")
                st.rerun()

def render() -> None:
    if "editing_tx_id" not in st.session_state:
        st.session_state.editing_tx_id = None
    if "deleting_tx_id" not in st.session_state:
        st.session_state.deleting_tx_id = None
    if "form_feedback" not in st.session_state:
        st.session_state.form_feedback = None

    render_feedback()
    repo = get_repository()
    transactions = repo.load_all()

    # Edit Mode overrides top section if active
    if st.session_state.editing_tx_id is not None:
        try:
            tx_to_edit = repo.get(st.session_state.editing_tx_id)
            with st.expander(f"Editing transaction {tx_to_edit.id}", expanded=True):
                render_transaction_form("edit_tx_form", tx_to_edit)
        except Exception:
            st.session_state.editing_tx_id = None
            st.rerun()
    else:
        render_transaction_form("add_tx_form")
        
    st.markdown("---")

    # Delete Confirmation Banner
    if st.session_state.deleting_tx_id is not None:
        try:
            tx_to_delete = repo.get(st.session_state.deleting_tx_id)
            st.warning(f"⚠ Delete transaction {tx_to_delete.id} ({tx_to_delete.type.value.upper()} {tx_to_delete.shares} {tx_to_delete.ticker} on {_format_date(tx_to_delete.trade_date)})?")
            dcol1, dcol2 = st.columns([1, 10])
            with dcol1:
                if st.button("Confirm Delete"):
                    # Validate deletion doesn't break FIFO
                    transactions_without_this_one = [t for t in transactions if t.id != tx_to_delete.id]
                    try:
                        compute_positions(transactions_without_this_one)
                        repo.delete(tx_to_delete.id)
                        st.cache_data.clear()
                        st.session_state.deleting_tx_id = None
                        st.session_state.form_feedback = ("success", f"Deleted transaction {tx_to_delete.id}")
                        st.rerun()
                    except SellExceedsOpenSharesError:
                        st.session_state.form_feedback = ("error", "Cannot delete — subsequent sells depend on this buy. Delete or edit those first.")
                        st.session_state.deleting_tx_id = None
                        st.rerun()
            with dcol2:
                if st.button("Cancel", key="cancel_delete"):
                    st.session_state.deleting_tx_id = None
                    st.rerun()
        except Exception:
            st.session_state.deleting_tx_id = None
            st.rerun()

    st.markdown(f"<h2>All Transactions</h2><p style='color: var(--text3); margin-top: -10px; font-size: 0.9em;'>{len(transactions)} total · sorted by trade date (newest first)</p>", unsafe_allow_html=True)
    
    filter_q = st.text_input("Filter by ticker (substring match)")
    filtered_txs = _filter_by_ticker_substring(transactions, filter_q)
    
    sorted_txs = sorted(filtered_txs, key=lambda t: (t.trade_date, t.id), reverse=True)
    
    # Table Header
    st.markdown("<div class='tx-row'>", unsafe_allow_html=True)
    cols = st.columns([2, 1.5, 1, 1, 1.5, 1, 1.5, 1, 2, 0.5, 0.5])
    cols[0].markdown("**Date**")
    cols[1].markdown("**Ticker**")
    cols[2].markdown("**Type**")
    cols[3].markdown("**Shares**")
    cols[4].markdown("**Price**")
    cols[5].markdown("**Cur**")
    cols[6].markdown("**Cost (€)**")
    cols[7].markdown("**FX Rate**")
    cols[8].markdown("**Notes**")
    cols[9].markdown("** **")
    cols[10].markdown("** **")
    st.markdown("</div>", unsafe_allow_html=True)
    
    for tx in sorted_txs:
        st.markdown("<div class='tx-row'>", unsafe_allow_html=True)
        cols = st.columns([2, 1.5, 1, 1, 1.5, 1, 1.5, 1, 2, 0.5, 0.5])
        cols[0].write(_format_date(tx.trade_date))
        cols[1].write(tx.ticker)
        
        type_color = "var(--green)" if tx.type == TransactionType.BUY else "var(--red)"
        cols[2].markdown(f"<span style='color: {type_color}; font-weight: bold;'>{tx.type.value.upper()}</span>", unsafe_allow_html=True)
        
        cols[3].write(f"{tx.shares:.4f}")
        cols[4].write(f"{tx.price_native.amount:.2f}")
        cols[5].write(tx.price_native.currency.value)
        cols[6].write(f"{tx.cost_eur.amount:.2f}")
        cols[7].write(f"{tx.fx_rate_eur:.4f}")
        cols[8].write(tx.notes if tx.notes else "")
        
        if cols[9].button("✏️", key=f"edit_{tx.id}"):
            st.session_state.editing_tx_id = tx.id
            st.rerun()
        if cols[10].button("🗑️", key=f"delete_{tx.id}"):
            st.session_state.deleting_tx_id = tx.id
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
