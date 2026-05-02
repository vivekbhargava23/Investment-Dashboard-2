import pytest
from unittest.mock import patch, MagicMock
from app.services.ticker_search import search_tickers, resolve_unknown_ticker

@pytest.fixture
def mock_catalogue():
    return [
        {"ticker": "AAPL", "name": "Apple Inc."},
        {"ticker": "MSFT", "name": "Microsoft Corporation"},
        {"ticker": "ASML", "name": "ASML Holding N.V."},
        {"ticker": "AMD", "name": "Advanced Micro Devices"},
        {"ticker": "AMZN", "name": "Amazon.com, Inc."}
    ]

def test_search_tickers_exact_match_first(mock_catalogue):
    with patch("app.services.ticker_search._load_catalogue", return_value=mock_catalogue):
        # Query 'AMD' - should be exact match
        results = search_tickers("AMD")
        assert len(results) >= 1
        assert results[0]["ticker"] == "AMD"

def test_search_tickers_substring(mock_catalogue):
    with patch("app.services.ticker_search._load_catalogue", return_value=mock_catalogue):
        # Query 'soft' should find Microsoft
        results = search_tickers("soft")
        assert any(r["ticker"] == "MSFT" for r in results)
        
        # Query 'A' should find AAPL, ASML, AMD, AMZN
        results = search_tickers("A")
        assert len(results) >= 4
        # AAPL (exact match ranking if query was AAPL, but here starts-with)

def test_resolve_unknown_ticker_local(mock_catalogue):
    with patch("app.services.ticker_search._load_catalogue", return_value=mock_catalogue):
        resolved = resolve_unknown_ticker("AAPL")
        assert resolved is not None
        assert resolved["name"] == "Apple Inc."

@patch("app.services.ticker_search.lookup_name")
def test_resolve_unknown_ticker_remote(mock_lookup, mock_catalogue):
    with patch("app.services.ticker_search._load_catalogue", return_value=mock_catalogue):
        mock_lookup.return_value = "Test Remote Corp"
        
        # Ticker not in mock catalogue
        resolved = resolve_unknown_ticker("UNKNOWN")
        
        assert resolved is not None
        assert resolved["ticker"] == "UNKNOWN"
        assert resolved["name"] == "Test Remote Corp"
        mock_lookup.assert_called_once_with("UNKNOWN")

def test_search_tickers_empty():
    results = search_tickers("")
    assert results == []
