"""Catalysts page — portfolio-wide upcoming catalysts timeline (TICKET-PANEL-2).

A book-wide view of upcoming catalysts across all holdings plus portfolio-scope
macro events, rendered as the horizontal timeline component in ``portfolio`` mode.
Held tickers come from the FIFO open positions (no live price fetch needed — only
the held set matters here). Per-position catalysts live on the Company Deep Dive.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from app.config import get_settings
from app.domain.catalysts import CatalystEvent
from app.domain.fifo import compute_positions
from app.services.catalysts import get_portfolio_catalysts
from app.ui.cache_keys import file_mtime_key, transactions_signature
from app.ui.components.catalysts_timeline import render_catalysts_timeline
from app.ui.wiring import get_catalysts_repo, get_repository


@st.cache_data(ttl=60, show_spinner=False)
def _cached_portfolio_catalysts(
    tx_sig: str, as_of_iso: str, catalysts_sig: str
) -> list[CatalystEvent]:
    """Upcoming catalysts for the held set + book-wide events, cached once.

    Keyed on the transactions signature (held tickers), the `as_of` date, and the
    catalysts file's mtime so a curated edit invalidates the cache without a manual
    refresh. Held tickers derive from FIFO positions, so this needs no network.
    """
    transactions = get_repository().load_all()
    as_of = date.fromisoformat(as_of_iso)
    held = [
        ticker
        for ticker, position in compute_positions(transactions, as_of).items()
        if position.open_shares > 0
    ]
    return get_portfolio_catalysts(held, as_of=as_of, repo=get_catalysts_repo())


def render() -> None:
    st.caption(
        "Upcoming catalysts across your holdings, plus book-wide macro events. "
        "Hover a marker for detail."
    )

    transactions = get_repository().load_all()
    sig = transactions_signature(transactions)
    today = date.today()

    catalysts_doc = get_catalysts_repo().load()
    catalysts_sig = file_mtime_key(get_settings().catalysts_json_path)
    events = _cached_portfolio_catalysts(sig, today.isoformat(), catalysts_sig)

    render_catalysts_timeline(
        events, as_of=today, mode="portfolio", updated=catalysts_doc.updated
    )
