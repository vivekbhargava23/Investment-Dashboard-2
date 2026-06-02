"""Batch-fetch tests for the yfinance adapters (TICKET-PERF-1).

All network calls are mocked — zero real I/O. These cover the batch contract:
per-ticker error isolation, cache reuse (only misses are fetched), and dedup.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.adapters.yfinance_ohlc.adapter import YfinanceOhlcAdapter
from app.adapters.yfinance_price.adapter import YfinancePriceAdapter
from app.domain.market_data import ChartPeriod
from app.domain.money import Currency, Money

# ── Price batch ─────────────────────────────────────────────────────────────


@pytest.fixture
def price_adapter() -> YfinancePriceAdapter:
    return YfinancePriceAdapter(current_ttl_seconds=60)


def _price_ticker_factory(prices: dict[str, float | None]):
    """Return a yf.Ticker side_effect: known symbols get a price, others fail."""

    def factory(symbol: str) -> MagicMock:
        m = MagicMock()
        m.fast_info = {"lastPrice": prices.get(symbol)}
        m.history.return_value = pd.DataFrame()  # empty fallback → unavailable
        return m

    return factory


def test_batch_prices_returns_all(price_adapter: YfinancePriceAdapter) -> None:
    with patch("app.adapters.yfinance_price.adapter.yf.Ticker") as mock_ticker:
        mock_ticker.side_effect = _price_ticker_factory({"NVDA": 100.0, "MU": 80.0})
        result = price_adapter.get_current_prices(["NVDA", "MU"])

    assert result == {
        "NVDA": Money(amount=Decimal("100"), currency=Currency.USD),
        "MU": Money(amount=Decimal("80"), currency=Currency.USD),
    }


def test_batch_prices_isolates_bad_ticker(price_adapter: YfinancePriceAdapter) -> None:
    with patch("app.adapters.yfinance_price.adapter.yf.Ticker") as mock_ticker:
        mock_ticker.side_effect = _price_ticker_factory({"NVDA": 100.0, "BAD": None})
        result = price_adapter.get_current_prices(["NVDA", "BAD"])

    assert "NVDA" in result
    assert "BAD" not in result  # one bad ticker never fails the batch


def test_batch_prices_only_fetches_misses(price_adapter: YfinancePriceAdapter) -> None:
    with patch("app.adapters.yfinance_price.adapter.yf.Ticker") as mock_ticker:
        mock_ticker.side_effect = _price_ticker_factory({"NVDA": 100.0, "MU": 80.0})

        price_adapter.get_current_price("NVDA")  # warm the cache (1 fetch)
        result = price_adapter.get_current_prices(["NVDA", "MU"])  # only MU is a miss

    assert set(result) == {"NVDA", "MU"}
    assert mock_ticker.call_count == 2  # NVDA once (single) + MU once (batch)


def test_batch_prices_dedupes_tickers(price_adapter: YfinancePriceAdapter) -> None:
    with patch("app.adapters.yfinance_price.adapter.yf.Ticker") as mock_ticker:
        mock_ticker.side_effect = _price_ticker_factory({"NVDA": 100.0})
        result = price_adapter.get_current_prices(["NVDA", "NVDA", "NVDA"])

    assert set(result) == {"NVDA"}
    assert mock_ticker.call_count == 1  # fetched once despite three requests


# ── OHLC batch ──────────────────────────────────────────────────────────────


@pytest.fixture
def ohlc_adapter() -> YfinanceOhlcAdapter:
    return YfinanceOhlcAdapter()


def _ohlc_df(close: float) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp("2024-01-02", tz="UTC")])
    return pd.DataFrame(
        {
            "Open": [close],
            "High": [close + 5],
            "Low": [close - 5],
            "Close": [close],
            "Volume": [1000.0],
        },
        index=index,
    )


def _ohlc_ticker_factory(closes: dict[str, float]):
    """Return a yf.Ticker side_effect: known symbols get bars, others return empty."""

    def factory(symbol: str) -> MagicMock:
        m = MagicMock()
        if symbol in closes:
            m.history.return_value = _ohlc_df(closes[symbol])
        else:
            m.history.return_value = pd.DataFrame()
        return m

    return factory


def test_batch_ohlc_returns_all(ohlc_adapter: YfinanceOhlcAdapter) -> None:
    with patch("app.adapters.yfinance_ohlc.adapter.yf.Ticker") as mock_ticker:
        mock_ticker.side_effect = _ohlc_ticker_factory({"NVDA": 100.0, "RHM.DE": 200.0})
        result = ohlc_adapter.get_ohlc_histories(
            ["NVDA", "RHM.DE"], ChartPeriod.SIX_MONTH
        )

    assert set(result) == {"NVDA", "RHM.DE"}
    assert result["NVDA"].currency == Currency.USD
    assert result["RHM.DE"].currency == Currency.EUR


def test_batch_ohlc_isolates_bad_ticker(ohlc_adapter: YfinanceOhlcAdapter) -> None:
    with patch("app.adapters.yfinance_ohlc.adapter.yf.Ticker") as mock_ticker:
        mock_ticker.side_effect = _ohlc_ticker_factory({"NVDA": 100.0})
        result = ohlc_adapter.get_ohlc_histories(["NVDA", "BAD"], ChartPeriod.SIX_MONTH)

    assert "NVDA" in result
    assert "BAD" not in result  # empty/failed ticker is omitted, not raised


def test_batch_ohlc_only_fetches_misses(ohlc_adapter: YfinanceOhlcAdapter) -> None:
    with patch("app.adapters.yfinance_ohlc.adapter.yf.Ticker") as mock_ticker:
        mock_ticker.side_effect = _ohlc_ticker_factory({"NVDA": 100.0, "RHM.DE": 200.0})

        ohlc_adapter.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH)  # warm cache
        result = ohlc_adapter.get_ohlc_histories(
            ["NVDA", "RHM.DE"], ChartPeriod.SIX_MONTH
        )

    assert set(result) == {"NVDA", "RHM.DE"}
    assert mock_ticker.call_count == 2  # NVDA once (single) + RHM.DE once (batch)
