from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.adapters.yfinance_price.adapter import YfinancePriceAdapter
from app.adapters.yfinance_resolver.adapter import YfinanceResolverAdapter
from app.domain.money import Currency, Money


@pytest.fixture
def price_adapter() -> YfinancePriceAdapter:
    return YfinancePriceAdapter(current_ttl_seconds=60)


@pytest.fixture
def resolver_adapter() -> YfinanceResolverAdapter:
    return YfinanceResolverAdapter()


def test_current_price_cached_within_ttl(price_adapter: YfinancePriceAdapter) -> None:
    with patch("app.adapters.yfinance_price.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info = {"lastPrice": 100.0}

        p1 = price_adapter.get_current_price("NVDA")
        p2 = price_adapter.get_current_price("NVDA")

        assert p1 == p2 == Money(amount=Decimal("100"), currency=Currency.USD)
        assert mock_ticker.call_count == 1


def test_current_price_refetched_after_ttl(price_adapter: YfinancePriceAdapter) -> None:
    price_adapter.current_ttl_seconds = 60
    with patch("app.adapters.yfinance_price.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info = {"lastPrice": 100.0}

        with patch("app.adapters.yfinance_price.adapter.time.monotonic") as mock_time:
            mock_time.return_value = 1000.0
            price_adapter.get_current_price("NVDA")

            mock_time.return_value = 1100.0
            price_adapter.get_current_price("NVDA")

        assert mock_ticker.call_count == 2


def test_historical_never_expires(price_adapter: YfinancePriceAdapter) -> None:
    with patch("app.adapters.yfinance_price.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        df = pd.DataFrame({"Close": [100.0]}, index=[pd.Timestamp("2024-01-02")])
        mock_instance.history.return_value = df

        d = date(2024, 1, 2)
        price_adapter.get_historical_close("NVDA", d)
        price_adapter.get_historical_close("NVDA", d)

        assert mock_ticker.call_count == 1


def test_clear_cache_invalidates_everything(price_adapter: YfinancePriceAdapter) -> None:
    with patch("app.adapters.yfinance_price.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info = {"lastPrice": 100.0}
        df = pd.DataFrame({"Close": [100.0]}, index=[pd.Timestamp("2024-01-02")])
        mock_instance.history.return_value = df

        price_adapter.get_current_price("NVDA")
        price_adapter.get_historical_close("NVDA", date(2024, 1, 2))

        price_adapter.clear_cache()

        price_adapter.get_current_price("NVDA")
        price_adapter.get_historical_close("NVDA", date(2024, 1, 2))

        assert mock_ticker.call_count == 4


def test_different_tickers_cached_independently(price_adapter: YfinancePriceAdapter) -> None:
    with patch("app.adapters.yfinance_price.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info = {"lastPrice": 100.0}

        price_adapter.get_current_price("NVDA")
        price_adapter.get_current_price("MU")

        assert mock_ticker.call_count == 2


def test_cache_key_format(price_adapter: YfinancePriceAdapter) -> None:
    with patch("app.adapters.yfinance_price.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info = {"lastPrice": 100.0}
        df = pd.DataFrame({"Close": [100.0]}, index=[pd.Timestamp("2024-01-02")])
        mock_instance.history.return_value = df

        price_adapter.get_current_price("NVDA")
        price_adapter.get_historical_close("NVDA", date(2024, 1, 2))

        assert "price:NVDA" in price_adapter._current_cache
        assert "price:NVDA:2024-01-02" in price_adapter._historical_cache


def test_resolve_does_not_fetch_recent_prices(resolver_adapter: YfinanceResolverAdapter) -> None:
    """Search results are lightweight; exact lookup can enrich prices separately."""
    fake_quotes = [
        {"symbol": "APD", "longname": "Air Products", "exchDisp": "NYSE"},
    ]
    with (
        patch("app.adapters.yfinance_resolver.adapter.yf.Search") as mock_search,
        patch("app.adapters.yfinance_resolver.adapter.yf.Ticker") as mock_ticker,
    ):
        mock_instance = MagicMock()
        mock_instance.quotes = fake_quotes
        mock_search.return_value = mock_instance

        results = resolver_adapter.resolve("APD", limit=5)

    assert len(results) == 1
    assert results[0].recent_price is None
    mock_ticker.assert_not_called()
