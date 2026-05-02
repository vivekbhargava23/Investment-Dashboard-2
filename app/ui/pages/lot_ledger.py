"""
app/ui/pages/lot_ledger.py

FIFO Lot Ledger page: per-position lot detail, pre-trade disposal simulator,
and inline portfolio management (add/edit/delete).
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from app.config.settings import get_settings
from app.core.portfolio import Portfolio
from app.core.position import Horizon, Position, ThesisStatus
from app.core.tax import TaxYear
from app.core.transaction import Transaction
from app.data.repository import load_portfolio, load_tax_year, save_portfolio, save_tax_year
from app.services.price_service import (
    convert_to_eur, fifo_sell_preview, get_currency, inject_prices, lookup_name,
)
from app.ui.components import disposal_simulator, transaction_form
from app.utils.cache import clear_all
from app.utils.formatting import fmt_gain
from app.utils.logger import get_logger

logger = get_logger(__name__)
_settings = get_settings()

_HORIZON_OPTIONS = [h.value for h in Horizon]
_STATUS_OPTIONS = [s.value for s in ThesisStatus]

# Column proportions: # | Type | Date | Price | Ccy | Shares | Cost€ | Value€ | Gain | Days | (edit) | (del)
_LOT_COLS = [0.35, 0.62, 1.05, 0.85, 0.38, 0.72, 0.85, 0.85, 1.4, 0.48, 0.48, 0.48]

_BUY_BADGE = (
    "<span style='background:#1a7f3c;color:white;padding:1px 6px;"
    "border-radius:3px;font-size:0.75em;font-weight:bold;'>BUY</span>"
)
_SELL_BADGE = (
    "<span style='background:#b35900;color:white;padding:1px 6px;"
    "border-radius:3px;font-size:0.75em;font-weight:bold;'>SELL</span>"
)


def _recompute_and_save_tax_year() -> None:
    """Rebuild tax_year from all in-year disposals and persist."""
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


@st.cache_data(ttl=_settings.price_refresh_interval_seconds, show_spinner=False)
def _load_priced_portfolio() -> Portfolio:
    return inject_prices(load_portfolio())


@st.cache_data(ttl=300, show_spinner=False)
def _load_tax_year() -> TaxYear | None:
    return load_tax_year()


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_company_name(ticker: str) -> str | None:
    """Cached company name lookup — avoids a network call on every keypress."""
    return lookup_name(ticker)


def _init_ss() -> None:
    """Initialise session-state keys used by the management forms."""
    defaults: dict = {
        "ll_show_add_position": False,
        "ll_show_add_lot": False,
        "ll_edit_ticker": None,
        "ll_pending_delete_lot_id": None,
        "ll_editing_lot_id": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ─── page entry ──────────────────────────────────────────────────────────────

def render() -> None:
    """Render the FIFO Lot Ledger page."""
    _init_ss()
    st.title("FIFO Lot Ledger")

    with st.spinner("Fetching live prices…"):
        portfolio = _load_priced_portfolio()
    tax_year = _load_tax_year()

    # ── Add New Position ──────────────────────────────────────────────────
    _render_add_position_section(portfolio)
    st.divider()

    # ── Position selector ─────────────────────────────────────────────────
    if not portfolio.positions:
        st.info("No positions yet — add one above.")
        return

    options = [pos.ticker for pos in portfolio.positions]
    selected = st.selectbox(
        "Position",
        options=options,
        format_func=lambda t: f"{t} — {portfolio.get_position(t).name}",  # type: ignore[union-attr]
    )

    position = portfolio.get_position(selected)
    if position is None:
        return

    # ── Position header with edit button ─────────────────────────────────
    hdr_col, edit_col = st.columns([5, 1])
    with hdr_col:
        st.subheader(f"{position.name} ({position.ticker})")
        avg = position.average_cost
        st.caption(
            f"{position.lot_count} open lot(s) · "
            f"{position.total_shares:g} shares · "
            f"avg cost {avg:.2f} (display only — FIFO used for tax)"
            if avg is not None else
            f"{position.lot_count} open lot(s) · {position.total_shares:g} shares"
        )
    with edit_col:
        st.write("")  # vertical alignment
        edit_label = "✕ Close" if st.session_state.ll_edit_ticker == selected else "✏ Edit"
        if st.button(edit_label, key="btn_edit_meta"):
            st.session_state.ll_edit_ticker = (
                None if st.session_state.ll_edit_ticker == selected else selected
            )
            st.rerun()

    # ── Edit metadata form (inline, toggled by button above) ─────────────
    if st.session_state.ll_edit_ticker == selected:
        _render_edit_position_form(position)

    _render_lot_table(position)

    # ── Add Lot ───────────────────────────────────────────────────────────
    _render_add_lot_section(position)

    st.divider()

    # ── Disposal simulator ────────────────────────────────────────────────
    disposal_simulator.render(position, tax_year)

    # ── Refresh ───────────────────────────────────────────────────────────
    st.caption(f"Prices refresh automatically every {_settings.price_refresh_interval_seconds}s.")
    if st.button("↺ Refresh now"):
        clear_all()
        st.rerun()


# ─── add new position ────────────────────────────────────────────────────────

def _render_add_position_section(portfolio: Portfolio) -> None:
    """Button and inline form for adding a new position to the portfolio."""
    if not st.session_state.ll_show_add_position:
        if st.button("＋ Add New Position", key="btn_show_add_pos"):
            st.session_state.ll_show_add_position = True
            st.rerun()
        return

    existing_tickers = {p.ticker for p in portfolio.positions}
    st.markdown("#### New Position")

    # Ticker is outside the form so the name preview updates on every change.
    ticker = st.text_input(
        "Ticker",
        key="add_pos_ticker",
        placeholder="e.g. NVDA, RHM.DE",
    ).strip().upper()

    # Name preview: auto-fetch and display so user can confirm the right stock.
    fetched_name: str | None = None
    if len(ticker) >= 2:
        fetched_name = _fetch_company_name(ticker)
        if fetched_name:
            st.success(fetched_name)
        else:
            st.warning(f"'{ticker}' not found in yfinance — add a display name in Advanced below.")

    with st.form("form_add_position"):
        lot_c1, lot_c2, lot_c3 = st.columns(3)
        with lot_c1:
            purchase_date = st.date_input(
                "Purchase date", value=date.today(), max_value=date.today(), key="ap_date"
            )
        with lot_c2:
            purchase_price = st.number_input(
                "Price per share", min_value=0.01, value=100.00,
                step=0.01, format="%.2f", key="ap_price",
            )
        with lot_c3:
            shares = st.number_input(
                "Shares", min_value=0.001, value=1.000,
                step=0.001, format="%.3f", key="ap_shares",
            )

        with st.expander("Advanced (optional)"):
            name_override = st.text_input(
                "Display name override",
                value=fetched_name or ticker,
                placeholder="Auto-filled from ticker lookup",
            )
            tags_raw = st.text_input("Tags (comma-separated)")
            adv_c1, adv_c2 = st.columns(2)
            with adv_c1:
                horizon = st.selectbox("Horizon", options=_HORIZON_OPTIONS)
            with adv_c2:
                thesis_status = st.selectbox("Thesis status", options=_STATUS_OPTIONS)
            thesis_notes = st.text_area("Thesis notes")

        btn_c1, btn_c2 = st.columns([1, 5])
        submitted = btn_c1.form_submit_button("Add Position", type="primary")
        cancelled = btn_c2.form_submit_button("Cancel")

    if cancelled:
        st.session_state.ll_show_add_position = False
        st.session_state.pop("add_pos_ticker", None)
        st.rerun()
    elif submitted:
        if not ticker:
            st.error("Ticker is required.")
        elif ticker in existing_tickers:
            st.error(f"{ticker} is already in the portfolio.")
        else:
            display_name = name_override.strip() or fetched_name or ticker
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            first_txn = Transaction(
                ticker=ticker,
                trade_date=purchase_date,
                trade_type="buy",
                shares=shares,
                price=purchase_price,
            )
            new_pos = Position(
                ticker=ticker,
                name=display_name,
                tags=tags,
                horizon=Horizon(horizon),
                thesis_status=ThesisStatus(thesis_status),
                thesis_notes=thesis_notes,
                transactions=[first_txn],
            )
            fresh = load_portfolio()
            new_portfolio = fresh.model_copy(
                update={"positions": fresh.positions + [new_pos]}
            )
            save_portfolio(new_portfolio)
            st.session_state.ll_show_add_position = False
            st.session_state.pop("add_pos_ticker", None)
            clear_all()
            logger.info("position_added", ticker=ticker, name=display_name)
            st.success(f"Position {ticker} — {display_name} added.")
            st.rerun()


# ─── add lot ─────────────────────────────────────────────────────────────────

def _render_add_lot_section(position: Position) -> None:
    """Button and inline section for recording a buy or sell transaction."""
    if not st.session_state.ll_show_add_lot:
        if st.button(
            f"＋ Add Transaction — {position.ticker}",
            key="btn_show_add_lot",
            type="secondary",
        ):
            st.session_state.ll_show_add_lot = True
            st.rerun()
        return

    transaction_form.render(
        position=position,
        on_success=lambda: st.session_state.update({"ll_show_add_lot": False}),
        on_cancel=lambda: st.session_state.update({"ll_show_add_lot": False}),
        key_prefix="add_lot",
    )


# ─── lot table ───────────────────────────────────────────────────────────────

def _render_lot_table(position: Position) -> None:
    """Column-based transaction table: all buy and sell transactions, chronological."""
    ccy = get_currency(position.ticker)

    # Build gain map from FIFO replay: sell_txn_id → gain in native currency
    gain_map: dict[str, float] = {
        d.sell_transaction_id: d.total_gain
        for d in position.realised_disposals
    }

    sorted_txns = sorted(position.transactions, key=lambda t: t.trade_date)

    if st.session_state.ll_editing_lot_id:
        editing_txn = next((t for t in position.transactions if t.id == st.session_state.ll_editing_lot_id), None)
        if editing_txn:
            transaction_form.render(
                position=position,
                existing_txn=editing_txn,
                key_prefix=f"edit_{editing_txn.id}",
                on_success=lambda: st.session_state.update({"ll_editing_lot_id": None}),
                on_cancel=lambda: st.session_state.update({"ll_editing_lot_id": None}),
            )
            st.divider()

    h = st.columns(_LOT_COLS)
    for col, label in zip(h, ["**#**", "**Type**", "**Date**", "**Price**", "**Ccy**",
                               "**Shares**", "**Cost €**", "**Value €**",
                               "**Gain**", "**Days**", "", ""]):
        col.markdown(label)
    st.markdown(
        "<hr style='margin:2px 0 6px 0; border:none; border-top:1px solid #e0e0e0;'/>",
        unsafe_allow_html=True,
    )

    for i, txn in enumerate(sorted_txns, start=1):
        _render_txn_row(i, txn, position, ccy, gain_map)

    if not position.has_live_price:
        st.caption("⚠ No live price — Value and Gain unavailable for open lots.")


def _render_txn_row(
    seq_num: int,
    txn: Transaction,
    position: Position,
    ccy: str,
    gain_map: dict[str, float],
) -> None:
    """One transaction row: buy or sell, with edit and delete."""
    is_pending_delete = st.session_state.ll_pending_delete_lot_id == txn.id
    is_editing = st.session_state.ll_editing_lot_id == txn.id
    is_buy = txn.trade_type == "buy"

    row = st.columns(_LOT_COLS)
    row[0].write(str(seq_num))
    row[1].markdown(_BUY_BADGE if is_buy else _SELL_BADGE, unsafe_allow_html=True)

    # Normal display mode
    row[2].write(txn.trade_date.strftime("%-d %b %Y"))
    row[3].write(f"{txn.price:,.2f}")
    row[4].write(ccy)
    row[5].write(f"{txn.shares:g}")

    cost_eur = convert_to_eur(txn.price * txn.shares, ccy)

    if is_buy:
        row[6].write(f"{cost_eur:,.2f}" if cost_eur is not None else "—")
        if position.has_live_price:
            value_eur = convert_to_eur(position.live_price * txn.shares, ccy)  # type: ignore[operator]
            row[7].write(f"{value_eur:,.2f}" if value_eur is not None else "—")
            if value_eur is not None and cost_eur is not None:
                g = value_eur - cost_eur
                row[8].write(fmt_gain(g, g / cost_eur if cost_eur else None, symbol="€"))
            else:
                row[8].write("—")
        else:
            row[7].write("—")
            row[8].write("—")
    else:
        # Sell row: show proceeds and realised gain from FIFO replay
        proceeds_eur = convert_to_eur(txn.price * txn.shares, ccy)
        row[6].write("—")
        row[7].write(f"{proceeds_eur:,.2f}" if proceeds_eur is not None else "—")
        
        # Gain is derived from the FIFO engine result
        gain_native = gain_map.get(txn.id)
        if gain_native is not None:
            gain_eur = convert_to_eur(gain_native, ccy)
            # Use gain_eur if available, else gain_native with native currency symbol
            display_gain = fmt_gain(
                absolute=gain_eur if gain_eur is not None else gain_native,
                percent=None,
                symbol="€" if gain_eur is not None else ccy
            )
            row[8].write(display_gain)
        else:
            row[8].write("—")

    row[9].write(str((date.today() - txn.trade_date).days))

    if not is_pending_delete:
        if row[10].button("✏", key=f"edit_btn_{txn.id}", help="Edit"):
            st.session_state.ll_editing_lot_id = txn.id
            st.rerun()

    if is_pending_delete:
        if row[11].button("✕", key=f"cancel_del_{txn.id}", help="Cancel"):
            st.session_state.ll_pending_delete_lot_id = None
            st.rerun()
        conf_c, btn_c, _ = st.columns([3, 1.2, 3])
        confirmed = conf_c.checkbox(
            f"Confirm delete — {txn.trade_date.strftime('%-d %b %Y')}"
            f", {txn.shares:g} shares",
            key=f"confirm_{txn.id}",
        )
        if btn_c.button(
            "Delete", key=f"do_del_{txn.id}", disabled=not confirmed, type="primary"
        ):
            _execute_txn_delete(position, txn.id)
    else:
        if row[11].button("🗑", key=f"del_btn_{txn.id}", help="Delete"):
            st.session_state.ll_pending_delete_lot_id = txn.id
            st.rerun()


def _execute_txn_delete(position: Position, txn_id: str) -> None:
    """Delete a transaction (or the entire position if it was the last one) and save."""
    fresh = load_portfolio()
    fresh_pos = fresh.get_position(position.ticker)
    if fresh_pos is None:
        st.error(f"Position {position.ticker} not found.")
        return

    remaining = [t for t in fresh_pos.transactions if t.id != txn_id]
    if remaining:
        updated_pos = fresh_pos.model_copy(update={"transactions": remaining})
        new_positions = [
            updated_pos if p.ticker == position.ticker else p
            for p in fresh.positions
        ]
        msg = f"Transaction deleted from {position.ticker}."
    else:
        new_positions = [p for p in fresh.positions if p.ticker != position.ticker]
        msg = f"Last transaction deleted — {position.ticker} removed from portfolio."

    new_portfolio = fresh.model_copy(update={"positions": new_positions})
    save_portfolio(new_portfolio)
    _recompute_and_save_tax_year()
    st.session_state.ll_pending_delete_lot_id = None
    clear_all()
    logger.info("transaction_deleted", ticker=position.ticker, txn_id=txn_id, position_removed=(not remaining))
    st.success(msg)
    st.rerun()


# ─── edit position metadata ───────────────────────────────────────────────────

def _render_edit_position_form(position: Position) -> None:
    """Inline form for editing horizon, thesis_status, thesis_notes, and tags."""
    st.markdown(f"#### Edit — {position.ticker}")

    horizon_idx = _HORIZON_OPTIONS.index(position.horizon.value) if position.horizon else 0
    status_idx = _STATUS_OPTIONS.index(position.thesis_status.value)

    with st.form("form_edit_position"):
        edit_c1, edit_c2 = st.columns(2)
        with edit_c1:
            horizon = st.selectbox(
                "Horizon", options=_HORIZON_OPTIONS, index=horizon_idx, key="em_horizon"
            )
            thesis_status = st.selectbox(
                "Thesis status", options=_STATUS_OPTIONS, index=status_idx, key="em_status"
            )
            tags_raw = st.text_input(
                "Tags (comma-separated)", value=", ".join(position.tags), key="em_tags"
            )
        with edit_c2:
            thesis_notes = st.text_area(
                "Thesis notes", value=position.thesis_notes, height=155, key="em_notes"
            )

        btn_c1, btn_c2 = st.columns([1, 5])
        submitted = btn_c1.form_submit_button("Save", type="primary")
        cancelled = btn_c2.form_submit_button("Cancel")

    if cancelled:
        st.session_state.ll_edit_ticker = None
        st.rerun()
    elif submitted:
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        fresh = load_portfolio()
        fresh_pos = fresh.get_position(position.ticker)
        if fresh_pos is None:
            st.error(f"Position {position.ticker} not found.")
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
            updated_pos if p.ticker == position.ticker else p
            for p in fresh.positions
        ]
        new_portfolio = fresh.model_copy(update={"positions": new_positions})
        save_portfolio(new_portfolio)
        st.session_state.ll_edit_ticker = None
        clear_all()
        logger.info("position_metadata_updated", ticker=position.ticker)
        st.success(f"{position.ticker} metadata saved.")
        st.rerun()
