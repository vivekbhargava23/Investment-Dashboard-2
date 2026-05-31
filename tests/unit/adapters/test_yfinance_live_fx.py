"""Unit tests for YfinanceLiveFxAdapter — all network calls mocked."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.adapters.fx_yfinance.adapter import YfinanceLiveFxAdapter
from app.domain.money import Currency
from app.ports.fx_feed import FxRateUnavailableError, UnsupportedCurrencyPairError


@pytest.fixture
def adapter() -> YfinanceLiveFxAdapter:
    return YfinanceLiveFxAdapter(current_ttl_seconds=60)


def test_get_current_rate_eur_usd(adapter: YfinanceLiveFxAdapter) -> None:
    with patch("app.adapters.fx_yfinance.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info.get.return_value = 1.08

        rate = adapter.get_current_rate(Currency.EUR, Currency.USD)
        assert rate == Decimal("1.080000")


def test_get_current_rate_inverts_reversed_pair(adapter: YfinanceLiveFxAdapter) -> None:
    with patch("app.adapters.fx_yfinance.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        # Canonical is EURUSD=X → 1.08; USD/EUR is inverted
        mock_instance.fast_info.get.return_value = 1.08

        rate = adapter.get_current_rate(Currency.USD, Currency.EUR)
        expected = (Decimal("1") / Decimal("1.08")).quantize(Decimal("0.000001"))
        assert rate == expected


def test_get_current_rate_cached_within_ttl(adapter: YfinanceLiveFxAdapter) -> None:
    with patch("app.adapters.fx_yfinance.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info.get.return_value = 1.08

        r1 = adapter.get_current_rate(Currency.EUR, Currency.USD)
        r2 = adapter.get_current_rate(Currency.EUR, Currency.USD)

        assert r1 == r2
        assert mock_ticker.call_count == 1


def test_unsupported_pair_raises(adapter: YfinanceLiveFxAdapter) -> None:
    with pytest.raises(UnsupportedCurrencyPairError):
        adapter.get_current_rate(Currency.EUR, "GBP")  # type: ignore


def test_nan_rate_raises_fx_unavailable(adapter: YfinanceLiveFxAdapter) -> None:
    with patch("app.adapters.fx_yfinance.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info.get.return_value = float("nan")
        mock_instance.history.return_value = pd.DataFrame()

        with pytest.raises(FxRateUnavailableError):
            adapter.get_current_rate(Currency.EUR, Currency.USD)


def test_clear_cache(adapter: YfinanceLiveFxAdapter) -> None:
    with patch("app.adapters.fx_yfinance.adapter.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.fast_info.get.return_value = 1.08

        adapter.get_current_rate(Currency.EUR, Currency.USD)
        assert len(adapter._current_cache) == 1

        adapter.clear_cache()
        assert len(adapter._current_cache) == 0
