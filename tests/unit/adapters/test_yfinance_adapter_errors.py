from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.adapters.yfinance_feed import YfinanceAdapter
from app.domain.money import Currency
from app.ports.fx_feed import UnsupportedCurrencyPairError
from app.ports.price_feed import PriceUnavailableError, TickerNotFoundError


@pytest.fixture
def adapter() -> YfinanceAdapter:
    return YfinanceAdapter()


def test_yfinance_raises_price_unavailable(adapter: YfinanceAdapter) -> None:
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info.get.side_effect = Exception("network down")

        with pytest.raises(PriceUnavailableError) as excinfo:
            adapter.get_current_price("NVDA")
        
        assert "network down" in str(excinfo.value)
        assert excinfo.value.ticker == "NVDA"


def test_yfinance_returns_nan_ticker_not_found(adapter: YfinanceAdapter) -> None:
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info = {"lastPrice": float("nan")}
        mock_instance.history.return_value = pd.DataFrame()

        with pytest.raises(TickerNotFoundError):
            adapter.get_current_price("NVDA")


def test_historical_expansion_logic(adapter: YfinanceAdapter) -> None:
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        
        # First call (exact date) returns empty
        # Second call (expansion) returns data
        mock_instance.history.side_effect = [
            pd.DataFrame(),
            pd.DataFrame({"Close": [100.0]}, index=[pd.Timestamp("2024-01-01")])
        ]

        p = adapter.get_historical_close("NVDA", date(2024, 1, 2))
        assert p.amount == Decimal("100.0000")
        assert mock_instance.history.call_count == 2


def test_both_windows_empty_raises(adapter: YfinanceAdapter) -> None:
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.history.return_value = pd.DataFrame()

        with pytest.raises(PriceUnavailableError) as excinfo:
            adapter.get_historical_close("NVDA", date(2024, 1, 2))
        
        assert "No historical close near 2024-01-02" in str(excinfo.value)


def test_unsupported_currency_pair(adapter: YfinanceAdapter) -> None:
    # Use a string that isn't EUR or USD if possible, but Currency is an Enum.
    # We can try to pass a string if the type hint isn't enforced at runtime,
    # or just test with what we have.
    with pytest.raises(UnsupportedCurrencyPairError):
        # We can't easily construct an invalid Currency if it's a strict Enum,
        # but we can try to pass something else.
        adapter.get_current_rate(Currency.EUR, "GBP")  # type: ignore
