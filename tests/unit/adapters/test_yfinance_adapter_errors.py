from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.adapters.fx_yfinance.adapter import YfinanceLiveFxAdapter
from app.adapters.yfinance_price.adapter import YfinancePriceAdapter
from app.domain.money import Currency
from app.ports.fx_feed import UnsupportedCurrencyPairError
from app.ports.price_feed import PriceUnavailableError, TickerNotFoundError


@pytest.fixture
def price_adapter() -> YfinancePriceAdapter:
    return YfinancePriceAdapter()


@pytest.fixture
def fx_adapter() -> YfinanceLiveFxAdapter:
    return YfinanceLiveFxAdapter()


def test_yfinance_raises_price_unavailable(price_adapter: YfinancePriceAdapter) -> None:
    with patch("app.adapters.yfinance_price.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info.get.side_effect = Exception("network down")

        with pytest.raises(PriceUnavailableError) as excinfo:
            price_adapter.get_current_price("NVDA")

        assert "network down" in str(excinfo.value)
        assert excinfo.value.ticker == "NVDA"


def test_yfinance_returns_nan_ticker_not_found(price_adapter: YfinancePriceAdapter) -> None:
    with patch("app.adapters.yfinance_price.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info = {"lastPrice": float("nan")}
        mock_instance.history.return_value = pd.DataFrame()

        with pytest.raises(TickerNotFoundError):
            price_adapter.get_current_price("NVDA")


def test_historical_expansion_logic(price_adapter: YfinancePriceAdapter) -> None:
    with patch("app.adapters.yfinance_price.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance

        mock_instance.history.side_effect = [
            pd.DataFrame(),
            pd.DataFrame({"Close": [100.0]}, index=[pd.Timestamp("2024-01-01")])
        ]

        p = price_adapter.get_historical_close("NVDA", date(2024, 1, 2))
        assert p.amount == Decimal("100.0000")
        assert mock_instance.history.call_count == 2


def test_both_windows_empty_raises(price_adapter: YfinancePriceAdapter) -> None:
    with patch("app.adapters.yfinance_price.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.history.return_value = pd.DataFrame()

        with pytest.raises(PriceUnavailableError) as excinfo:
            price_adapter.get_historical_close("NVDA", date(2024, 1, 2))

        assert "No historical close near 2024-01-02" in str(excinfo.value)


def test_unsupported_currency_pair(fx_adapter: YfinanceLiveFxAdapter) -> None:
    with pytest.raises(UnsupportedCurrencyPairError):
        fx_adapter.get_current_rate(Currency.EUR, "GBP")  # type: ignore
