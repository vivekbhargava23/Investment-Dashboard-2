"""Tests for trend-value fetching and the positions table on the Overview page.

TICKET-RD2: trend is now a numeric column in the ``st.dataframe`` grid (the
table sorts client-side), so the overview helper returns numeric % changes
instead of pre-formatted HTML spans.
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.market_data import ChartPeriod
from app.ui.components.positions_table import build_positions_dataframe
from app.ui.pages.overview import _fetch_trend_values
from tests.fakes.ohlc import FAKE_SERIES_NVDA_6MO, FAKE_SERIES_RHM_1Y, FakeOhlcDataProvider
from tests.unit.ui.test_overview_render import _make_live_position, _make_summary

# ── _fetch_trend_values isolation ─────────────────────────────────────────────

def test_trend_failure_does_not_break_other_tickers() -> None:
    """If one ticker raises OhlcUnavailableError, others still return a value."""
    series_map = {
        ("NVDA", ChartPeriod.ONE_MONTH): FAKE_SERIES_NVDA_6MO,
        ("RHM.DE", ChartPeriod.ONE_MONTH): FAKE_SERIES_RHM_1Y,
    }
    provider = FakeOhlcDataProvider(
        series_map=series_map,
        raise_for={("ANET", ChartPeriod.ONE_MONTH)},
    )

    from unittest.mock import patch
    with patch("app.ui.pages.overview.get_ohlc_data_provider", return_value=provider):
        trend = _fetch_trend_values(["NVDA", "ANET", "RHM.DE"])

    assert trend["NVDA"] is not None
    assert trend["ANET"] is None
    assert trend["RHM.DE"] is not None


def test_fetch_trend_values_issues_single_batch_fetch() -> None:
    """All tickers' OHLC come from one batched call, not one fetch per ticker."""
    series_map = {
        ("NVDA", ChartPeriod.ONE_MONTH): FAKE_SERIES_NVDA_6MO,
        ("RHM.DE", ChartPeriod.ONE_MONTH): FAKE_SERIES_RHM_1Y,
    }
    provider = FakeOhlcDataProvider(series_map=series_map)

    from unittest.mock import patch
    with patch("app.ui.pages.overview.get_ohlc_data_provider", return_value=provider):
        _fetch_trend_values(["NVDA", "RHM.DE"])

    assert provider.batch_call_count == 1


def test_trend_positive_pct_is_positive_number() -> None:
    """NVDA 6MO fixture has positive period change → trend value > 0."""
    series_map = {("NVDA", ChartPeriod.ONE_MONTH): FAKE_SERIES_NVDA_6MO}
    provider = FakeOhlcDataProvider(series_map=series_map)

    from unittest.mock import patch
    with patch("app.ui.pages.overview.get_ohlc_data_provider", return_value=provider):
        trend = _fetch_trend_values(["NVDA"])

    assert trend["NVDA"] is not None and trend["NVDA"] > 0


def test_trend_negative_pct_is_negative_number() -> None:
    """A series with negative period change → trend value < 0."""
    from datetime import UTC, datetime

    from app.domain.market_data import OhlcBar, OhlcSeries
    from app.domain.money import Currency

    falling_series = OhlcSeries(
        ticker="FALL",
        currency=Currency.EUR,
        period=ChartPeriod.ONE_MONTH,
        bars=(
            OhlcBar(
                timestamp=datetime(2024, 1, 2, tzinfo=UTC),
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("95"),
                close=Decimal("96"),  # open=100 > close=96 → negative period change
                volume=1000,
            ),
        ),
        fetched_at=datetime(2024, 2, 1, tzinfo=UTC),
    )
    series_map = {("FALL", ChartPeriod.ONE_MONTH): falling_series}
    provider = FakeOhlcDataProvider(series_map=series_map)

    from unittest.mock import patch
    with patch("app.ui.pages.overview.get_ohlc_data_provider", return_value=provider):
        trend = _fetch_trend_values(["FALL"])

    assert trend["FALL"] is not None and trend["FALL"] < 0


# ── Trend column in the dataframe ─────────────────────────────────────────────

def test_trend_column_present_in_dataframe() -> None:
    positions = {"NVDA": _make_live_position("NVDA")}
    df = build_positions_dataframe(positions, _make_summary(positions))
    assert "Trend 30D (%)" in df.columns


def test_trend_value_appears_in_dataframe() -> None:
    positions = {"NVDA": _make_live_position("NVDA")}
    df = build_positions_dataframe(
        positions, _make_summary(positions), trend_values={"NVDA": 5.3}
    )
    assert df.iloc[0]["Trend 30D (%)"] == 5.3


def test_trend_value_none_when_no_data() -> None:
    positions = {"NVDA": _make_live_position("NVDA")}
    df = build_positions_dataframe(positions, _make_summary(positions))
    assert df.iloc[0]["Trend 30D (%)"] is None
