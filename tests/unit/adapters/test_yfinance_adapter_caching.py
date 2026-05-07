from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.adapters.yfinance_feed import YfinanceAdapter
from app.domain.money import Currency, Money


@pytest.fixture
def adapter() -> YfinanceAdapter:
    return YfinanceAdapter(current_ttl_seconds=60)


def test_current_price_cached_within_ttl(adapter: YfinanceAdapter) -> None:
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info = {"lastPrice": 100.0}

        # First call
        p1 = adapter.get_current_price("NVDA")
        # Second call
        p2 = adapter.get_current_price("NVDA")

        assert p1 == p2 == Money(amount=Decimal("100"), currency=Currency.USD)
        assert mock_ticker.call_count == 1


def test_current_price_refetched_after_ttl(adapter: YfinanceAdapter) -> None:
    adapter.current_ttl_seconds = 60
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info = {"lastPrice": 100.0}

        with patch("time.monotonic") as mock_time:
            mock_time.return_value = 1000.0
            adapter.get_current_price("NVDA")
            
            # Advance time beyond TTL
            mock_time.return_value = 1100.0
            adapter.get_current_price("NVDA")

        assert mock_ticker.call_count == 2


def test_historical_never_expires(adapter: YfinanceAdapter) -> None:
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        df = pd.DataFrame({"Close": [100.0]}, index=[pd.Timestamp("2024-01-02")])
        mock_instance.history.return_value = df

        d = date(2024, 1, 2)
        adapter.get_historical_close("NVDA", d)
        adapter.get_historical_close("NVDA", d)

        assert mock_ticker.call_count == 1


def test_clear_cache_invalidates_everything(adapter: YfinanceAdapter) -> None:
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info = {"lastPrice": 100.0}
        df = pd.DataFrame({"Close": [100.0]}, index=[pd.Timestamp("2024-01-02")])
        mock_instance.history.return_value = df

        adapter.get_current_price("NVDA")
        adapter.get_historical_close("NVDA", date(2024, 1, 2))

        adapter.clear_cache()

        adapter.get_current_price("NVDA")
        adapter.get_historical_close("NVDA", date(2024, 1, 2))

        # Each call creates a new Ticker instance
        assert mock_ticker.call_count == 4


def test_different_tickers_cached_independently(adapter: YfinanceAdapter) -> None:
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info = {"lastPrice": 100.0}

        adapter.get_current_price("NVDA")
        adapter.get_current_price("MU")

        assert mock_ticker.call_count == 2


def test_cache_key_format(adapter: YfinanceAdapter) -> None:
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info = {"lastPrice": 100.0}
        df = pd.DataFrame({"Close": [100.0]}, index=[pd.Timestamp("2024-01-02")])
        mock_instance.history.return_value = df

        adapter.get_current_price("NVDA")
        adapter.get_historical_close("NVDA", date(2024, 1, 2))

        assert "price:NVDA" in adapter._current_cache
        assert "price:NVDA:2024-01-02" in adapter._historical_cache


def test_resolve_does_not_fetch_recent_prices(adapter: YfinanceAdapter) -> None:
    """Search results are lightweight; exact lookup can enrich prices separately."""
    fake_quotes = [
        {"symbol": "APD", "longname": "Air Products", "exchDisp": "NYSE"},
    ]
    with (
        patch("yfinance.Search") as mock_search,
        patch("yfinance.Ticker") as mock_ticker,
    ):
        mock_instance = MagicMock()
        mock_instance.quotes = fake_quotes
        mock_search.return_value = mock_instance

        results = adapter.resolve("APD", limit=5)

    assert len(results) == 1
    assert results[0].recent_price is None
    mock_ticker.assert_not_called()
