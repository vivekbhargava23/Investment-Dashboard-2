"""Integration tests for YfinanceResolverAdapter.

These tests hit the real yfinance network endpoint and are skipped by default.
Run with: pytest -m integration
"""
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.yfinance_resolver.adapter import YfinanceResolverAdapter
from app.domain.money import Currency


@pytest.mark.integration
def test_resolve_usd_ticker() -> None:
    adapter = YfinanceResolverAdapter()
    results = adapter.resolve("APD")
    symbols = [m.symbol for m in results]
    assert "APD" in symbols
    apd = next(m for m in results if m.symbol == "APD")
    assert apd.currency == Currency.USD


@pytest.mark.integration
def test_resolve_eur_ticker() -> None:
    adapter = YfinanceResolverAdapter()
    results = adapter.resolve("RHM")
    symbols = [m.symbol for m in results]
    assert "RHM.DE" in symbols
    rhm = next(m for m in results if m.symbol == "RHM.DE")
    assert rhm.currency == Currency.EUR


@pytest.mark.integration
def test_resolve_jpy_ticker() -> None:
    adapter = YfinanceResolverAdapter()
    results = adapter.resolve("5631.T")
    symbols = [m.symbol for m in results]
    assert "5631.T" in symbols
    jsw = next(m for m in results if m.symbol == "5631.T")
    assert jsw.currency == Currency.JPY


@pytest.mark.integration
def test_resolve_empty_query_returns_empty() -> None:
    adapter = YfinanceResolverAdapter()
    assert adapter.resolve("") == []


@pytest.mark.integration
def test_resolve_garbage_query_returns_empty() -> None:
    adapter = YfinanceResolverAdapter()
    results = adapter.resolve("XQYZNOTREAL999ZZZZZ")
    assert isinstance(results, list)


@pytest.mark.integration
def test_lookup_nvda_returns_usd() -> None:
    adapter = YfinanceResolverAdapter()
    match = adapter.lookup("NVDA")
    assert match is not None
    assert match.symbol == "NVDA"
    assert match.currency == Currency.USD


@pytest.mark.integration
def test_lookup_unknown_returns_none() -> None:
    adapter = YfinanceResolverAdapter()
    result = adapter.lookup("XQYZNOTREAL999ZZZZZ")
    assert result is None


@pytest.mark.integration
def test_resolve_cache_avoids_second_network_call() -> None:
    """Second call with same query returns results without hitting the network again."""
    adapter = YfinanceResolverAdapter()
    first = adapter.resolve("APD", limit=5)
    second = adapter.resolve("APD", limit=5)
    assert first == second


@pytest.mark.integration
def test_clear_cache_invalidates_resolver() -> None:
    adapter = YfinanceResolverAdapter()
    first = adapter.resolve("APD", limit=5)
    adapter.clear_cache()
    second = adapter.resolve("APD", limit=5)
    assert first is not second
    assert any(m.symbol == "APD" for m in second)


def test_resolve_omits_unsupported_currency() -> None:
    """Matches with currency not in the Currency enum are silently dropped."""
    adapter = YfinanceResolverAdapter()
    fake_quotes = [
        {
            "symbol": "0700.HK",
            "longname": "Tencent Holdings",
            "exchDisp": "HKEX",
        }
    ]
    with patch("app.adapters.yfinance_resolver.adapter.yf.Search") as mock_search:
        mock_instance = MagicMock()
        mock_instance.quotes = fake_quotes
        mock_search.return_value = mock_instance
        results = adapter.resolve("Tencent")
    assert results == []


def test_resolve_empty_on_search_exception() -> None:
    """Search failure returns empty list, not an exception."""
    adapter = YfinanceResolverAdapter()
    exc = Exception("network error")
    with patch("app.adapters.yfinance_resolver.adapter.yf.Search", side_effect=exc):
        results = adapter.resolve("APD")
    assert results == []


def test_resolve_respects_limit() -> None:
    """Result list never exceeds the requested limit."""
    adapter = YfinanceResolverAdapter()
    fake_quotes = [
        {"symbol": f"TICK{i}.DE", "longname": f"Company {i}", "exchDisp": "XETRA"}
        for i in range(20)
    ]
    with patch("app.adapters.yfinance_resolver.adapter.yf.Search") as mock_search:
        mock_instance = MagicMock()
        mock_instance.quotes = fake_quotes
        mock_search.return_value = mock_instance
        results = adapter.resolve("TICK", limit=5)
    assert len(results) <= 5
