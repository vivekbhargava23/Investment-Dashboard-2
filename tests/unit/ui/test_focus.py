"""Unit tests for the focus ticker module (TICKET-RD0)."""
from unittest.mock import patch

from app.ui.focus import get_focus_ticker, resolve_initial_focus, set_focus_ticker

# ── resolve_initial_focus precedence ──────────────────────────────────────────

def test_resolve_query_wins_over_session_and_owned() -> None:
    session = {"focus_ticker": "MSFT"}
    owned = ["AAPL", "NVDA"]
    assert resolve_initial_focus(session, "RHM.DE", owned) == "RHM.DE"


def test_resolve_session_wins_over_owned() -> None:
    session = {"focus_ticker": "MSFT"}
    owned = ["AAPL", "NVDA"]
    assert resolve_initial_focus(session, None, owned) == "MSFT"


def test_resolve_first_owned_wins_when_no_query_or_session() -> None:
    assert resolve_initial_focus({}, None, ["AAPL", "NVDA"]) == "AAPL"


def test_resolve_returns_none_when_nothing_available() -> None:
    assert resolve_initial_focus({}, None, []) is None


def test_resolve_empty_string_query_does_not_win() -> None:
    # Empty string is falsy — session should win, not the empty query
    session = {"focus_ticker": "MSFT"}
    assert resolve_initial_focus(session, "", ["AAPL"]) == "MSFT"


def test_resolve_none_query_does_not_win() -> None:
    session = {"focus_ticker": "TSLA"}
    assert resolve_initial_focus(session, None, []) == "TSLA"


# ── query-param round-trip ────────────────────────────────────────────────────

def test_resolve_initial_focus_query_param_round_trip() -> None:
    # Simulates: user lands on /?ticker=NVDA with no prior session
    result = resolve_initial_focus({}, "NVDA", [])
    assert result == "NVDA"

    # Simulate that result was written to session; subsequent call uses session
    session = {"focus_ticker": result}
    assert resolve_initial_focus(session, None, []) == "NVDA"


# ── get_focus_ticker ──────────────────────────────────────────────────────────

def test_get_focus_ticker_returns_none_when_not_set() -> None:
    with patch("app.ui.focus.st") as mock_st:
        mock_st.session_state.get.return_value = None
        assert get_focus_ticker() is None


def test_get_focus_ticker_returns_string_when_set() -> None:
    with patch("app.ui.focus.st") as mock_st:
        mock_st.session_state.get.return_value = "AAPL"
        assert get_focus_ticker() == "AAPL"


def test_get_focus_ticker_coerces_to_str() -> None:
    # Defensively handles non-string values stored in session
    with patch("app.ui.focus.st") as mock_st:
        mock_st.session_state.get.return_value = 42
        result = get_focus_ticker()
        assert result == "42"
        assert isinstance(result, str)


# ── set_focus_ticker ──────────────────────────────────────────────────────────

def test_set_focus_ticker_writes_session_state_and_query_params() -> None:
    with patch("app.ui.focus.st") as mock_st:
        mock_st.session_state = {}
        mock_st.query_params = {}
        set_focus_ticker("NVDA")
        assert mock_st.session_state["focus_ticker"] == "NVDA"
        assert mock_st.query_params["ticker"] == "NVDA"


def test_set_focus_ticker_overwrites_previous_value() -> None:
    with patch("app.ui.focus.st") as mock_st:
        mock_st.session_state = {"focus_ticker": "AAPL"}
        mock_st.query_params = {"ticker": "AAPL"}
        set_focus_ticker("MSFT")
        assert mock_st.session_state["focus_ticker"] == "MSFT"
        assert mock_st.query_params["ticker"] == "MSFT"
