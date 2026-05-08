"""Adapter-level OHLC tests. All network calls are mocked — zero real I/O."""

from datetime import UTC
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest

from app.adapters.yfinance_feed import YfinanceAdapter
from app.domain.market_data import ChartPeriod, OhlcUnavailableError
from app.domain.money import Currency


@pytest.fixture()
def adapter() -> YfinanceAdapter:
    return YfinanceAdapter()


def _make_df(
    rows: list[tuple[str, float, float, float, float, float | None]],
) -> pd.DataFrame:
    """Build a minimal yfinance-style DataFrame for mocking .history()."""
    index = pd.DatetimeIndex(
        [pd.Timestamp(r[0], tz="UTC") for r in rows]
    )
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
            "Volume": [r[5] if r[5] is not None else float("nan") for r in rows],
        },
        index=index,
    )


def test_happy_path_returns_ohlcseries(adapter: YfinanceAdapter) -> None:
    df = _make_df([
        ("2024-01-02", 450.0, 465.0, 445.0, 460.0, 1_000_000.0),
        ("2024-01-03", 460.0, 475.0, 455.0, 470.0, 1_200_000.0),
        ("2024-01-04", 470.0, 480.0, 465.0, 475.0, 900_000.0),
        ("2024-01-05", 475.0, 490.0, 470.0, 485.0, 1_100_000.0),
        ("2024-01-08", 485.0, 495.0, 480.0, 490.0, 800_000.0),
    ])
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = df
        series = adapter.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH)

    assert series.ticker == "NVDA"
    assert series.currency == Currency.USD
    assert series.period == ChartPeriod.SIX_MONTH
    assert len(series.bars) == 5
    assert series.bars[0].open == Decimal("450.0")
    assert series.bars[0].timestamp.tzinfo == UTC


def test_empty_dataframe_raises(adapter: YfinanceAdapter) -> None:
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = pd.DataFrame()
        with pytest.raises(OhlcUnavailableError):
            adapter.get_ohlc_history("XQYZ", ChartPeriod.SIX_MONTH)


def test_bad_row_skipped_valid_rows_kept(adapter: YfinanceAdapter) -> None:
    # Row 1: open > high — will fail OhlcBar validation → skipped
    # Row 2: valid
    df = _make_df([
        ("2024-01-02", 500.0, 490.0, 480.0, 485.0, 1_000.0),  # open > high: bad
        ("2024-01-03", 485.0, 495.0, 480.0, 490.0, 2_000.0),  # valid
    ])
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = df
        series = adapter.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH)

    assert len(series.bars) == 1
    assert series.bars[0].open == Decimal("485.0")


def test_nan_volume_becomes_none(adapter: YfinanceAdapter) -> None:
    df = _make_df([("2024-01-02", 450.0, 460.0, 445.0, 455.0, None)])
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = df
        series = adapter.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH)

    assert series.bars[0].volume is None


def test_decimal_precision_preserved(adapter: YfinanceAdapter) -> None:
    df = _make_df([("2024-01-02", 251.378241, 260.0, 250.0, 255.5, 1000.0)])
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = df
        series = adapter.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH)

    assert series.bars[0].open == Decimal("251.378241")


def test_currency_inferred_from_ticker(adapter: YfinanceAdapter) -> None:
    df = _make_df([("2024-01-02", 200.0, 210.0, 198.0, 205.0, 500.0)])
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = df
        series = adapter.get_ohlc_history("RHM.DE", ChartPeriod.SIX_MONTH)

    assert series.currency == Currency.EUR


def test_intraday_ttl_respected(adapter: YfinanceAdapter) -> None:
    df = _make_df([("2024-01-02", 450.0, 460.0, 445.0, 455.0, 1000.0)])
    with patch("yfinance.Ticker") as mock_ticker, patch("time.monotonic") as mock_time:
        mock_ticker.return_value.history.return_value = df
        mock_time.return_value = 1000.0
        adapter.get_ohlc_history("NVDA", ChartPeriod.ONE_DAY)
        assert mock_ticker.call_count == 1

        # Within 15-min TTL
        mock_time.return_value = 1000.0 + 14 * 60
        adapter.get_ohlc_history("NVDA", ChartPeriod.ONE_DAY)
        assert mock_ticker.call_count == 1

        # Past 15-min TTL
        mock_time.return_value = 1000.0 + 15 * 60 + 1
        adapter.get_ohlc_history("NVDA", ChartPeriod.ONE_DAY)
        assert mock_ticker.call_count == 2


def test_interval_for_period_mappings() -> None:
    assert YfinanceAdapter._interval_for_period(ChartPeriod.ONE_DAY) == "5m"
    assert YfinanceAdapter._interval_for_period(ChartPeriod.FIVE_DAY) == "15m"
    assert YfinanceAdapter._interval_for_period(ChartPeriod.ONE_MONTH) == "1d"
    assert YfinanceAdapter._interval_for_period(ChartPeriod.SIX_MONTH) == "1d"
    assert YfinanceAdapter._interval_for_period(ChartPeriod.ONE_YEAR) == "1d"


def test_clear_cache_clears_ohlc(adapter: YfinanceAdapter) -> None:
    df = _make_df([("2024-01-02", 450.0, 460.0, 445.0, 455.0, 1000.0)])
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = df
        adapter.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH)
        assert len(adapter._ohlc_cache) == 1
        adapter.clear_cache()
        assert len(adapter._ohlc_cache) == 0
        adapter.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH)
        assert mock_ticker.call_count == 2
