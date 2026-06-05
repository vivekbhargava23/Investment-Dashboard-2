"""Tests for the Overview allocation treemap (TICKET-RD10).

Cover figure-data assembly (sizes follow EUR value), the symmetric clamp config,
in-tile return text, None-return neutral/"n/a" handling, high/low in the hover,
and stale-position exclusion.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import plotly.graph_objects as go

from app.domain.money import Currency, Money
from app.domain.positions import LivePosition
from app.domain.returns import ReturnWindow, WindowStats
from app.ui.components.treemap import (
    RETURN_CLAMP_PCT,
    build_treemap_figure,
    render_treemap,
)
from tests.unit.ui.test_overview_render import _make_position_with_lot

StatsMap = dict[str, dict[ReturnWindow, WindowStats | None]]


def _live(ticker: str, value_eur: str) -> LivePosition:
    """A non-stale LivePosition with an exact live EUR value (EUR native price)."""
    value = Money(amount=Decimal(value_eur), currency=Currency.EUR)
    return LivePosition(
        position=_make_position_with_lot(ticker, "1", "100"),
        live_price_native=Money(amount=Decimal(value_eur), currency=Currency.EUR),
        live_value_eur=value,
        unrealised_gain_eur=Money(amount=Decimal("0"), currency=Currency.EUR),
        unrealised_gain_pct=Decimal("0"),
        current_fx_rate=Decimal("1.0"),
        staleness_reason=None,
    )


def _live_usd(ticker: str, value_eur: str, *, fx: str, price_usd: str) -> LivePosition:
    """A non-stale USD-native LivePosition with an explicit EUR-per-USD FX rate."""
    return LivePosition(
        position=_make_position_with_lot(ticker, "1", "100"),
        live_price_native=Money(amount=Decimal(price_usd), currency=Currency.USD),
        live_value_eur=Money(amount=Decimal(value_eur), currency=Currency.EUR),
        unrealised_gain_eur=Money(amount=Decimal("0"), currency=Currency.EUR),
        unrealised_gain_pct=Decimal("0"),
        current_fx_rate=Decimal(fx),
        staleness_reason=None,
    )


def _stale(ticker: str) -> LivePosition:
    return LivePosition(
        position=_make_position_with_lot(ticker, "1", "100"),
        live_price_native=None,
        live_value_eur=None,
        unrealised_gain_eur=None,
        unrealised_gain_pct=None,
        current_fx_rate=None,
        staleness_reason="price feed unavailable",
    )


def _stat(pct: Decimal | None, *, high: str = "1", low: str = "1") -> WindowStats:
    return WindowStats(pct=pct, high=Decimal(high), low=Decimal(low))


def _stats(**rows: WindowStats | None) -> StatsMap:
    """Build a stats map where each kwarg sets the 30D stats for that ticker."""
    return {ticker: {ReturnWindow.M1: stat} for ticker, stat in rows.items()}


# ---------------------------------------------------------------------------
# Test case 1 — sizes follow live EUR value
# ---------------------------------------------------------------------------

def test_values_match_live_value_eur() -> None:
    positions = {
        "AAA": _live("AAA", "1000"),
        "BBB": _live("BBB", "500"),
        "CCC": _live("CCC", "250"),
    }
    stats = _stats(AAA=_stat(Decimal("1")), BBB=_stat(Decimal("2")), CCC=_stat(Decimal("3")))
    fig = build_treemap_figure(positions, stats, ReturnWindow.M1, name_lookup={})
    assert fig is not None
    trace = fig.data[0]
    assert trace.type == "treemap"
    by_label = dict(zip(trace.labels, trace.values))
    assert by_label == {"AAA": 1000.0, "BBB": 500.0, "CCC": 250.0}


# ---------------------------------------------------------------------------
# Test case 2 — fixed symmetric clamp
# ---------------------------------------------------------------------------

def test_clamp_is_symmetric_and_colors_carry_raw_returns() -> None:
    positions = {"UP": _live("UP", "100"), "DOWN": _live("DOWN", "100")}
    stats = _stats(UP=_stat(Decimal("30")), DOWN=_stat(Decimal("-30")))
    fig = build_treemap_figure(positions, stats, ReturnWindow.M1, name_lookup={})
    assert fig is not None
    marker = fig.data[0].marker
    # cmin/cmax are symmetric ±RETURN_CLAMP_PCT; out-of-range returns are clamped
    # to the scale ends by Plotly at render time (raw values are passed through).
    assert marker.cmin == float(-RETURN_CLAMP_PCT)
    assert marker.cmax == float(RETURN_CLAMP_PCT)
    assert marker.cmid == 0.0
    by_label = dict(zip(fig.data[0].labels, marker.colors))
    assert by_label["UP"] == 30.0
    assert by_label["DOWN"] == -30.0


# ---------------------------------------------------------------------------
# In-tile text shows the window return
# ---------------------------------------------------------------------------

def test_tile_text_shows_return_percent() -> None:
    positions = {"AAA": _live("AAA", "100")}
    stats = _stats(AAA=_stat(Decimal("4.2")))
    fig = build_treemap_figure(positions, stats, ReturnWindow.M1, name_lookup={"AAA": "Alpha"})
    assert fig is not None
    text = fig.data[0].text[0]
    assert "AAA" in text
    assert "Alpha" in text
    assert "+4.2%" in text


# ---------------------------------------------------------------------------
# Test case 3 — None return is neutral + "n/a", never a fabricated 0%
# ---------------------------------------------------------------------------

def test_none_return_is_neutral_and_hover_says_na() -> None:
    positions = {"AAA": _live("AAA", "750"), "BBB": _live("BBB", "250")}
    stats: StatsMap = {
        "AAA": {ReturnWindow.M1: None},
        "BBB": {ReturnWindow.M1: _stat(Decimal("5"))},
    }
    fig = build_treemap_figure(positions, stats, ReturnWindow.M1, name_lookup={"AAA": "Alpha"})
    assert fig is not None
    trace = fig.data[0]
    colors_by_label = dict(zip(trace.labels, trace.marker.colors))
    hover_by_label = dict(zip(trace.labels, trace.customdata))
    text_by_label = dict(zip(trace.labels, trace.text))
    # neutral colour = cmid value (0.0), not red/green
    assert colors_by_label["AAA"] == 0.0
    assert "1M return: n/a" in hover_by_label["AAA"]
    assert text_by_label["AAA"].endswith("n/a")
    # never a fabricated 0% return for the n/a tile
    assert "return: 0.0%" not in hover_by_label["AAA"]
    assert "1M return: +5.0%" in hover_by_label["BBB"]


# ---------------------------------------------------------------------------
# Hover shows the window high/low (candlestick-style), in native currency
# ---------------------------------------------------------------------------

def test_hover_shows_window_high_low_in_eur() -> None:
    # EUR-native position → factor 1, prices shown directly in EUR (German format).
    positions = {"AAA": _live("AAA", "100")}
    stats = _stats(AAA=_stat(Decimal("3"), high="142.50", low="118.00"))
    fig = build_treemap_figure(positions, stats, ReturnWindow.M1, name_lookup={})
    assert fig is not None
    hover = fig.data[0].customdata[0]
    assert "high €142,50" in hover
    assert "low €118,00" in hover


def test_hover_high_low_converted_to_eur_at_current_fx() -> None:
    # USD-native high/low are converted at current FX (EUR per USD = 0.90).
    positions = {"AAA": _live_usd("AAA", "180", fx="0.90", price_usd="200")}
    stats = _stats(AAA=_stat(Decimal("3"), high="200.00", low="150.00"))
    fig = build_treemap_figure(positions, stats, ReturnWindow.M1, name_lookup={})
    assert fig is not None
    hover = fig.data[0].customdata[0]
    # 200 * 0.90 = 180.00; 150 * 0.90 = 135.00 — and no USD anywhere.
    assert "high €180,00" in hover
    assert "low €135,00" in hover
    assert "USD" not in hover


def test_hovering_is_enabled() -> None:
    # base_layout(show_axes=False) sets hovermode=False (disables the tooltip);
    # the treemap must re-enable it or the hover never appears (regression guard).
    positions = {"AAA": _live("AAA", "100")}
    stats = _stats(AAA=_stat(Decimal("1")))
    fig = build_treemap_figure(positions, stats, ReturnWindow.M1, name_lookup={})
    assert fig is not None
    assert fig.layout.hovermode == "closest"


# ---------------------------------------------------------------------------
# Test case 4 — stale positions excluded
# ---------------------------------------------------------------------------

def test_stale_position_absent_from_figure() -> None:
    positions = {"LIVE": _live("LIVE", "400"), "STALE": _stale("STALE")}
    stats = _stats(LIVE=_stat(Decimal("2")))
    fig = build_treemap_figure(positions, stats, ReturnWindow.M1, name_lookup={})
    assert fig is not None
    assert list(fig.data[0].labels) == ["LIVE"]


def test_all_stale_returns_none_figure() -> None:
    positions = {"S1": _stale("S1"), "S2": _stale("S2")}
    fig = build_treemap_figure(positions, {}, ReturnWindow.M1, name_lookup={})
    assert fig is None


def test_render_treemap_shows_placeholder_when_empty() -> None:
    with patch("app.ui.components.treemap.st") as mock_st:
        render_treemap({}, {}, ReturnWindow.M1, name_lookup={})
        mock_st.info.assert_called_once()
        mock_st.plotly_chart.assert_not_called()


def test_render_treemap_draws_figure() -> None:
    positions = {"AAA": _live("AAA", "100")}
    stats = _stats(AAA=_stat(Decimal("1")))
    with patch("app.ui.components.treemap.st") as mock_st:
        render_treemap(positions, stats, ReturnWindow.M1, name_lookup={})
        mock_st.plotly_chart.assert_called_once()
        fig = mock_st.plotly_chart.call_args[0][0]
        assert isinstance(fig, go.Figure)


# ---------------------------------------------------------------------------
# Weight % in hover reflects share of total live value
# ---------------------------------------------------------------------------

def test_hover_weight_is_share_of_total_value() -> None:
    positions = {"AAA": _live("AAA", "750"), "BBB": _live("BBB", "250")}
    stats = _stats(AAA=_stat(Decimal("1")), BBB=_stat(Decimal("1")))
    fig = build_treemap_figure(positions, stats, ReturnWindow.M1, name_lookup={})
    assert fig is not None
    hover_by_label = dict(zip(fig.data[0].labels, fig.data[0].customdata))
    assert "75.0% of portfolio" in hover_by_label["AAA"]
    assert "25.0% of portfolio" in hover_by_label["BBB"]
