"""One card per instrument, with three independent controls.

Which price feed values a holding, what tax kind it is taxed under, and whether
it should be in the book at all are three separate decisions. The old mapper row
welded them into one: Save was disabled until a ticker matched, so a holding with
no feed could not be given a tax kind at all, and the two feedless holdings in
Vivek's book had to be classified by migration.

Here each control writes on its own and nothing disables anything else. Only the
feed Save needs a ticker match, because a feed *is* a ticker.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

import streamlit as st

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.tax.classification import InstrumentKind
from app.ports.ticker_resolver import TickerMatch
from app.services.isin_remap import (
    TickerAlreadyMappedError,
    count_transactions_for_isin,
    delete_transactions_for_isin,
)
from app.services.valuation import clear_caches
from app.ui.components.ticker_searchbox import render_ticker_searchbox
from app.ui.wiring import (
    get_company_provider,
    get_live_fx_provider,
    get_price_provider,
    get_ticker_resolver,
)

CardContext = Literal["task", "holding", "all_instruments"]

KIND_OPTIONS: list[InstrumentKind] = list(InstrumentKind)

KIND_LABEL: dict[InstrumentKind, str] = {
    InstrumentKind.AKTIE: "Aktie",
    InstrumentKind.AKTIENFONDS: "Aktienfonds (ETF)",
    InstrumentKind.MISCHFONDS: "Mischfonds",
    InstrumentKind.RENTENFONDS: "Rentenfonds",
    InstrumentKind.IMMOBILIENFONDS: "Immobilienfonds",
    InstrumentKind.IMMOBILIENFONDS_AUSLAND: "Immobilienfonds (Ausland)",
    InstrumentKind.SONSTIGE: "Sonstige",
    InstrumentKind.DIVIDENDE: "Dividende",
    InstrumentKind.ZINSEN: "Zinsen",
}

# Ticking this passes ``allow_shared_ticker`` — the deliberate "these two ISINs
# are the same instrument" merge of ADR-014 rule 4.
SHARED_TICKER_LABEL = "Same instrument (ISIN change)"

SHARED_TICKER_HELP = "Only tick this when the ISIN changed but the instrument did not."

USE_LAST_TRADE_LABEL = "Use last trade price"

_NO_FEED_SENTENCE = "none — valued at last trade price"


# ─── pure helpers ─────────────────────────────────────────────────────────────

def format_shares(value: Decimal) -> str:
    return f"{value.normalize():f}"


def card_headline(name: str, isin: str, open_shares: Decimal) -> str:
    """The card's first line: what this is, and whether it is still held."""
    held = (
        f"{format_shares(open_shares)} shares open" if open_shares > 0 else "closed"
    )
    return f"**{name or isin}** · {isin} · {held}"


def feed_state_sentence(mapping: IsinMapping | None) -> str:
    """The current price-feed state, in words rather than in a status value.

    "mapped"/"unmapped"/"ignored" are storage; this is what the user reads.
    """
    if mapping is None or mapping.status == "unmapped":
        return "not set"
    if mapping.status == "ignored":
        return _NO_FEED_SENTENCE
    if not mapping.ticker:
        return "not set"
    kind = mapping.instrument_kind
    if kind is None:
        return mapping.ticker
    return f"{mapping.ticker} ({KIND_LABEL.get(kind, kind.value)})"


def save_feed_disabled(match: TickerMatch | None) -> bool:
    """Only the feed Save needs a ticker match — no other control is gated on it."""
    return match is None


def shared_ticker_message(exc: TickerAlreadyMappedError) -> str:
    """The warning shown when a ticker is already another mapped ISIN's feed."""
    return (
        f"{exc.ticker} is already the feed for {exc.other_isin}. "
        f"Tick '{SHARED_TICKER_LABEL}' to merge on purpose."
    )


# ─── cached reads ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def suggest_kind(ticker: str) -> InstrumentKind | None:
    """Suggest InstrumentKind from yfinance quoteType. Returns None if unavailable."""
    try:
        qt = get_company_provider().get_quote_type(ticker)
        if qt == "EQUITY":
            return InstrumentKind.AKTIE
        if qt == "ETF":
            return InstrumentKind.AKTIENFONDS
        if qt == "MUTUALFUND":
            return InstrumentKind.MISCHFONDS
        return None
    except Exception:
        return None


def invalidate_view_caches() -> None:
    """Drop every cached view after a mapping write.

    Positions, NAV and the price/FX feeds are all keyed on tickers, and a remap
    rewrites tickers in place (ADR-014 consequence 1).
    """
    st.cache_data.clear()
    clear_caches(get_price_provider(), get_live_fx_provider())


# ─── controls ─────────────────────────────────────────────────────────────────

def render_feed_control(
    isin: str,
    name: str,
    mapping: IsinMapping | None,
    *,
    key_prefix: str,
) -> tuple[TickerMatch | None, bool, bool, bool]:
    """The price-feed row. Returns (match, allow_shared, save_clicked, use_last_clicked)."""
    st.caption(f"**Price feed** — {feed_state_sentence(mapping)}")
    match: TickerMatch | None = render_ticker_searchbox(
        key=f"{key_prefix}_search_{isin}",
        resolver=get_ticker_resolver(),
        placeholder=f"Search for {(name or isin)[:30]}…",
    )
    allow_shared = st.checkbox(
        SHARED_TICKER_LABEL,
        key=f"{key_prefix}_shared_{isin}",
        help=SHARED_TICKER_HELP,
    )
    col_save, col_last, _ = st.columns([1.1, 1.4, 3.5])
    save_clicked = col_save.button(
        "Save feed",
        key=f"{key_prefix}_save_{isin}",
        type="primary",
        disabled=save_feed_disabled(match),
        help=None if match else "Pick a ticker from the search results first.",
    )
    show_use_last = mapping is None or mapping.status != "ignored"
    use_last_clicked = show_use_last and col_last.button(
        USE_LAST_TRADE_LABEL,
        key=f"{key_prefix}_ignore_{isin}",
        help="No feed for this holding — value it at the price you last traded it.",
    )
    return match, allow_shared, save_clicked, bool(use_last_clicked)


def render_kind_control(
    isin: str,
    mapping: IsinMapping | None,
    *,
    key_prefix: str,
    suggested: InstrumentKind | None = None,
) -> InstrumentKind | None:
    """The tax-kind selectbox. Never gated on a feed — a certificate has a kind too.

    The stored kind is the only default. A suggestion is shown as a hint and never
    pre-selected: this control saves on change, so a pre-selected guess would save
    itself without anybody choosing it.
    """
    current = mapping.instrument_kind if mapping else None
    options: list[InstrumentKind | None] = [None, *KIND_OPTIONS]
    index = options.index(current) if current in options else 0
    st.caption("**Tax kind**")
    if current is None and suggested is not None:
        st.caption(f"yfinance suggests {KIND_LABEL.get(suggested, suggested.value)}.")
    return st.selectbox(
        "Tax kind",
        options=options,
        index=index,
        format_func=lambda k: "— pick a kind —" if k is None else KIND_LABEL.get(k, str(k)),
        key=f"{key_prefix}_kind_{isin}",
        label_visibility="collapsed",
    )


def render_write_off_control(
    isin: str,
    name: str,
    open_shares: Decimal,
    *,
    key_prefix: str,
    state_key: str,
    today: date,
) -> tuple[Decimal, date] | None:
    """Offer to write the holding down to €0. Returns (shares, date) once confirmed.

    Two fields, because both are judgement calls: when the broker actually stopped
    carrying it, and how much of it is gone.
    """
    if st.session_state.get(state_key) != isin:
        if st.button(
            f"Write off remaining {format_shares(open_shares)} shares…",
            key=f"{key_prefix}_writeoff_{isin}",
            help="Records a €0 sell. The history — and the realised loss — are kept.",
        ):
            st.session_state[state_key] = isin
            st.rerun()
        return None

    col_date, col_shares = st.columns(2)
    on_date = col_date.date_input(
        "Write-off date", value=today, key=f"{key_prefix}_wo_date_{isin}"
    )
    shares = col_shares.number_input(
        "Shares",
        min_value=0.0,
        max_value=float(open_shares),
        value=float(open_shares),
        key=f"{key_prefix}_wo_shares_{isin}",
    )
    col_yes, col_no, _ = st.columns([1, 1, 4])
    confirmed = col_yes.button(
        "Write off", key=f"{key_prefix}_wo_confirm_{isin}", type="primary"
    )
    if col_no.button("Cancel", key=f"{key_prefix}_wo_cancel_{isin}"):
        st.session_state[state_key] = None
        st.rerun()
    if not confirmed:
        return None
    st.session_state[state_key] = None
    return Decimal(str(shares)), on_date


def render_remove_control(
    isin: str,
    name: str,
    *,
    key_prefix: str,
    state_key: str,
) -> bool:
    """Remove the instrument and purge its transactions. Returns True once done.

    Two clicks, and a timestamped backup of ``portfolio.json`` before the purge —
    this is the only control on the card that destroys history.
    """
    from app.ui.backup import backup_portfolio_before_purge
    from app.ui.wiring import get_repository

    n = count_transactions_for_isin(get_repository(), isin)
    if st.session_state.get(state_key) != isin:
        if st.button(
            f"Remove instrument and its {n} transaction(s)…",
            key=f"{key_prefix}_remove_{isin}",
        ):
            st.session_state[state_key] = isin
            st.rerun()
        return False

    st.warning(
        f"Remove {name or isin} ({isin})? This permanently deletes {n} "
        "transaction(s) and the mapping. A backup of portfolio.json is written first."
    )
    col_yes, col_no, _ = st.columns([1, 1, 4])
    if col_yes.button("Remove", key=f"{key_prefix}_remove_confirm_{isin}", type="primary"):
        backup_portfolio_before_purge()
        delete_transactions_for_isin(get_repository(), isin)
        st.session_state[state_key] = None
        return True
    if col_no.button("Cancel", key=f"{key_prefix}_remove_cancel_{isin}"):
        st.session_state[state_key] = None
        st.rerun()
    return False


# ─── the card ─────────────────────────────────────────────────────────────────

FEEDBACK_KEY = "instrument_card.feedback"
_REMOVE_STATE_KEY = "instrument_card.confirming_remove"
_WRITE_OFF_STATE_KEY = "instrument_card.confirming_write_off"


def render_feedback() -> None:
    """Show and clear whatever the last card action said. Call once per page."""
    feedback = st.session_state.pop(FEEDBACK_KEY, None)
    if not feedback:
        return
    level, message = feedback
    {"success": st.success, "warning": st.warning, "error": st.error}[level](message)


def _say(level: str, message: str) -> None:
    st.session_state[FEEDBACK_KEY] = (level, message)


def render_instrument_card(
    isin: str,
    name: str,
    doc: IsinMapDocument,
    *,
    session_id: str | None,
    key_prefix: str,
    context: CardContext,
) -> None:
    """One instrument, three independent controls, plain-word state.

    ``session_id`` is the open sync session, or None when no file is open: every
    write goes through the session when there is one, so "Undo last sync" keeps
    working (`docs/DESIGN/SYNC-TAB.md`, "Sync session").
    """
    from app.services.isin_admin import apply_ignore, apply_kind, open_shares_for_isin
    from app.services.isin_remap import change_feed
    from app.services.sync import (
        WriteOffNotPossible,
        change_feed_in_session,
        ignore_in_session,
        set_kind_in_session,
        write_off,
        write_off_in_session,
    )
    from app.ui.wiring import get_isin_map_repo, get_repository, get_sync_store

    mapping = doc.entries.get(isin)
    display_name = mapping.name if mapping and mapping.name else name
    open_shares = open_shares_for_isin(get_repository(), isin)

    st.markdown(card_headline(display_name, isin, open_shares))

    match, allow_shared, save_clicked, use_last_clicked = render_feed_control(
        isin, display_name, mapping, key_prefix=key_prefix
    )

    if save_clicked and match is not None:
        kind = (
            mapping.instrument_kind
            if mapping and mapping.instrument_kind
            else suggest_kind(match.symbol)
        )
        try:
            if session_id:
                rewritten = change_feed_in_session(
                    isin,
                    match.symbol,
                    kind or InstrumentKind.SONSTIGE,
                    session_id,
                    get_isin_map_repo(),
                    get_repository(),
                    get_sync_store(),
                    allow_shared_ticker=allow_shared,
                )
            else:
                repo = get_isin_map_repo()
                new_doc, rewritten = change_feed(
                    isin,
                    match.symbol,
                    kind or InstrumentKind.SONSTIGE,
                    repo.load(),
                    get_repository(),
                    allow_shared_ticker=allow_shared,
                )
                repo.save(new_doc)
        except TickerAlreadyMappedError as exc:
            _say("warning", shared_ticker_message(exc))
            st.rerun()
        invalidate_view_caches()
        _say(
            "success",
            f"{display_name or isin} now values off {match.symbol}. "
            f"Rewrote {rewritten} transaction(s).",
        )
        st.rerun()

    if use_last_clicked:
        if session_id:
            ignore_in_session(
                isin, display_name, session_id, get_isin_map_repo(), get_sync_store()
            )
        else:
            repo = get_isin_map_repo()
            repo.save(apply_ignore(repo.load(), isin, display_name))
        invalidate_view_caches()
        _say(
            "success",
            f"{display_name or isin} is now valued at its last trade price.",
        )
        st.rerun()

    suggested = (
        suggest_kind(mapping.ticker)
        if mapping and mapping.status == "mapped" and mapping.ticker
        else None
    )
    selected_kind = render_kind_control(
        isin, mapping, key_prefix=key_prefix, suggested=suggested
    )
    stored_kind = mapping.instrument_kind if mapping else None
    if selected_kind is not None and selected_kind != stored_kind:
        if session_id:
            set_kind_in_session(
                isin,
                selected_kind,
                session_id,
                get_isin_map_repo(),
                get_sync_store(),
                name=display_name,
            )
        else:
            repo = get_isin_map_repo()
            repo.save(apply_kind(repo.load(), isin, selected_kind, name=display_name))
        invalidate_view_caches()
        _say(
            "success",
            f"{display_name or isin} is taxed as "
            f"{KIND_LABEL.get(selected_kind, selected_kind.value)}.",
        )
        st.rerun()

    if open_shares > 0:
        write_off_choice = render_write_off_control(
            isin,
            display_name,
            open_shares,
            key_prefix=key_prefix,
            state_key=_WRITE_OFF_STATE_KEY,
            today=date.today(),
        )
        if write_off_choice is not None:
            shares, on_date = write_off_choice
            try:
                if session_id:
                    write_off_in_session(
                        isin,
                        display_name,
                        shares,
                        on_date,
                        session_id,
                        get_repository(),
                        get_isin_map_repo(),
                        get_sync_store(),
                    )
                else:
                    write_off(
                        isin,
                        display_name,
                        shares,
                        on_date,
                        get_isin_map_repo(),
                        get_repository(),
                    )
            except WriteOffNotPossible as exc:
                _say("warning", str(exc))
                st.rerun()
            invalidate_view_caches()
            kind = mapping.instrument_kind if mapping else None
            kind_text = KIND_LABEL.get(kind, kind.value) if kind else "its tax kind"
            _say(
                "success",
                f"Wrote off {format_shares(shares)} {display_name or isin} at €0 on "
                f"{on_date.isoformat()}. The loss shows on the Tax Dashboard under "
                f"{kind_text}.",
            )
            st.rerun()

    if context == "all_instruments":
        removed = render_remove_control(
            isin, display_name, key_prefix=key_prefix, state_key=_REMOVE_STATE_KEY
        )
        if removed:
            repo = get_isin_map_repo()
            current = repo.load()
            repo.save(
                IsinMapDocument(
                    version=current.version,
                    entries={k: v for k, v in current.entries.items() if k != isin},
                )
            )
            invalidate_view_caches()
            _say("success", f"Removed {display_name or isin} and its transactions.")
            st.rerun()
