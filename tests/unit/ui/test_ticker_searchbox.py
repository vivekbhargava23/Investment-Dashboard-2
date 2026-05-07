"""Unit tests for the ticker searchbox component helpers. Zero Streamlit runtime needed."""
import logging

import pytest

from app.domain.money import Currency
from app.ports.ticker_resolver import TickerMatch
from app.ui.components.ticker_searchbox import _format_label, _search_callback_for
from tests.fakes.ticker_resolver import FakeTickerResolver


def _make_match(
    symbol: str = "APD",
    name: str = "Air Products",
    exchange: str = "NYSE",
    currency: Currency = Currency.USD,
) -> TickerMatch:
    return TickerMatch(symbol=symbol, name=name, exchange=exchange, currency=currency)


# ---------------------------------------------------------------------------
# _search_callback short-circuits on empty / single-char query
# ---------------------------------------------------------------------------

def test_empty_query_returns_empty() -> None:
    fake = FakeTickerResolver([_make_match()])
    callback = _search_callback_for(fake)
    assert callback("") == []
    assert fake.resolve_call_count == 0


def test_empty_query_returns_pinned_matches() -> None:
    pinned = _make_match(symbol="NVDA", name="NVIDIA")
    fake = FakeTickerResolver([_make_match()])
    callback = _search_callback_for(fake, (pinned,))

    assert callback("") == [(_format_label(pinned), pinned)]
    assert fake.resolve_call_count == 0


def test_single_char_returns_empty() -> None:
    fake = FakeTickerResolver([_make_match()])
    callback = _search_callback_for(fake)
    assert callback("A") == []
    assert fake.resolve_call_count == 0


# ---------------------------------------------------------------------------
# Label formatting
# ---------------------------------------------------------------------------

def test_search_callback_formats_label_correctly() -> None:
    m = _make_match(symbol="APD", name="Air Products", exchange="NYSE", currency=Currency.USD)
    fake = FakeTickerResolver([m])
    callback = _search_callback_for(fake)
    results = callback("AP")
    assert len(results) == 1
    label, value = results[0]
    assert label == "APD — Air Products (NYSE, USD)"
    assert value == m


def test_search_callback_typed_query_uses_resolver_results_without_pinned_prefix() -> None:
    pinned = _make_match(symbol="NVDA", name="NVIDIA")
    apd = _make_match(symbol="APD", name="Air Products")
    other = _make_match(symbol="AAPL", name="Apple")
    fake = FakeTickerResolver([apd, other])
    callback = _search_callback_for(fake, (pinned,))

    results = callback("AP")

    assert [value.symbol for _, value in results] == ["APD", "AAPL"]


def test_format_label_all_currencies() -> None:
    for currency in Currency:
        m = _make_match(currency=currency)
        label = _format_label(m)
        assert currency.value in label


# ---------------------------------------------------------------------------
# Exception swallowing
# ---------------------------------------------------------------------------

def test_search_callback_swallows_resolver_exception(caplog: pytest.LogCaptureFixture) -> None:
    class RaisingResolver:
        def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]:
            raise RuntimeError("network down")

        def lookup(self, symbol: str) -> TickerMatch | None:
            return None

        def clear_cache(self) -> None:
            pass

    callback = _search_callback_for(RaisingResolver())  # type: ignore[arg-type]
    with caplog.at_level(logging.WARNING):
        result = callback("AP")
    assert result == []
    assert any("Ticker resolver error" in r.message for r in caplog.records)
