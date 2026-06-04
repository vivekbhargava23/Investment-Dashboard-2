"""Focus ticker — a single shared ticker selection that persists across pages."""

from __future__ import annotations

import streamlit as st


def resolve_initial_focus(
    session: dict[str, object],
    query: str | None,
    owned: list[str],
) -> str | None:
    """Return the highest-priority available ticker from three sources.

    Precedence: query-param > session state > first owned ticker > None.
    Pure function — no side effects; safe to call in tests without Streamlit.
    """
    if query:
        return query
    session_focus = session.get("focus_ticker")
    if session_focus:
        return str(session_focus)
    if owned:
        return owned[0]
    return None


def get_focus_ticker() -> str | None:
    """Return the current focus ticker from session state, or None."""
    val = st.session_state.get("focus_ticker")
    return str(val) if val else None


def set_focus_ticker(symbol: str) -> None:
    """Persist the focus ticker in session state and URL query params."""
    st.session_state["focus_ticker"] = symbol
    st.query_params["ticker"] = symbol
