"""Tests for trend-text fetching and the positions table on the Overview page."""

from __future__ import annotations

from decimal import Decimal

from app.domain.market_data import ChartPeriod
from app.ui.components.positions_table import (
    build_positions_table_html as _build_positions_table_html,
)
from app.ui.pages.overview import _fetch_trend_texts
from tests.fakes.ohlc import FAKE_SERIES_NVDA_6MO, FAKE_SERIES_RHM_1Y, FakeOhlcDataProvider
from tests.unit.ui.test_overview_render import _make_live_position, _make_summary

# ── _fetch_trend_texts isolation ──────────────────────────────────────────────

def test_trend_text_failure_does_not_break_other_tickers() -> None:
    """If one ticker raises OhlcUnavailableError, others still return text."""
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
        trend_texts = _fetch_trend_texts(["NVDA", "ANET", "RHM.DE"])

    assert trend_texts["NVDA"] != "—"
    assert trend_texts["ANET"] == "—"
    assert trend_texts["RHM.DE"] != "—"


def test_fetch_trend_texts_issues_single_batch_fetch() -> None:
    """All tickers' OHLC come from one batched call, not one fetch per ticker."""
    series_map = {
        ("NVDA", ChartPeriod.ONE_MONTH): FAKE_SERIES_NVDA_6MO,
        ("RHM.DE", ChartPeriod.ONE_MONTH): FAKE_SERIES_RHM_1Y,
    }
    provider = FakeOhlcDataProvider(series_map=series_map)

    from unittest.mock import patch
    with patch("app.ui.pages.overview.get_ohlc_data_provider", return_value=provider):
        _fetch_trend_texts(["NVDA", "RHM.DE"])

    assert provider.batch_call_count == 1


def test_trend_text_positive_pct_uses_up_arrow() -> None:
    """NVDA 6MO fixture has positive period change → trend text contains ↑."""
    series_map = {("NVDA", ChartPeriod.ONE_MONTH): FAKE_SERIES_NVDA_6MO}
    provider = FakeOhlcDataProvider(series_map=series_map)

    from unittest.mock import patch
    with patch("app.ui.pages.overview.get_ohlc_data_provider", return_value=provider):
        trend_texts = _fetch_trend_texts(["NVDA"])

    assert "↑" in trend_texts["NVDA"]


def test_trend_text_negative_pct_uses_down_arrow() -> None:
    """A series with negative period change → trend text contains ↓."""
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
        trend_texts = _fetch_trend_texts(["FALL"])

    assert "↓" in trend_texts["FALL"]


# ── Trend column in HTML table ────────────────────────────────────────────────

def test_trend_column_appears_in_table_header() -> None:
    """The Trend 30D column header is present in the rendered HTML."""
    positions = {"NVDA": _make_live_position("NVDA")}
    summary = _make_summary(positions)
    html = _build_positions_table_html(positions, summary)
    assert "Trend" in html


def test_trend_column_shows_provided_trend_text() -> None:
    """When trend_data is passed, the trend text appears in the table HTML."""
    positions = {"NVDA": _make_live_position("NVDA")}
    summary = _make_summary(positions)
    trend_data = {"NVDA": "↑ +5.3%"}
    html = _build_positions_table_html(positions, summary, trend_data=trend_data)
    assert "↑ +5.3%" in html


def test_trend_column_shows_placeholder_when_no_data() -> None:
    """When trend_data is None (no fetch), the trend cell shows '—'."""
    positions = {"NVDA": _make_live_position("NVDA")}
    summary = _make_summary(positions)
    html = _build_positions_table_html(positions, summary, trend_data=None)
    assert "—" in html


def test_existing_table_tests_unaffected_with_no_trend_data() -> None:
    """Calling _build_positions_table_html without trend_data still works (backward compat)."""
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    summary = _make_summary(positions)
    html = _build_positions_table_html(positions, summary)
    assert html[0] == "<"
    assert "<table" in html
