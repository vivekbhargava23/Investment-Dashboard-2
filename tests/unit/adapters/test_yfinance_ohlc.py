from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest

from app.adapters.yfinance_feed.yfinance_adapter import (
    YfinanceAdapter,
    _interval_for_period,
)
from app.domain.market_data import ChartPeriod, OhlcUnavailableError
from app.domain.money import Currency


def _df(rows: list[dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        index=pd.DatetimeIndex(
            [pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=i) for i in range(len(rows))]
        ),
    )


def test_yfinance_dataframe_converts_to_ohlc_series() -> None:
    data = _df(
        [
            {"Open": 100.1, "High": 110.1, "Low": 95.1, "Close": 108.1, "Volume": 1000.0},
            {"Open": 108.2, "High": 115.2, "Low": 105.2, "Close": 112.2, "Volume": 1200.0},
        ]
    )

    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = data
        series = YfinanceAdapter().get_ohlc_history("nvda", ChartPeriod.SIX_MONTH)

    assert series.ticker == "NVDA"
    assert series.currency == Currency.USD
    assert series.period == ChartPeriod.SIX_MONTH
    assert len(series.bars) == 2
    assert series.bars[0].open == Decimal("100.1")
    mock_ticker.return_value.history.assert_called_once_with(
        period="6mo",
        interval="1wk",
        auto_adjust=False,
    )


def test_empty_dataframe_raises_ohlc_unavailable_error() -> None:
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = pd.DataFrame()
        with pytest.raises(OhlcUnavailableError):
            YfinanceAdapter().get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH)


def test_bad_row_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    data = _df(
        [
            {"Open": 120.0, "High": 110.0, "Low": 95.0, "Close": 108.0, "Volume": 1000.0},
            {"Open": 108.0, "High": 115.0, "Low": 105.0, "Close": 112.0, "Volume": 1200.0},
        ]
    )

    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = data
        series = YfinanceAdapter().get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH)

    assert len(series.bars) == 1
    assert "Skipping invalid OHLC row" in caplog.text


def test_nan_volume_becomes_none() -> None:
    data = _df(
        [{"Open": 100.0, "High": 110.0, "Low": 95.0, "Close": 108.0, "Volume": float("nan")}]
    )

    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = data
        series = YfinanceAdapter().get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH)

    assert series.bars[0].volume is None


def test_decimal_precision_preserved() -> None:
    data = _df(
        [{"Open": 251.378241, "High": 260.0, "Low": 250.0, "Close": 255.0, "Volume": 1000.0}]
    )

    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = data
        series = YfinanceAdapter().get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH)

    assert series.bars[0].open == Decimal("251.378241")


def test_currency_inference_is_canonical() -> None:
    data = _df(
        [{"Open": 100.0, "High": 110.0, "Low": 95.0, "Close": 108.0, "Volume": 1000.0}]
    )

    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = data
        series = YfinanceAdapter().get_ohlc_history("RHM.DE", ChartPeriod.SIX_MONTH)

    assert series.currency == Currency.EUR


def test_ohlc_cache_ttl_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _df(
        [{"Open": 100.0, "High": 110.0, "Low": 95.0, "Close": 108.0, "Volume": 1000.0}]
    )
    now = 1000.0
    monkeypatch.setattr("app.adapters.yfinance_feed.yfinance_adapter.time.monotonic", lambda: now)

    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = data
        adapter = YfinanceAdapter()
        adapter.get_ohlc_history("NVDA", ChartPeriod.ONE_DAY)
        adapter.get_ohlc_history("NVDA", ChartPeriod.ONE_DAY)
        now += 15 * 60 + 1
        adapter.get_ohlc_history("NVDA", ChartPeriod.ONE_DAY)

    assert mock_ticker.return_value.history.call_count == 2


def test_interval_for_period_mappings() -> None:
    assert _interval_for_period(ChartPeriod.ONE_DAY) == "5m"
    assert _interval_for_period(ChartPeriod.FIVE_DAY) == "15m"
    assert _interval_for_period(ChartPeriod.ONE_MONTH) == "1d"
    assert _interval_for_period(ChartPeriod.THREE_MONTH) == "1wk"
    assert _interval_for_period(ChartPeriod.SIX_MONTH) == "1wk"
    assert _interval_for_period(ChartPeriod.ONE_YEAR) == "1mo"
    assert _interval_for_period(ChartPeriod.TWO_YEAR) == "1mo"
    assert _interval_for_period(ChartPeriod.FIVE_YEAR) == "1mo"
