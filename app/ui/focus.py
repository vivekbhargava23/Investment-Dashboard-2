"""Persistent "focus ticker" shared across pages.

One symbol is in focus at a time. It lives in Streamlit session state under
``_FOCUS_KEY`` and is mirrored to the ``?ticker=`` query param so it survives a
full page rerun and is shareable via URL. Pages read it with
:func:`get_focus_ticker` and update it with :func:`set_focus_ticker`.

:func:`resolve_initial_focus` is pure (no Streamlit) so it can be unit-tested:
it decides the starting focus from the available sources by precedence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import streamlit as st

_FOCUS_KEY = "focus_ticker"
_FOCUS_QUERY_PARAM = "ticker"


def _normalize(symbol: str | None) -> str | None:
    """Upper-case and strip a symbol; treat blank/None as "no focus"."""
    if symbol is None:
        return None
    cleaned = symbol.strip().upper()
    return cleaned or None


def resolve_initial_focus(
    session: Mapping[str, object],
    query: Mapping[str, object],
    owned: Sequence[str],
) -> str | None:
    """Decide the starting focus ticker by precedence.

    Precedence: ``query`` (``?ticker=``) > ``session`` state > first ``owned``
    position > ``None``. Symbols are normalized (stripped, upper-cased); blanks
    are ignored at every level. Pure — no Streamlit access — so it is unit
    testable.
    """
    from_query = _normalize(_as_str(query.get(_FOCUS_QUERY_PARAM)))
    if from_query is not None:
        return from_query

    from_session = _normalize(_as_str(session.get(_FOCUS_KEY)))
    if from_session is not None:
        return from_session

    for symbol in owned:
        normalized = _normalize(symbol)
        if normalized is not None:
            return normalized

    return None


def _as_str(value: object) -> str | None:
    """Coerce a query-param/session value to a single string, or None.

    Streamlit query params can surface as a list when a key repeats; take the
    first element in that case.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and value:
        first = value[0]
        return first if isinstance(first, str) else None
    return None


def get_focus_ticker() -> str | None:
    """Return the current focus ticker from session state, or None."""
    return _normalize(_as_str(st.session_state.get(_FOCUS_KEY)))


def set_focus_ticker(symbol: str | None) -> None:
    """Set the focus ticker in session state and mirror it to ``?ticker=``.

    Passing a blank or None symbol clears the focus and removes the query param.
    """
    normalized = _normalize(symbol)
    if normalized is None:
        st.session_state.pop(_FOCUS_KEY, None)
        if _FOCUS_QUERY_PARAM in st.query_params:
            del st.query_params[_FOCUS_QUERY_PARAM]
        return
    st.session_state[_FOCUS_KEY] = normalized
    st.query_params[_FOCUS_QUERY_PARAM] = normalized
