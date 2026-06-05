"""Tests for the Overview performance heatmap (TICKET-RD11).

Cover row ordering (by sort-window desc, None last), in-cell return text, the
None → "—"/neutral rule, the shared colour scale (regression vs the treemap), and
the empty-state placeholder.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import plotly.graph_objects as go

from app.domain.money import Currency, Money
from app.domain.positions import LivePosition
from app.domain.returns import ALL_WINDOWS, ReturnWindow, WindowStats
from app.ui.components._chart_styles import RETURN_CLAMP_PCT
from app.ui.components.perf_heatmap import build_heatmap_figure, render_heatmap
from app.ui.components.treemap import build_treemap_figure
from tests.unit.ui.test_overview_render import _make_position_with_lot

StatsMap = dict[str, dict[ReturnWindow, WindowStats | None]]

_M1_COL = ALL_WINDOWS.index(ReturnWindow.M1)


def _live(ticker: str, value_eur: str = "100") -> LivePosition:
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


def _stale(ticker: str) -> LivePosition:
    """A stale holding — no live value, so it can't be sized and sorts last."""
    return LivePosition(
        position=_make_position_with_lot(ticker, "1", "100"),
        live_price_native=None,
        live_value_eur=None,
        unrealised_gain_eur=None,
        unrealised_gain_pct=None,
        current_fx_rate=None,
        staleness_reason="price feed unavailable",
    )


def _stat(pct: Decimal | None) -> WindowStats:
    return WindowStats(pct=pct, high=Decimal("1"), low=Decimal("1"))


def _m1(**rows: Decimal | None) -> StatsMap:
    """Stats map setting just the 1M window per ticker."""
    return {ticker: {ReturnWindow.M1: _stat(pct)} for ticker, pct in rows.items()}


# ---------------------------------------------------------------------------
# Test case 1 — rows ordered by holding size (live EUR value) desc; cell text
# ---------------------------------------------------------------------------

def test_rows_ordered_by_holding_value_desc_with_cell_text() -> None:
    positions = {
        "AAA": _live("AAA", "250"),
        "BBB": _live("BBB", "1000"),
        "CCC": _live("CCC", "500"),
    }
    stats = _m1(AAA=Decimal("1"), BBB=Decimal("3"), CCC=Decimal("2"))
    fig = build_heatmap_figure(positions, stats, name_lookup={})
    assert fig is not None
    trace = fig.data[0]
    # Biggest holding first (data order largest→smallest; y-axis reversed for display).
    assert list(trace.y) == ["BBB", "CCC", "AAA"]
    # The 1M cell of the top row (BBB, the biggest holding) prints its return.
    assert trace.text[0][_M1_COL] == "+3.0%"
    assert trace.text[2][_M1_COL] == "+1.0%"


def test_columns_are_all_windows_in_order() -> None:
    fig = build_heatmap_figure({"AAA": _live("AAA")}, _m1(AAA=Decimal("1")), name_lookup={})
    assert fig is not None
    assert list(fig.data[0].x) == [w.value for w in ALL_WINDOWS]


def test_row_label_includes_company_name() -> None:
    fig = build_heatmap_figure(
        {"AAA": _live("AAA")}, _m1(AAA=Decimal("1")), name_lookup={"AAA": "Alpha"}
    )
    assert fig is not None
    assert list(fig.data[0].y) == ["AAA (Alpha)"]


# ---------------------------------------------------------------------------
# Test case 2 — stale (unvalued) holdings sort last regardless of return
# ---------------------------------------------------------------------------

def test_stale_holding_sorts_last() -> None:
    positions = {
        "AAA": _live("AAA", "1000"),
        "STALE": _stale("STALE"),
        "CCC": _live("CCC", "500"),
    }
    # STALE has a huge return but no live value — it must still sort last.
    stats: StatsMap = {
        "AAA": {ReturnWindow.M1: _stat(Decimal("1"))},
        "STALE": {ReturnWindow.M1: _stat(Decimal("99"))},
        "CCC": {ReturnWindow.M1: _stat(Decimal("2"))},
    }
    fig = build_heatmap_figure(positions, stats, name_lookup={})
    assert fig is not None
    assert list(fig.data[0].y) == ["AAA", "CCC", "STALE"]


# ---------------------------------------------------------------------------
# Test case 3 — None cell shows "—" on the neutral colour, never 0.0%
# ---------------------------------------------------------------------------

def test_none_cell_is_em_dash_and_neutral_never_zero() -> None:
    fig = build_heatmap_figure(
        {"AAA": _live("AAA")}, _m1(AAA=None), name_lookup={}
    )
    assert fig is not None
    trace = fig.data[0]
    assert trace.text[0][_M1_COL] == "—"
    # Neutral = 0.0 on the diverging scale (zmid), the same as the treemap's n/a.
    assert trace.z[0][_M1_COL] == 0.0
    hover = trace.customdata[0][_M1_COL]
    assert "1M: n/a" in hover
    assert "0.0%" not in hover


def test_hover_shows_ticker_window_and_return() -> None:
    fig = build_heatmap_figure(
        {"AAA": _live("AAA")}, _m1(AAA=Decimal("4.2")), name_lookup={"AAA": "Alpha"}
    )
    assert fig is not None
    assert fig.data[0].customdata[0][_M1_COL] == "AAA · 1M: +4.2%"


# ---------------------------------------------------------------------------
# Test case 4 — shared colour scale: heatmap and treemap can't drift
# ---------------------------------------------------------------------------

def test_heatmap_and_treemap_share_one_colour_scale() -> None:
    positions = {"AAA": _live("AAA")}
    stats: StatsMap = {"AAA": {ReturnWindow.M1: _stat(Decimal("5"))}}
    heatmap = build_heatmap_figure(positions, stats, name_lookup={})
    treemap = build_treemap_figure(positions, stats, ReturnWindow.M1, name_lookup={})
    assert heatmap is not None and treemap is not None

    h = heatmap.data[0]
    m = treemap.data[0].marker
    # Same colorscale object and same symmetric clamp ⇒ identical value→colour map.
    assert h.colorscale == m.colorscale
    assert h.zmin == m.cmin == float(-RETURN_CLAMP_PCT)
    assert h.zmax == m.cmax == float(RETURN_CLAMP_PCT)
    assert h.zmid == m.cmid == 0.0


# ---------------------------------------------------------------------------
# Empty state + render plumbing
# ---------------------------------------------------------------------------

def test_no_holdings_returns_none_figure() -> None:
    assert build_heatmap_figure({}, {}, name_lookup={}) is None


def test_render_shows_placeholder_when_empty() -> None:
    with patch("app.ui.components.perf_heatmap.st") as mock_st:
        render_heatmap({}, {}, name_lookup={})
        mock_st.info.assert_called_once()
        mock_st.plotly_chart.assert_not_called()


def test_render_draws_figure() -> None:
    positions = {"AAA": _live("AAA")}
    with patch("app.ui.components.perf_heatmap.st") as mock_st:
        render_heatmap(positions, _m1(AAA=Decimal("1")), name_lookup={})
        mock_st.plotly_chart.assert_called_once()
        assert isinstance(mock_st.plotly_chart.call_args[0][0], go.Figure)
