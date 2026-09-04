"""When the app last valued the book against live prices.

The Sync page states plainly that market values are estimates and when they were
fetched, so the timestamp has to come from whichever page actually fetched them
rather than from a fetch the Sync page starts itself.
"""
from __future__ import annotations

from datetime import datetime

import streamlit as st

_KEY = "last_price_fetch_at"


def record_price_fetch(as_of: datetime) -> None:
    """Remember that live prices were valued as of ``as_of``."""
    st.session_state[_KEY] = as_of


def last_price_fetch() -> datetime | None:
    value = st.session_state.get(_KEY)
    return value if isinstance(value, datetime) else None
