# ruff: noqa: E501
"""
Manage Portfolio page — EUR-native transaction entry (ADR-005 / TICKET-009-revised).

Input model: ticker, type, date, shares, total EUR paid, fees EUR.
Currency and FX are derived, never entered by the user.

Submit flow (Add): Fill form → Calculate Preview → Confirm & Record.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from app.config import get_settings
from app.domain.fifo import SellExceedsOpenSharesError, compute_positions
from app.domain.isin_map import IsinMapDocument
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.tickers import UnsupportedTickerError, infer_currency_from_ticker
from app.ports.price_feed import PriceUnavailableError
from app.ports.ticker_resolver import TickerMatch
from app.services.data_admin import (
    UNSET,
    SourceFilter,
    count_transactions,
    erase_all_transactions,
    erase_transactions,
)
from app.services.sell_simulator import SellSimulationRequest
from app.services.trading import build_transaction
from app.services.valuation import clear_caches
from app.ui.backup import write_portfolio_backup
from app.ui.format import format_date, format_eur
from app.ui.wiring import (
    get_historical_fx_provider,
    get_isin_map_repo,
    get_live_fx_provider,
    get_price_provider,
    get_repository,
    get_ticker_resolver,
)

# ---------------------------------------------------------------------------
# Session-state helpers (pure functions — testable without Streamlit)
# ---------------------------------------------------------------------------

_STATE_DEFAULTS: dict[str, Any] = {
    "manage_add_query": "",
    "manage_add_resolved": None,       # TickerMatch | None
    "manage_add_use_as_typed": False,
    "manage_add_step": "fill",         # "fill" | "preview"
    "manage_add_pending": None,        # dict of captured form values | None
    "manage_add_form_key": 0,          # incremented on submit to reset the searchbox
    "manage_editing_tx_id": None,
    "manage_deleting_tx_id": None,
    "manage_feedback": None,           # ("success"|"error", message) | None
}


def _init_state(state: Any) -> None:
    """Idempotent: sets missing keys to their defaults."""
    for key, default in _STATE_DEFAULTS.items():
        if key not in state:
            state[key] = default


def _tx_to_form_values(tx: Transaction) -> dict[str, Any]:
    """Back-compute EUR-native form field values from a stored Transaction."""
    fees_eur = Decimal("0")
    if tx.fees_native:
        fees_eur = (tx.fees_native.amount * tx.fx_rate_eur).quantize(Decimal("0.01"))
    return {
        "ticker": tx.ticker,
        "tx_type": tx.type.value,
        "trade_date": tx.trade_date,
        "shares": float(tx.shares),
        "eur_total": float(tx.cost_eur.amount),
        "fees_eur": float(fees_eur),
        "notes": tx.notes or "",
    }


def _match_label(m: TickerMatch) -> str:
    price_str = f" · ~{m.recent_price}" if m.recent_price else ""
    return f"{m.symbol} · {m.name} · {m.exchange} · {m.currency.value}{price_str}"


# ---------------------------------------------------------------------------
# Submit pipeline helpers
# ---------------------------------------------------------------------------

def _resolve_currency(
    resolved: TickerMatch | None,
    ticker: str,
    use_as_typed: bool,
) -> Currency | None:
    """Return the native currency for this submit, or None on error."""
    if resolved is not None:
        return resolved.currency
    if use_as_typed:
        try:
            return infer_currency_from_ticker(ticker)
        except UnsupportedTickerError:
            return None
    return None


def _run_fifo_check(new_tx: Transaction, existing_txs: list[Transaction]) -> None:
    """Raises SellExceedsOpenSharesError if the sell would exceed open shares."""
    compute_positions(existing_txs + [new_tx])


# ---------------------------------------------------------------------------
# Recording preview panel — returns (price_available, deviation_pct)
# ---------------------------------------------------------------------------

def _render_recording_preview(
    ticker: str,
    currency: Currency,
    tx_type: str,
    trade_date: date,
    shares: Decimal,
    eur_total: Decimal,
    fees_eur: Decimal,
) -> tuple[bool, Decimal | None]:
    """
    Renders the breakdown of what will be recorded.

    Returns (price_available, deviation_pct):
    - price_available=False → PriceUnavailableError; caller should show fallback.
    - deviation_pct=None    → EUR-native or ECB rate unavailable.
    - deviation_pct≥10      → high-deviation; caller should change button label.
    """
    if shares <= 0 or eur_total <= 0:
        return True, None

    def _eur(v: Decimal) -> Money:
        return Money(amount=v.quantize(Decimal("0.01")), currency=Currency.EUR)

    if currency == Currency.EUR:
        net = eur_total - fees_eur
        eur_price_per_share = net / shares
        total_line = (
            f"- Your EUR total: {format_eur(_eur(eur_total))}"
            f"  (= {format_eur(_eur(net))} net + {format_eur(_eur(fees_eur))} fees) ✓"
            if fees_eur
            else f"- Your EUR total: {format_eur(_eur(eur_total))} ✓"
        )
        st.markdown(
            f"Recording: {shares:g} share(s) of **{ticker}** on {format_date(trade_date)}\n"
            f"- Price: {format_eur(_eur(eur_price_per_share))}\n"
            f"{total_line}"
        )
        eur_deviation_pct: Decimal | None = None
        try:
            hist = get_price_provider().get_historical_close(ticker, trade_date)
            raw_dev = abs(eur_price_per_share - hist.amount) / hist.amount * Decimal("100")
            eur_deviation_pct = raw_dev.quantize(Decimal("0.1"))
            direction = "below" if eur_price_per_share < hist.amount else "above"
            if eur_deviation_pct > Decimal("2"):
                st.warning(
                    f"⚠ Your total ({format_eur(_eur(eur_total))}) implies "
                    f"{format_eur(_eur(eur_price_per_share))} per share vs market close "
                    f"{format_eur(hist)} — {eur_deviation_pct}% {direction} market close. "
                    f"Check your amount and date."
                )
            else:
                st.markdown(f"✓ within {eur_deviation_pct}% of market close ({format_eur(hist)})")
        except PriceUnavailableError:
            st.warning(
                f"⚠ Couldn't fetch the historical price for **{ticker}** on {format_date(trade_date)}."
            )
        return True, eur_deviation_pct

    try:
        hist = get_price_provider().get_historical_close(ticker, trade_date)
        net = eur_total - fees_eur
        implied_fx = (net / (shares * hist.amount)).quantize(Decimal("0.000001"))

        deviation_pct = None
        ecb_ref_line = ""
        deviation_note = ""
        try:
            ecb_fx = get_historical_fx_provider().get_historical_rate(currency, Currency.EUR, trade_date)
            ecb_ref_amount = (hist.amount * ecb_fx).quantize(Decimal("0.01"))
            ecb_ref_eur = _eur(ecb_ref_amount)
            ecb_rate_str = ecb_fx.quantize(Decimal("0.0001"))
            ecb_ref_line = f"- ECB reference price: {format_eur(ecb_ref_eur)}  (= {hist} × {ecb_rate_str} ECB rate)\n"

            deviation_pct = (abs(implied_fx - ecb_fx) / ecb_fx * Decimal("100")).quantize(Decimal("0.1"))
            direction = "below" if implied_fx < ecb_fx else "above"
            if deviation_pct > Decimal("2"):
                implied_per_share = _eur((net / shares).quantize(Decimal("0.01")))
                st.warning(
                    f"⚠ Your total ({format_eur(_eur(eur_total))}) implies "
                    f"{format_eur(implied_per_share)} per share vs ECB reference "
                    f"{format_eur(ecb_ref_eur)} — {deviation_pct}% {direction} ECB reference. "
                    f"Check your amount and date."
                )
                deviation_note = f"  ({deviation_pct}% {direction} ECB reference — check your amount)"
            else:
                deviation_note = f"  ✓ within {deviation_pct}% of ECB"
        except Exception:
            pass

        total_line = (
            f"- Your EUR total: {format_eur(_eur(eur_total))}"
            f"  (= {format_eur(_eur(net))} net + {format_eur(_eur(fees_eur))} fees)"
            if fees_eur
            else f"- Your EUR total: {format_eur(_eur(eur_total))}"
        )
        st.markdown(
            f"Recording: {shares:g} share(s) of **{ticker}** on {format_date(trade_date)}\n"
            f"- Native currency: {currency.value}\n"
            f"- Historical close on {format_date(trade_date)}: {hist}\n"
            f"{ecb_ref_line}"
            f"{total_line}\n"
            f"- Implied FX rate: {implied_fx}{deviation_note}"
        )
        return True, deviation_pct

    except PriceUnavailableError:
        st.warning(
            f"⚠ Couldn't fetch the historical price for **{ticker}** on {format_date(trade_date)}. "
            "Enter native price and FX rate manually below."
        )
        return False, None
    except Exception:
        logging.warning("_render_recording_preview unexpected error for %s", ticker, exc_info=True)
        return True, None


# ---------------------------------------------------------------------------
# Add form — step router
# ---------------------------------------------------------------------------

def _render_add_form() -> None:
    if st.session_state.manage_add_step == "preview":
        _render_add_preview()
        return
    _render_add_fill()


# ---------------------------------------------------------------------------
# Add form — step 1: Fill
# ---------------------------------------------------------------------------

def _restore_fill_state_from_pending(pending: dict[str, Any] | None) -> None:
    """Re-sync session-state ticker fields from pending so the fill form re-populates.

    Called by the 'Back' button in the preview step. The pending dict is kept
    intact (not cleared) so the fill form can read draft values from it.
    """
    if pending is None:
        return
    if pending.get("use_as_typed"):
        st.session_state.manage_add_use_as_typed = True
        st.session_state.manage_add_query = pending.get("ticker", "")


def _render_add_fill() -> None:
    st.subheader("Add Transaction")

    # Draft holds saved values when the user navigates back from the preview step.
    draft: dict[str, Any] | None = st.session_state.manage_add_pending

    resolver = get_ticker_resolver()

    # --- Ticker autocomplete (outside form — uses st.rerun) ---
    searchbox_key = f"add_tx_ticker_{st.session_state.manage_add_form_key}"
    try:
        from app.ui.components.ticker_searchbox import render_ticker_searchbox
        # Pass the previously selected ticker as default when coming back from preview.
        default_match = draft.get("resolved") if draft else None
        resolved: TickerMatch | None = render_ticker_searchbox(
            key=searchbox_key, resolver=resolver, default_match=default_match
        )
    except Exception:
        logging.warning("Searchbox failed; falling back to text input", exc_info=True)
        raw = st.text_input("Ticker (autocomplete unavailable)", key="add_tx_ticker_fallback")
        resolved = resolver.lookup(raw) if raw else None

    use_as_typed: bool = False
    if resolved is not None:
        st.session_state.manage_add_resolved = resolved
        st.session_state.manage_add_use_as_typed = False
        st.session_state.manage_add_query = ""
    elif st.session_state.manage_add_use_as_typed:
        use_as_typed = True
    else:
        st.session_state.manage_add_resolved = None
        query = st.session_state.manage_add_query
        raw_ticker = st.text_input(
            "Or enter ticker directly (if not in dropdown)",
            value=query,
            key="_manage_add_query_input",
            placeholder="e.g. APD",
        )
        if raw_ticker != query:
            st.session_state.manage_add_query = raw_ticker
        if raw_ticker:
            if st.button("Use as-typed (no validation)", key="_manage_add_use_as_typed_btn"):
                st.session_state.manage_add_use_as_typed = True
                st.rerun()

    ticker_display = resolved.symbol if resolved else (
        st.session_state.manage_add_query if use_as_typed else ""
    )

    if ticker_display:
        st.caption(f"Ticker: **{ticker_display}**" + (f" · {resolved.name} · {resolved.exchange}" if resolved else " (as-typed)"))

    # --- Transaction form ---
    # Pre-populate from draft so values survive a round-trip through the preview step.
    default_type_idx = 0 if draft is None or draft.get("tx_type_str") == "Buy" else 1
    default_date = draft["trade_date"] if draft else date.today()
    default_shares = float(draft["shares"]) if draft else 1.0
    default_price = float(draft["price_per_share"]) if draft and "price_per_share" in draft else None
    default_fees = float(draft["fees_eur"]) if draft else 0.99
    default_notes = draft.get("notes") or "" if draft else ""

    with st.form("manage_add_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            tx_type_str = st.radio("Type", ["Buy", "Sell"], index=default_type_idx, horizontal=True)
            trade_date = st.date_input(
                "Trade date",
                value=default_date,
                min_value=date(2000, 1, 1),
                max_value=date.today(),
            )
            shares_f = st.number_input(
                "Shares", min_value=0.0001, value=default_shares, step=1.0, format="%.4f"
            )
        with col2:
            price_per_share_f: float | None = st.number_input(
                "Price per share (EUR)",
                min_value=0.01,
                value=default_price,
                step=0.01,
                format="%.2f",
                placeholder="e.g. 725.50",
                help="Price of a single share in EUR per your broker confirmation.",
            )
            fees_eur_f = st.number_input(
                "Fees (EUR, optional)",
                min_value=0.0,
                value=default_fees,
                step=0.01,
                format="%.2f",
                help="Broker commission. Scalable typically charges €0.99.",
            )
            notes = st.text_input("Notes (optional)", value=default_notes)

        submitted = st.form_submit_button("Calculate Preview →", type="primary")

    if submitted:
        currency = _resolve_currency(resolved, ticker_display, use_as_typed)
        if not ticker_display:
            st.error("Please search for and select a ticker, or click 'Use as-typed' first.")
        elif currency is None:
            st.error(f"Currency for '{ticker_display}' is not yet supported. Contact the developer.")
        elif price_per_share_f is None or price_per_share_f <= 0:
            st.error("Please enter the price per share (the price of a single share in EUR).")
        else:
            price_per_share = Decimal(str(price_per_share_f))
            shares = Decimal(str(shares_f))
            fees_eur = Decimal(str(fees_eur_f))
            eur_total = (price_per_share * shares + fees_eur).quantize(Decimal("0.01"))
            st.session_state.manage_add_pending = {
                "ticker": ticker_display,
                "resolved": resolved,
                "use_as_typed": use_as_typed,
                "tx_type_str": str(tx_type_str),
                "trade_date": trade_date,
                "shares": shares,
                "price_per_share": price_per_share,
                "eur_total": eur_total,
                "fees_eur": fees_eur,
                "notes": notes or None,
                "currency": currency,
            }
            st.session_state.manage_add_step = "preview"
            st.rerun()


# ---------------------------------------------------------------------------
# Add form — step 2: Preview + Confirm
# ---------------------------------------------------------------------------

def _render_add_preview() -> None:
    pending = st.session_state.manage_add_pending
    if pending is None:
        st.session_state.manage_add_step = "fill"
        st.rerun()
        return

    ticker: str = pending["ticker"]
    currency: Currency = pending["currency"]
    tx_type_str: str = pending["tx_type_str"]
    trade_date: date = pending["trade_date"]
    shares: Decimal = pending["shares"]
    eur_total: Decimal = pending["eur_total"]
    fees_eur: Decimal = pending["fees_eur"]
    notes: str | None = pending.get("notes")
    resolved: TickerMatch | None = pending.get("resolved")
    use_as_typed: bool = pending.get("use_as_typed", False)

    st.subheader("Preview Transaction")
    st.caption(
        f"Reviewing: **{ticker}** — {tx_type_str} {shares:g} share(s) "
        f"on {format_date(trade_date)} for €{eur_total:.2f}"
    )

    price_available, deviation_pct = _render_recording_preview(
        ticker, currency, tx_type_str, trade_date, shares, eur_total, fees_eur
    )

    st.divider()

    if not price_available:
        # Fallback: price fetch failed — show manual entry
        st.markdown("**Enter values manually to proceed:**")
        fb_currency_str = st.selectbox(
            "Currency", [c.value for c in Currency], key="_preview_fb_currency"
        )
        fallback_currency = Currency(fb_currency_str)
        fallback_price_f = st.number_input(
            "Native price per share", min_value=0.0001, step=0.01, format="%.4f",
            key="_preview_fb_price",
        )
        fallback_fx_f = st.number_input(
            "FX rate (EUR per 1 native)", min_value=0.000001, value=1.0,
            step=0.000001, format="%.6f", key="_preview_fb_fx",
        )
        col1, col2 = st.columns([2, 5])
        with col1:
            if st.button("Record with manual values", type="primary", key="_preview_confirm_fallback"):
                _handle_add_submit(
                    ticker=ticker,
                    resolved=resolved,
                    use_as_typed=use_as_typed,
                    tx_type_str=tx_type_str,
                    trade_date=trade_date,
                    shares=shares,
                    eur_total=eur_total,
                    fees_eur=fees_eur,
                    notes=notes,
                    fallback_price=Decimal(str(fallback_price_f)),
                    fallback_fx=Decimal(str(fallback_fx_f)),
                    fallback_currency=fallback_currency,
                )
        with col2:
            if st.button("← Back to edit", key="_preview_back_fallback"):
                _restore_fill_state_from_pending(st.session_state.manage_add_pending)
                st.session_state.manage_add_step = "fill"
                st.rerun()
        return

    # Price is available — show confirm / back buttons
    _HIGH_DEV = Decimal("10")
    is_high_dev = deviation_pct is not None and deviation_pct >= _HIGH_DEV
    if not is_high_dev:
        st.success("FX check passed — ready to record.")

    confirm_label = "Record anyway" if is_high_dev else "Confirm & Record ✓"
    col1, col2 = st.columns([2, 5])
    with col1:
        if st.button(confirm_label, type="primary", key="_preview_confirm"):
            _handle_add_submit(
                ticker=ticker,
                resolved=resolved,
                use_as_typed=use_as_typed,
                tx_type_str=tx_type_str,
                trade_date=trade_date,
                shares=shares,
                eur_total=eur_total,
                fees_eur=fees_eur,
                notes=notes,
                fallback_price=None,
                fallback_fx=None,
                fallback_currency=None,
            )
    with col2:
        if st.button("← Back to edit", key="_preview_back"):
            _restore_fill_state_from_pending(st.session_state.manage_add_pending)
            st.session_state.manage_add_step = "fill"
            st.rerun()


def _handle_add_submit(
    *,
    ticker: str,
    resolved: TickerMatch | None,
    use_as_typed: bool,
    tx_type_str: str,
    trade_date: date,
    shares: Decimal,
    eur_total: Decimal,
    fees_eur: Decimal,
    notes: str | None,
    fallback_price: Decimal | None,
    fallback_fx: Decimal | None,
    fallback_currency: Currency | None,
) -> None:
    if not ticker:
        st.error("Please search for and select a ticker, or click 'Use as-typed' first.")
        return

    currency = _resolve_currency(resolved, ticker, use_as_typed)
    if currency is None:
        st.error(f"Currency for '{ticker}' is not yet supported. Contact the developer.")
        return

    tx_type = TransactionType.BUY if tx_type_str == "Buy" else TransactionType.SELL

    try:
        if fallback_price is not None and fallback_fx is not None and fallback_currency is not None:
            fees_native = None
            if fees_eur:
                fees_native = Money(
                    amount=(fees_eur / fallback_fx).quantize(Decimal("0.0001")),
                    currency=fallback_currency,
                )
            tx = Transaction(
                ticker=ticker,
                type=tx_type,
                trade_date=trade_date,
                shares=shares,
                price_native=Money(amount=fallback_price, currency=fallback_currency),
                fees_native=fees_native,
                fx_rate_eur=fallback_fx,
                notes=notes,
            )
        else:
            tx, _ = build_transaction(
                ticker=ticker,
                tx_type=tx_type,
                trade_date=trade_date,
                shares=shares,
                eur_total=eur_total,
                fees_eur=fees_eur,
                currency=currency,
                price_provider=get_price_provider(),
                fx_provider=get_historical_fx_provider(),
            )
            tx = tx.model_copy(update={"notes": notes})

    except PriceUnavailableError as e:
        st.error(f"Could not fetch price for {ticker}: {e}. Use manual entry above.")
        return
    except ValidationError as e:
        st.error(f"Validation error: {e}")
        return
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        return

    if tx_type == TransactionType.SELL:
        try:
            existing = get_repository().load_all()
            _run_fifo_check(tx, existing)
        except SellExceedsOpenSharesError as e:
            st.error(str(e))
            return

    try:
        repo = get_repository()
        existing_tickers = {t.ticker for t in repo.load_all()}
        repo.add(tx)
    except Exception as e:
        st.error(f"Failed to save: {e}")
        return

    st.cache_data.clear()
    if tx.ticker not in existing_tickers:
        clear_caches(get_price_provider(), get_live_fx_provider())

    st.session_state.manage_add_query = ""
    st.session_state.manage_add_resolved = None
    st.session_state.manage_add_use_as_typed = False
    st.session_state.manage_add_step = "fill"
    st.session_state.manage_add_pending = None
    st.session_state.manage_add_form_key = st.session_state.manage_add_form_key + 1
    st.session_state.manage_feedback = (
        "success",
        f"Recorded {tx_type_str} of {shares:g} {ticker} for €{eur_total:.2f}.",
    )
    st.rerun()


# ---------------------------------------------------------------------------
# All Transactions table
# ---------------------------------------------------------------------------

# ── "All Transactions" table (TICKET-RD2) ───────────────────────────────────
# Rendered with st.dataframe for client-side sort/search (no page rerun on sort).
# st.dataframe can't host inline buttons, so actions live in an action bar that
# appears when a row is selected — mirrors the CSV-import workbench's pattern.

def build_transactions_dataframe(txs: list[Transaction]) -> pd.DataFrame:
    """Build the display dataframe. Row order matches ``txs`` so a selection index
    maps straight back to the transaction."""
    return pd.DataFrame(
        [
            {
                "Ticker": t.ticker,
                "Type": t.type.value.upper(),
                "Date": t.trade_date,
                "Shares": float(t.shares),
                "Cost (€)": float(t.cost_eur.amount),
                "Notes": t.notes or "",
            }
            for t in txs
        ],
        columns=["Ticker", "Type", "Date", "Shares", "Cost (€)", "Notes"],
    )


def _render_transactions_table(txs: list[Transaction]) -> None:
    st.subheader("All Transactions")
    if not txs:
        st.info("No transactions recorded yet.")
        return

    # A pending delete takes over the surface with its confirmation prompt.
    deleting_id = st.session_state.manage_deleting_tx_id
    if deleting_id:
        tx = next((t for t in txs if t.id == deleting_id), None)
        if tx is not None:
            _render_delete_confirmation(tx)
            return
        st.session_state.manage_deleting_tx_id = None

    df = build_transactions_dataframe(txs)
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="manage_tx_table",
        column_config={
            "Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "Shares": st.column_config.NumberColumn(format="%.4g"),
            "Cost (€)": st.column_config.NumberColumn(format="€%.2f"),
        },
    )

    selected = cast(Any, event).selection.rows
    if not selected:
        st.caption("Select a row to edit or delete it.")
        return

    tx = txs[selected[0]]
    st.caption(
        f"Selected **{tx.ticker}** — {tx.type.value} {tx.shares:g} share(s) "
        f"on {format_date(tx.trade_date)} for {format_eur(tx.cost_eur)}"
    )
    edit_col, del_col, _ = st.columns([1, 1, 6])
    if edit_col.button("✏ Edit", key="tx_edit_selected"):
        st.session_state.manage_editing_tx_id = tx.id
        st.rerun()
    if del_col.button("🗑 Delete", key="tx_delete_selected"):
        st.session_state.manage_deleting_tx_id = tx.id
        st.rerun()


def _render_delete_confirmation(tx: Transaction) -> None:
    cols = st.columns([6, 1, 1])
    cols[0].warning(f"Delete {tx.type.value} of {tx.shares:g} {tx.ticker} on {format_date(tx.trade_date)}?")
    if cols[1].button("Confirm", key=f"confirm_del_{tx.id}", type="primary"):
        try:
            get_repository().delete(tx.id)
        except Exception as e:
            st.error(f"Failed to delete: {e}")
            return
        st.cache_data.clear()
        st.session_state.manage_deleting_tx_id = None
        st.session_state.manage_feedback = ("success", f"Deleted {tx.ticker} transaction.")
        st.rerun()
    if cols[2].button("Cancel", key=f"cancel_del_{tx.id}"):
        st.session_state.manage_deleting_tx_id = None
        st.rerun()


# ---------------------------------------------------------------------------
# Edit form
# ---------------------------------------------------------------------------

def _render_edit_form(tx: Transaction) -> None:
    st.subheader(f"Edit Transaction — {tx.ticker}")
    vals = _tx_to_form_values(tx)

    # Ticker searchbox (outside form; pre-filled with existing ticker)
    resolver = get_ticker_resolver()
    default_match = resolver.lookup(tx.ticker)
    try:
        from app.ui.components.ticker_searchbox import render_ticker_searchbox
        edit_match: TickerMatch | None = render_ticker_searchbox(
            key=f"edit_tx_ticker_{tx.id}",
            resolver=resolver,
            default_match=default_match,
        )
    except Exception:
        logging.warning("Searchbox failed on edit form; showing ticker as caption", exc_info=True)
        edit_match = default_match
        st.caption(f"Ticker: **{tx.ticker}** (autocomplete unavailable)")

    resolved_ticker = edit_match.symbol if edit_match is not None else tx.ticker
    resolved_currency = edit_match.currency if edit_match is not None else infer_currency_from_ticker(tx.ticker)

    with st.form("manage_edit_form"):
        col1, col2 = st.columns(2)
        with col1:
            type_default = "Buy" if vals["tx_type"] == "buy" else "Sell"
            tx_type_str = st.radio("Type", ["Buy", "Sell"], index=0 if type_default == "Buy" else 1, horizontal=True)
            trade_date = st.date_input(
                "Trade date",
                value=vals["trade_date"],
                min_value=date(2000, 1, 1),
                max_value=date.today(),
            )
            shares_f = st.number_input("Shares", min_value=0.0001, value=vals["shares"], step=0.0001, format="%.4f")
        with col2:
            eur_total_f = st.number_input(
                "Total EUR paid",
                min_value=0.01,
                value=vals["eur_total"],
                step=0.01,
                format="%.2f",
                help="Total euros on the broker confirmation (including fees).",
            )
            fees_eur_f = st.number_input(
                "Fees (EUR)",
                min_value=0.0,
                value=vals["fees_eur"],
                step=0.01,
                format="%.2f",
            )
            notes = st.text_input("Notes", value=vals["notes"])

        shares = Decimal(str(shares_f))
        eur_total = Decimal(str(eur_total_f))
        fees_eur = Decimal(str(fees_eur_f))

        if shares > 0 and eur_total > 0:
            _render_recording_preview(
                resolved_ticker, resolved_currency, tx_type_str, trade_date, shares, eur_total, fees_eur
            )

        col_save, col_cancel = st.columns([1, 5])
        with col_save:
            submitted = st.form_submit_button("Save Changes", type="primary")
        with col_cancel:
            if st.form_submit_button("Cancel"):
                st.session_state.manage_editing_tx_id = None
                st.rerun()

    if submitted:
        _handle_edit_submit(
            tx_id=tx.id,
            ticker=resolved_ticker,
            currency=resolved_currency,
            tx_type_str=tx_type_str,
            trade_date=trade_date,
            shares=shares,
            eur_total=eur_total,
            fees_eur=fees_eur,
            notes=notes or None,
        )


def _handle_edit_submit(
    *,
    tx_id: str,
    ticker: str,
    currency: Currency,
    tx_type_str: str,
    trade_date: date,
    shares: Decimal,
    eur_total: Decimal,
    fees_eur: Decimal,
    notes: str | None,
) -> None:
    tx_type = TransactionType.BUY if tx_type_str == "Buy" else TransactionType.SELL
    try:
        tx, _ = build_transaction(
            ticker=ticker,
            tx_type=tx_type,
            trade_date=trade_date,
            shares=shares,
            eur_total=eur_total,
            fees_eur=fees_eur,
            currency=currency,
            price_provider=get_price_provider(),
            fx_provider=get_historical_fx_provider(),
        )
        tx = tx.model_copy(update={"id": tx_id, "notes": notes})
    except PriceUnavailableError as e:
        st.error(f"Could not fetch price for {ticker}: {e}. Try adjusting the date or check yfinance.")
        return
    except ValidationError as e:
        st.error(f"Validation error: {e}")
        return

    if tx_type == TransactionType.SELL:
        try:
            existing = [t for t in get_repository().load_all() if t.id != tx_id]
            _run_fifo_check(tx, existing)
        except SellExceedsOpenSharesError as e:
            st.error(str(e))
            return

    try:
        get_repository().update(tx)
    except Exception as e:
        st.error(f"Failed to update: {e}")
        return

    st.cache_data.clear()
    st.session_state.manage_editing_tx_id = None
    st.session_state.manage_feedback = ("success", f"Updated {ticker} transaction.")
    st.rerun()


# ---------------------------------------------------------------------------
# Danger zone — erase imported data (TICKET-CSV-17)
# ---------------------------------------------------------------------------

_ANY_SOURCE = "Any source"


def _write_erase_backup() -> Path:
    """Back up portfolio.json before an erase; return the backup path.

    If portfolio.json does not exist yet there is nothing to back up, so return a
    sentinel path that names the situation (mirrors the import workbench).
    """
    settings = get_settings()
    portfolio_path = Path(settings.portfolio_json_path)
    if portfolio_path.exists():
        return write_portfolio_backup(portfolio_path, settings.backups_dir)
    return settings.backups_dir / "no-backup-portfolio-did-not-exist.txt"


def _do_full_erase(also_clear_map: bool) -> None:
    bak = _write_erase_backup()
    count = erase_all_transactions(get_repository())
    map_msg = ""
    if also_clear_map:
        get_isin_map_repo().save(IsinMapDocument())
        map_msg = " ISIN mappings cleared."
    st.cache_data.clear()
    st.session_state.manage_feedback = (
        "success",
        f"Erased {count} transaction(s).{map_msg} Backup at `{bak}`.",
    )
    st.rerun()


def _do_scoped_erase(
    source: SourceFilter, date_from: date | None, date_to: date | None
) -> None:
    bak = _write_erase_backup()
    count = erase_transactions(
        get_repository(), source=source, date_from=date_from, date_to=date_to
    )
    st.cache_data.clear()
    st.session_state.manage_feedback = (
        "success",
        f"Erased {count} transaction(s). Backup at `{bak}`.",
    )
    st.rerun()


def _render_full_erase(txs: list[Transaction]) -> None:
    st.markdown("**Erase everything**")
    n = len(txs)
    st.caption(f"Deletes all {n} transaction(s). This cannot be undone except via the backup.")
    also_clear_map = st.checkbox(
        "Also clear ISIN → ticker mappings", key="danger_full_clear_map"
    )
    confirm = st.checkbox(
        f"I understand this permanently deletes all {n} transaction(s)",
        key="danger_full_confirm",
        disabled=n == 0 and not also_clear_map,
    )
    enabled = confirm and (n > 0 or also_clear_map)
    if st.button(
        "Erase everything", type="primary", disabled=not enabled, key="danger_full_btn"
    ):
        _do_full_erase(also_clear_map)


def _render_scoped_erase(txs: list[Transaction]) -> None:
    st.markdown("**Erase in parts**")
    st.caption("Delete only the transactions matching a source and/or trade-date range.")

    present_sources = sorted({tx.source for tx in txs})
    sel_source = st.selectbox(
        "Source", [_ANY_SOURCE, *present_sources], key="danger_scoped_source"
    )
    source_arg = UNSET if sel_source == _ANY_SOURCE else sel_source

    col1, col2 = st.columns(2)
    with col1:
        date_from: date | None = None
        if st.checkbox("Limit start date", key="danger_scoped_use_from"):
            date_from = st.date_input(
                "From (inclusive)",
                value=date.today(),
                min_value=date(2000, 1, 1),
                max_value=date.today(),
                key="danger_scoped_from",
            )
    with col2:
        date_to: date | None = None
        if st.checkbox("Limit end date", key="danger_scoped_use_to"):
            date_to = st.date_input(
                "To (inclusive)",
                value=date.today(),
                min_value=date(2000, 1, 1),
                max_value=date.today(),
                key="danger_scoped_to",
            )

    would_delete = count_transactions(
        get_repository(), source=source_arg, date_from=date_from, date_to=date_to
    )
    st.caption(f"Would delete **{would_delete}** transaction(s).")

    confirm = st.checkbox(
        f"I understand this permanently deletes {would_delete} transaction(s)",
        key="danger_scoped_confirm",
        disabled=would_delete == 0,
    )
    if st.button(
        "Erase matching",
        type="primary",
        disabled=not (would_delete > 0 and confirm),
        key="danger_scoped_btn",
    ):
        _do_scoped_erase(source_arg, date_from, date_to)


def _render_danger_zone(txs: list[Transaction]) -> None:
    with st.expander("⚠️ Danger zone — erase imported data", expanded=False):
        st.caption(
            "Destructive and intentional. Every erase writes a timestamped backup of "
            "portfolio.json first; roll back by restoring that file."
        )
        _render_full_erase(txs)
        st.divider()
        _render_scoped_erase(txs)


# ---------------------------------------------------------------------------
# Page entry point
# ---------------------------------------------------------------------------

def _apply_simulator_handoff(state: Any) -> None:
    """Pre-fill the add form from a simulator handoff, then clear it."""
    handoff: SellSimulationRequest | None = state.get("simulator_handoff")
    if handoff is None:
        return
    state.simulator_handoff = None  # consume once
    state.manage_add_query = handoff.ticker
    state.manage_add_use_as_typed = True
    state.manage_add_step = "fill"
    _price_eur = (handoff.sell_price_native.amount * handoff.sell_fx_rate_eur).quantize(Decimal("0.01"))
    state.manage_add_pending = {
        "ticker": handoff.ticker,
        "resolved": None,
        "use_as_typed": True,
        "tx_type_str": "Sell",
        "trade_date": handoff.sell_date,
        "shares": handoff.shares,
        "price_per_share": _price_eur,
        "eur_total": (_price_eur * handoff.shares).quantize(Decimal("0.01")),
        "fees_eur": Decimal("0"),
        "notes": "Recorded from sell simulator",
        "currency": handoff.sell_price_native.currency,
    }
    state.manage_add_step = "preview"
    state.manage_feedback = ("success", "Pre-filled from simulator — review the values and click Confirm & Record.")


def render() -> None:
    _init_state(st.session_state)
    _apply_simulator_handoff(st.session_state)

    feedback = st.session_state.manage_feedback
    if feedback:
        level, msg = feedback
        if level == "success":
            st.success(msg)
        else:
            st.error(msg)
        st.session_state.manage_feedback = None

    _render_add_form()

    st.divider()

    try:
        txs = get_repository().load_all()
    except Exception as e:
        st.error(f"Could not load transactions: {e}")
        txs = []

    _render_danger_zone(txs)

    st.divider()
    _render_transactions_table(txs)

    editing_id = st.session_state.manage_editing_tx_id
    if editing_id:
        st.divider()
        tx_to_edit = next((t for t in txs if t.id == editing_id), None)
        if tx_to_edit:
            _render_edit_form(tx_to_edit)
        else:
            st.session_state.manage_editing_tx_id = None
