"""Tests for the persistent focus-ticker helpers (TICKET-RD0)."""

from __future__ import annotations

import app.ui.focus as focus_mod
from app.ui.focus import resolve_initial_focus

# ── resolve_initial_focus precedence ────────────────────────────────────────


def test_query_wins_over_session_and_owned() -> None:
    result = resolve_initial_focus(
        session={"focus_ticker": "MSFT"},
        query={"ticker": "AAPL"},
        owned=["NVDA"],
    )
    assert result == "AAPL"


def test_session_wins_when_no_query() -> None:
    result = resolve_initial_focus(
        session={"focus_ticker": "MSFT"},
        query={},
        owned=["NVDA"],
    )
    assert result == "MSFT"


def test_first_owned_when_no_query_or_session() -> None:
    result = resolve_initial_focus(session={}, query={}, owned=["NVDA", "AAPL"])
    assert result == "NVDA"


def test_none_when_everything_empty() -> None:
    assert resolve_initial_focus(session={}, query={}, owned=[]) is None


def test_blank_query_falls_through_to_session() -> None:
    result = resolve_initial_focus(
        session={"focus_ticker": "MSFT"},
        query={"ticker": "   "},
        owned=["NVDA"],
    )
    assert result == "MSFT"


def test_symbols_are_normalized() -> None:
    result = resolve_initial_focus(
        session={}, query={"ticker": "  aapl "}, owned=[]
    )
    assert result == "AAPL"


def test_blank_owned_entries_are_skipped() -> None:
    result = resolve_initial_focus(session={}, query={}, owned=["", "  ", "tsla"])
    assert result == "TSLA"


def test_query_param_list_form_takes_first() -> None:
    # Streamlit can surface a repeated query key as a list.
    result = resolve_initial_focus(
        session={}, query={"ticker": ["AAPL", "MSFT"]}, owned=[]
    )
    assert result == "AAPL"


# ── get/set round-trip ───────────────────────────────────────────────────────


class _FakeQueryParams(dict):
    """Minimal stand-in for st.query_params (dict-like)."""


def _install_fake_streamlit(monkeypatch) -> tuple[dict, _FakeQueryParams]:
    session: dict = {}
    query = _FakeQueryParams()

    class _FakeSt:
        session_state = session
        query_params = query

    monkeypatch.setattr(focus_mod, "st", _FakeSt)
    return session, query


def test_set_focus_round_trips_to_session_and_query(monkeypatch) -> None:
    session, query = _install_fake_streamlit(monkeypatch)

    focus_mod.set_focus_ticker("aapl")

    assert session["focus_ticker"] == "AAPL"
    assert query["ticker"] == "AAPL"
    assert focus_mod.get_focus_ticker() == "AAPL"


def test_set_focus_none_clears_session_and_query(monkeypatch) -> None:
    session, query = _install_fake_streamlit(monkeypatch)
    focus_mod.set_focus_ticker("AAPL")

    focus_mod.set_focus_ticker(None)

    assert "focus_ticker" not in session
    assert "ticker" not in query
    assert focus_mod.get_focus_ticker() is None


def test_set_focus_blank_clears(monkeypatch) -> None:
    session, query = _install_fake_streamlit(monkeypatch)
    focus_mod.set_focus_ticker("AAPL")

    focus_mod.set_focus_ticker("   ")

    assert "focus_ticker" not in session
    assert "ticker" not in query


def test_get_focus_none_when_unset(monkeypatch) -> None:
    _install_fake_streamlit(monkeypatch)
    assert focus_mod.get_focus_ticker() is None
