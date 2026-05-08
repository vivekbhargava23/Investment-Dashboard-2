"""Smoke tests for the Research page — call-shape tests using mocked st + service layer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.domain.market_data import ChartPeriod, OhlcUnavailableError
from app.ui.pages import research
from tests.fakes.ohlc import FAKE_SERIES_NVDA_6MO
from tests.fakes.ticker_resolver import FAKE_TICKER_NVDA, FakeTickerResolver

_TWO_COLS = [MagicMock(), MagicMock()]
_THREE_COLS = [MagicMock(), MagicMock(), MagicMock()]


def _col_side_effects(*shapes: int) -> list[list[MagicMock]]:
    """Return a list of mock column lists for st.columns side_effect."""
    return [[MagicMock() for _ in range(n)] for n in shapes]


# ── Empty state ───────────────────────────────────────────────────────────────

def test_empty_state_shows_info_when_no_match() -> None:
    """When searchbox returns None, st.info is called with the expected prompt."""
    with (
        patch("app.ui.pages.research.st") as mock_st,
        patch("app.ui.pages.research.render_ticker_searchbox", return_value=None),
        patch("app.ui.pages.research.get_ticker_resolver", return_value=FakeTickerResolver()),
        patch("app.ui.pages.research.get_ohlc_data_provider", return_value=MagicMock()),
    ):
        mock_st.session_state = {}
        mock_st.radio.return_value = ChartPeriod.SIX_MONTH
        # input row (2); second call for quick-pick buttons uses zip → 2 is fine
        mock_st.columns.side_effect = _col_side_effects(2, 5)
        research.render()

    info_calls = [str(c) for c in mock_st.info.call_args_list]
    assert any("ticker" in s.lower() or "symbol" in s.lower() for s in info_calls)


# ── Header region ─────────────────────────────────────────────────────────────

def test_header_renders_symbol_and_name_when_match_set() -> None:
    """When searchbox returns a match, the header markdown contains the symbol and name."""
    markdown_calls: list[str] = []

    with (
        patch("app.ui.pages.research.st") as mock_st,
        patch("app.ui.pages.research.render_ticker_searchbox", return_value=FAKE_TICKER_NVDA),
        patch("app.ui.pages.research.get_ticker_resolver", return_value=FakeTickerResolver()),
        patch("app.ui.pages.research.get_ohlc_data_provider", return_value=MagicMock()),
        patch("app.ui.pages.research.get_ohlc_history", return_value=FAKE_SERIES_NVDA_6MO),
        patch("app.ui.pages.research.render_candlestick"),
    ):
        mock_st.session_state = {}
        mock_st.radio.return_value = ChartPeriod.SIX_MONTH
        # input row (2), metrics row (3), action row (3)
        mock_st.columns.side_effect = _col_side_effects(2, 3, 3)
        mock_st.markdown.side_effect = lambda s, **kw: markdown_calls.append(str(s))
        research.render()

    combined = "\n".join(markdown_calls)
    assert "NVDA" in combined
    assert "NVIDIA" in combined


# ── Chart unavailable ─────────────────────────────────────────────────────────

def test_warning_shown_when_ohlc_unavailable() -> None:
    """On OhlcUnavailableError, st.warning is called with the reason; no crash."""
    with (
        patch("app.ui.pages.research.st") as mock_st,
        patch("app.ui.pages.research.render_ticker_searchbox", return_value=FAKE_TICKER_NVDA),
        patch("app.ui.pages.research.get_ticker_resolver", return_value=FakeTickerResolver()),
        patch("app.ui.pages.research.get_ohlc_data_provider", return_value=MagicMock()),
        patch(
            "app.ui.pages.research.get_ohlc_history",
            side_effect=OhlcUnavailableError("no data for NVDA"),
        ),
    ):
        mock_st.session_state = {}
        mock_st.radio.return_value = ChartPeriod.SIX_MONTH
        # input row (2), action row (3) — no metrics row since series is None
        mock_st.columns.side_effect = _col_side_effects(2, 3)
        research.render()

    mock_st.warning.assert_called_once()
    warning_text = str(mock_st.warning.call_args)
    assert "unavailable" in warning_text.lower() or "NVDA" in warning_text


# ── Period selector ───────────────────────────────────────────────────────────

def test_period_selector_default_is_six_month() -> None:
    """The radio default index must map to SIX_MONTH (index 4 in ChartPeriod)."""
    assert list(ChartPeriod).index(ChartPeriod.SIX_MONTH) == 4


def test_period_labels_cover_all_periods() -> None:
    """Every ChartPeriod must have a short label in the module mapping."""
    labels = research._PERIOD_LABELS
    for period in ChartPeriod:
        assert period in labels, f"Missing label for {period}"
    assert labels[ChartPeriod.ONE_DAY] == "1D"
    assert labels[ChartPeriod.YEAR_TO_DATE] == "YTD"


# ── Simulate buy ─────────────────────────────────────────────────────────────

def test_simulate_buy_sets_session_state_and_navigates() -> None:
    """Clicking Simulate buy sets simulator_default_ticker and navigates to simulator page."""
    session_state: dict = {}

    with (
        patch("app.ui.pages.research.st") as mock_st,
        patch("app.ui.pages.research.render_ticker_searchbox", return_value=FAKE_TICKER_NVDA),
        patch("app.ui.pages.research.get_ticker_resolver", return_value=FakeTickerResolver()),
        patch("app.ui.pages.research.get_ohlc_data_provider", return_value=MagicMock()),
        patch("app.ui.pages.research.get_ohlc_history", return_value=FAKE_SERIES_NVDA_6MO),
        patch("app.ui.pages.research.render_candlestick"),
    ):
        mock_st.session_state = session_state
        mock_st.radio.return_value = ChartPeriod.SIX_MONTH
        # input row (2), metrics row (3), action row (3)
        mock_st.columns.side_effect = _col_side_effects(2, 3, 3)
        # Simulate the "Simulate buy" button being clicked
        mock_st.button.side_effect = lambda label, **kw: label == "Simulate buy"
        research.render()

    assert session_state.get("simulator_default_ticker") == "NVDA"
    assert session_state.get("current_page") == "simulator"
