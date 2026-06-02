"""Integration tests for FinnhubTickerResolverAdapter. Skipped when FINNHUB_API_KEY unset."""
from __future__ import annotations

import os

import pytest

from app.adapters.ticker_resolver_finnhub.adapter import FinnhubTickerResolverAdapter


def _key() -> str:
    return os.environ.get("FINNHUB_API_KEY", "")


@pytest.mark.integration
def test_resolve_returns_matches_for_apple() -> None:
    if not _key():
        pytest.skip("FINNHUB_API_KEY not set")

    adapter = FinnhubTickerResolverAdapter(api_key=_key())
    results = adapter.resolve("apple", limit=5)

    assert len(results) > 0
    assert any("AAPL" in r.symbol for r in results)


@pytest.mark.integration
def test_resolve_empty_query_returns_empty() -> None:
    if not _key():
        pytest.skip("FINNHUB_API_KEY not set")

    adapter = FinnhubTickerResolverAdapter(api_key=_key())
    assert adapter.resolve("", limit=5) == []


@pytest.mark.integration
def test_lookup_aapl_returns_match() -> None:
    if not _key():
        pytest.skip("FINNHUB_API_KEY not set")

    adapter = FinnhubTickerResolverAdapter(api_key=_key())
    result = adapter.lookup("AAPL")

    assert result is not None
    assert result.symbol.upper() == "AAPL"
    assert result.name


@pytest.mark.integration
def test_lookup_unknown_symbol_returns_none() -> None:
    if not _key():
        pytest.skip("FINNHUB_API_KEY not set")

    adapter = FinnhubTickerResolverAdapter(api_key=_key())
    assert adapter.lookup("XQZNOTAREALTICKERXYZ") is None


@pytest.mark.integration
def test_no_api_key_resolve_returns_empty() -> None:
    adapter = FinnhubTickerResolverAdapter(api_key="")
    assert adapter.resolve("apple", limit=5) == []


@pytest.mark.integration
def test_no_api_key_lookup_returns_none() -> None:
    adapter = FinnhubTickerResolverAdapter(api_key="")
    assert adapter.lookup("AAPL") is None
