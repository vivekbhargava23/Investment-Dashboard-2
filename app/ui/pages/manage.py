# ruff: noqa: E501
"""
Manage Portfolio page — EUR-native transaction entry (ADR-005 / TICKET-009-revised).

Input model: ticker, type, date, shares, total EUR paid, fees EUR.
Currency and FX are derived, never entered by the user.

Submit flow (Add): Fill form → Calculate Preview → Confirm & Record.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import streamlit as st
from pydantic import ValidationError

from app.domain.fifo import SellExceedsOpenSharesError, compute_positions
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.tickers import UnsupportedTickerError, infer_currency_from_ticker
from app.ports.price_feed import PriceUnavailableError
from app.ports.ticker_resolver import TickerMatch
from app.services.sell_simulator import SellSimulationRequest
from app.services.trading import build_transaction
from app.services.valuation import clear_caches
from app.ui.format import format_date, format_eur
from app.ui.wiring import (
    get_fx_provider,
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
        price_per_share = net / shares
        total_line = (
            f"- Your EUR total: {format_eur(_eur(eur_total))}"
            f"  (= {format_eur(_eur(net))} net + {format_eur(_eur(fees_eur))} fees) ✓"
            if fees_eur
            else f"- Your EUR total: {format_eur(_eur(eur_total))} ✓"
        )
        st.markdown(
            f"Recording: {shares:g} share(s) of **{ticker}** on {format_date(trade_date)}\n"
            f"- Price: {format_eur(_eur(price_per_share))}\n"
            f"{total_line}"
        )
        return True, None

    try:
        hist = get_price_provider().get_historical_close(ticker, trade_date)
        net = eur_total - fees_eur
        implied_fx = (net / (shares * hist.amount)).quantize(Decimal("0.000001"))

        deviation_pct: Decimal | None = None
        ecb_ref_line = ""
        deviation_note = ""
        try:
            ecb_fx = get_fx_provider().get_historical_rate(currency, Currency.EUR, trade_date)
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

def _render_add_fill() -> None:
    st.subheader("Add Transaction")

    resolver = get_ticker_resolver()

    # --- Ticker autocomplete (outside form — uses st.rerun) ---
    query = st.text_input(
        "Ticker search",
        value=st.session_state.manage_add_query,
        placeholder="Type 2+ characters to search (e.g. APD, RHM, NVDA)…",
        key="_manage_add_query_input",
    )
    if query != st.session_state.manage_add_query:
        st.session_state.manage_add_query = query
        st.session_state.manage_add_resolved = None
        st.session_state.manage_add_use_as_typed = False

    if len(query) >= 2 and not st.session_state.manage_add_use_as_typed:
        try:
            matches = resolver.resolve(query, limit=6)
        except Exception:
            matches = []
        if matches:
            labels = [_match_label(m) for m in matches]
            sel = st.selectbox(
                "Select ticker",
                options=["— select —"] + labels,
                key="_manage_add_select",
            )
            if sel != "— select —":
                idx = labels.index(sel)
                st.session_state.manage_add_resolved = matches[idx]
        else:
            st.caption("No matches — try a different query or use the escape hatch below.")

    if st.session_state.manage_add_resolved is None and query:
        if st.button("Use as-typed (no validation)", key="_manage_add_use_as_typed_btn"):
            st.session_state.manage_add_use_as_typed = True

    resolved: TickerMatch | None = st.session_state.manage_add_resolved
    use_as_typed: bool = st.session_state.manage_add_use_as_typed
    ticker_display = resolved.symbol if resolved else (query if use_as_typed else "")

    if ticker_display:
        st.caption(f"Ticker: **{ticker_display}**" + (f" · {resolved.name} · {resolved.exchange}" if resolved else " (as-typed)"))

    # --- Transaction form ---
    with st.form("manage_add_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            tx_type_str = st.radio("Type", ["Buy", "Sell"], horizontal=True)
            trade_date = st.date_input(
                "Trade date",
                value=date.today(),
                min_value=date(2000, 1, 1),
                max_value=date.today(),
            )
            shares_f = st.number_input("Shares", min_value=0.0001, value=1.0, step=0.0001, format="%.4f")
        with col2:
            eur_total_f: float | None = st.number_input(
                "Total EUR paid",
                min_value=0.01,
                value=None,
                step=0.01,
                format="%.2f",
                placeholder="e.g. 1452.75",
                help="Total euros debited from your account (including fees), per your broker confirmation.",
            )
            fees_eur_f = st.number_input(
                "Fees (EUR, optional)",
                min_value=0.0,
                value=0.99,
                step=0.01,
                format="%.2f",
                help="Broker commission. Scalable typically charges €0.99.",
            )
            notes = st.text_input("Notes (optional)", value="")

        submitted = st.form_submit_button("Calculate Preview →", type="primary")

    if submitted:
        currency = _resolve_currency(resolved, ticker_display, use_as_typed)
        if not ticker_display:
            st.error("Please search for and select a ticker, or click 'Use as-typed' first.")
        elif currency is None:
            st.error(f"Currency for '{ticker_display}' is not yet supported. Contact the developer.")
        elif eur_total_f is None or eur_total_f <= 0:
            st.error("Please enter the total EUR paid (the amount debited from your account).")
        else:
            st.session_state.manage_add_pending = {
                "ticker": ticker_display,
                "resolved": resolved,
                "use_as_typed": use_as_typed,
                "tx_type_str": str(tx_type_str),
                "trade_date": trade_date,
                "shares": Decimal(str(shares_f)),
                "eur_total": Decimal(str(eur_total_f)),
                "fees_eur": Decimal(str(fees_eur_f)),
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
                st.session_state.manage_add_step = "fill"
                st.session_state.manage_add_pending = None
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
            st.session_state.manage_add_step = "fill"
            st.session_state.manage_add_pending = None
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
                fx_provider=get_fx_provider(),
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
        clear_caches(get_price_provider(), get_fx_provider())

    st.session_state.manage_add_query = ""
    st.session_state.manage_add_resolved = None
    st.session_state.manage_add_use_as_typed = False
    st.session_state.manage_add_step = "fill"
    st.session_state.manage_add_pending = None
    st.session_state.manage_feedback = (
        "success",
        f"Recorded {tx_type_str} of {shares:g} {ticker} for €{eur_total:.2f}.",
    )
    st.rerun()


# ---------------------------------------------------------------------------
# All Transactions table
# ---------------------------------------------------------------------------

def _render_transactions_table(txs: list[Transaction]) -> None:
    st.subheader("All Transactions")
    if not txs:
        st.info("No transactions recorded yet.")
        return

    sorted_txs = sorted(txs, key=lambda t: t.trade_date, reverse=True)

    header_cols = st.columns([2, 1, 2, 1.5, 2, 3, 1, 1])
    for col, label in zip(
        header_cols,
        ["Ticker", "Type", "Date", "Shares", "Cost (EUR)", "Notes", "", ""],
    ):
        col.markdown(f"**{label}**")

    for tx in sorted_txs:
        if st.session_state.manage_deleting_tx_id == tx.id:
            _render_delete_confirmation(tx)
            continue

        cols = st.columns([2, 1, 2, 1.5, 2, 3, 1, 1])
        cols[0].write(tx.ticker)
        cols[1].write(tx.type.value.upper())
        cols[2].write(format_date(tx.trade_date))
        cols[3].write(f"{tx.shares:g}")
        cols[4].write(format_eur(tx.cost_eur))
        cols[5].write(tx.notes or "—")
        if cols[6].button("✏", key=f"edit_{tx.id}", help="Edit"):
            st.session_state.manage_editing_tx_id = tx.id
            st.rerun()
        if cols[7].button("🗑", key=f"del_{tx.id}", help="Delete"):
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
    currency = infer_currency_from_ticker(tx.ticker)

    st.caption(f"Ticker: **{tx.ticker}** (read-only — to change ticker, delete and re-add)")

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
                tx.ticker, currency, tx_type_str, trade_date, shares, eur_total, fees_eur
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
            ticker=tx.ticker,
            currency=currency,
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
            fx_provider=get_fx_provider(),
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
    state.manage_add_pending = {
        "ticker": handoff.ticker,
        "resolved": None,
        "use_as_typed": True,
        "tx_type_str": "Sell",
        "trade_date": handoff.sell_date,
        "shares": handoff.shares,
        "eur_total": (handoff.sell_price_native.amount * handoff.sell_fx_rate_eur * handoff.shares).quantize(Decimal("0.01")),
        "fees_eur": Decimal("0"),
        "notes": "Recorded from sell simulator",
        "currency": handoff.sell_price_native.currency,
    }
    state.manage_add_step = "preview"
    state.manage_feedback = ("success", "Pre-filled from simulator — review the values and click Confirm & Record.")


def render() -> None:
    _init_state(st.session_state)
    _apply_simulator_handoff(st.session_state)

    st.markdown("<h2>Manage Portfolio</h2>", unsafe_allow_html=True)

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

    _render_transactions_table(txs)

    editing_id = st.session_state.manage_editing_tx_id
    if editing_id:
        st.divider()
        tx_to_edit = next((t for t in txs if t.id == editing_id), None)
        if tx_to_edit:
            _render_edit_form(tx_to_edit)
        else:
            st.session_state.manage_editing_tx_id = None
