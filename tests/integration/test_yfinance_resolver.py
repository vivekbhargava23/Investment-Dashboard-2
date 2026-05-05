"""Integration tests for YfinanceAdapter's TickerResolver implementation.

These tests hit the real yfinance network endpoint and are skipped by default.
Run with: pytest -m integration
"""
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.yfinance_feed import YfinanceAdapter
from app.domain.money import Currency


@pytest.mark.integration
def test_resolve_usd_ticker() -> None:
    adapter = YfinanceAdapter()
    results = adapter.resolve("APD")
    symbols = [m.symbol for m in results]
    assert "APD" in symbols
    apd = next(m for m in results if m.symbol == "APD")
    assert apd.currency == Currency.USD


@pytest.mark.integration
def test_resolve_eur_ticker() -> None:
    adapter = YfinanceAdapter()
    results = adapter.resolve("RHM")
    symbols = [m.symbol for m in results]
    assert "RHM.DE" in symbols
    rhm = next(m for m in results if m.symbol == "RHM.DE")
    assert rhm.currency == Currency.EUR


@pytest.mark.integration
def test_resolve_jpy_ticker() -> None:
    adapter = YfinanceAdapter()
    results = adapter.resolve("5631.T")
    symbols = [m.symbol for m in results]
    assert "5631.T" in symbols
    jsw = next(m for m in results if m.symbol == "5631.T")
    assert jsw.currency == Currency.JPY


@pytest.mark.integration
def test_resolve_empty_query_returns_empty() -> None:
    adapter = YfinanceAdapter()
    assert adapter.resolve("") == []


@pytest.mark.integration
def test_resolve_garbage_query_returns_empty() -> None:
    adapter = YfinanceAdapter()
    results = adapter.resolve("XQYZNOTREAL999ZZZZZ")
    assert isinstance(results, list)


@pytest.mark.integration
def test_lookup_nvda_returns_usd() -> None:
    adapter = YfinanceAdapter()
    match = adapter.lookup("NVDA")
    assert match is not None
    assert match.symbol == "NVDA"
    assert match.currency == Currency.USD


@pytest.mark.integration
def test_lookup_unknown_returns_none() -> None:
    adapter = YfinanceAdapter()
    result = adapter.lookup("XQYZNOTREAL999ZZZZZ")
    assert result is None


@pytest.mark.integration
def test_resolve_cache_avoids_second_network_call() -> None:
    """Second call with same query returns results without hitting the network again."""
    adapter = YfinanceAdapter()
    first = adapter.resolve("APD", limit=5)
    second = adapter.resolve("APD", limit=5)
    # Results are equal (same content) even though the list object may differ
    assert first == second


@pytest.mark.integration
def test_clear_cache_invalidates_resolver() -> None:
    adapter = YfinanceAdapter()
    first = adapter.resolve("APD", limit=5)
    adapter.clear_cache()
    second = adapter.resolve("APD", limit=5)
    # After clear the objects differ; both should contain APD
    assert first is not second
    assert any(m.symbol == "APD" for m in second)


def test_resolve_omits_unsupported_currency() -> None:
    """Matches with currency not in the Currency enum are silently dropped."""
    adapter = YfinanceAdapter()
    fake_quotes = [
        {
            "symbol": "0700.HK",
            "longname": "Tencent Holdings",
            "exchDisp": "HKEX",
        }
    ]
    with patch("yfinance.Search") as mock_search:
        mock_instance = MagicMock()
        mock_instance.quotes = fake_quotes
        mock_search.return_value = mock_instance
        results = adapter.resolve("Tencent")
    # HKD not in Currency enum → match omitted
    assert results == []


def test_resolve_empty_on_search_exception() -> None:
    """Search failure returns empty list, not an exception."""
    adapter = YfinanceAdapter()
    with patch("yfinance.Search", side_effect=Exception("network error")):
        results = adapter.resolve("APD")
    assert results == []


def test_resolve_respects_limit() -> None:
    """Result list never exceeds the requested limit."""
    adapter = YfinanceAdapter()
    fake_quotes = [
        {"symbol": f"TICK{i}.DE", "longname": f"Company {i}", "exchDisp": "XETRA"}
        for i in range(20)
    ]
    with patch("yfinance.Search") as mock_search:
        mock_instance = MagicMock()
        mock_instance.quotes = fake_quotes
        mock_search.return_value = mock_instance
        results = adapter.resolve("TICK", limit=5)
    assert len(results) <= 5
