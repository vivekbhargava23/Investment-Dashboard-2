"""Tests for the Overview positions table.

TICKET-RD2 rebuilt the table on ``st.dataframe`` (client-side sort/search, no
page rerun), so the builder now returns a ``pandas.DataFrame`` instead of an
HTML string. ``st.dataframe`` escapes content itself, so the manual
``html.escape`` regressions the HTML version guarded (TICKET-008b / ROBUST-1)
no longer apply.
"""
from __future__ import annotations

import math

from app.domain.positions import LivePosition
from app.ui.components.positions_table import _weight_bar_css, build_positions_dataframe
from tests.unit.ui.test_overview_render import (
    _make_live_position,
    _make_live_position_usd,
    _make_position_with_lot,
    _make_summary,
)


def _make_stale(ticker: str) -> LivePosition:
    return LivePosition(
        position=_make_position_with_lot(ticker, "1", "100"),
        live_price_native=None,
        live_value_eur=None,
        unrealised_gain_eur=None,
        unrealised_gain_pct=None,
        current_fx_rate=None,
        staleness_reason="price feed unavailable",
    )


def _row(df, ticker):
    return df[df["Ticker"] == ticker].iloc[0]


# ---------------------------------------------------------------------------
# Column shape
# ---------------------------------------------------------------------------

def test_dataframe_has_expected_columns() -> None:
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    df = build_positions_dataframe(positions, _make_summary(positions))
    assert list(df.columns) == [
        "Ticker", "Name", "Price (€)", "Shares", "Cost (€)", "Value (€)",
        "Gain (€)", "Weight (%)", "Trend 30D (%)", "Lots", "Sim",
    ]


def test_dataframe_one_row_per_position() -> None:
    positions = {
        "NVDA": _make_live_position("NVDA", "5", "400"),
        "ANET": _make_live_position("ANET", "10", "100"),
    }
    df = build_positions_dataframe(positions, _make_summary(positions))
    assert len(df) == 2


def test_dataframe_empty_positions() -> None:
    df = build_positions_dataframe({}, _make_summary({}))
    assert df.empty
    assert list(df.columns)[0] == "Ticker"


# ---------------------------------------------------------------------------
# Computed values
# ---------------------------------------------------------------------------

def test_value_gain_price_weight_computed() -> None:
    # shares=5, cost/share=400 → value=5*120=600, cost=2000, gain=-1400, price=120
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    summary = _make_summary(positions)
    row = _row(build_positions_dataframe(positions, summary), "NVDA")
    assert row["Value (€)"] == 600.0
    assert row["Cost (€)"] == 2000.0
    assert row["Gain (€)"] == -1400.0
    assert row["Price (€)"] == 120.0
    # single position → 100% weight
    assert math.isclose(row["Weight (%)"], 100.0, rel_tol=1e-6)


def test_weight_is_proportional_across_positions() -> None:
    positions = {
        "BIG": _make_live_position("BIG", "10", "50"),   # value 1200
        "SMALL": _make_live_position("SMALL", "1", "50"),  # value 120
    }
    df = build_positions_dataframe(positions, _make_summary(positions))
    assert _row(df, "BIG")["Weight (%)"] > _row(df, "SMALL")["Weight (%)"]
    assert math.isclose(
        _row(df, "BIG")["Weight (%)"] + _row(df, "SMALL")["Weight (%)"], 100.0, rel_tol=1e-6
    )


def test_trend_value_passed_through() -> None:
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    df = build_positions_dataframe(
        positions, _make_summary(positions), trend_values={"NVDA": 2.5}
    )
    assert _row(df, "NVDA")["Trend 30D (%)"] == 2.5


def test_name_resolved_from_lookup() -> None:
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    df = build_positions_dataframe(
        positions, _make_summary(positions), name_lookup={"NVDA": "NVIDIA Corp"}
    )
    assert _row(df, "NVDA")["Name"] == "NVIDIA Corp"


def test_name_falls_back_to_ticker() -> None:
    positions = {"QDVE": _make_live_position("QDVE", "10", "50")}
    df = build_positions_dataframe(positions, _make_summary(positions))
    assert _row(df, "QDVE")["Name"] == "QDVE"


def test_sim_column_links_to_simulator() -> None:
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    df = build_positions_dataframe(positions, _make_summary(positions))
    assert _row(df, "NVDA")["Sim"] == "/?page=simulator&ticker=NVDA"


def test_usd_position_price_in_eur() -> None:
    positions = {"NVDA": _make_live_position_usd("NVDA", shares="5", price_usd="200")}
    summary = _make_summary(positions)
    row = _row(build_positions_dataframe(positions, summary), "NVDA")
    # price = value_eur / shares; both derived from the USD helper.
    assert row["Price (€)"] == row["Value (€)"] / row["Shares"]


# ---------------------------------------------------------------------------
# Stale rows → blank (None) values so they sort to the end
# ---------------------------------------------------------------------------

def test_stale_row_has_none_live_fields() -> None:
    positions = {"STALE": _make_stale("STALE")}
    row = _row(build_positions_dataframe(positions, _make_summary(positions)), "STALE")
    assert row["Price (€)"] is None
    assert row["Value (€)"] is None
    assert row["Gain (€)"] is None
    assert row["Weight (%)"] is None


def test_stale_row_keeps_book_fields() -> None:
    """Cost, shares and lots come from the book of record, so they stay populated."""
    positions = {"STALE": _make_stale("STALE")}
    row = _row(build_positions_dataframe(positions, _make_summary(positions)), "STALE")
    assert row["Cost (€)"] == 100.0  # 1 share * 100
    assert row["Shares"] == 1.0
    assert row["Lots"] == 1


# ---------------------------------------------------------------------------
# Weight bar colour-coding (gain-tinted, green/red/grey)
# ---------------------------------------------------------------------------

def test_weight_bar_green_when_gain_positive() -> None:
    css = _weight_bar_css(50.0, 100.0, 100.0)
    assert "38, 166, 154" in css  # green
    assert "50.0%" in css


def test_weight_bar_red_when_gain_negative() -> None:
    css = _weight_bar_css(20.0, -100.0, 100.0)
    assert "239, 83, 80" in css  # red


def test_weight_bar_grey_when_gain_missing() -> None:
    css = _weight_bar_css(20.0, None, 100.0)
    assert "120, 120, 120" in css  # neutral grey


def test_weight_bar_empty_when_weight_missing() -> None:
    assert _weight_bar_css(None, 100.0, 100.0) == ""


def test_weight_bar_scales_to_weight_max() -> None:
    # weight 25 against a max of 50 → bar fills 50%.
    css = _weight_bar_css(25.0, 10.0, 50.0)
    assert "50.0%" in css
