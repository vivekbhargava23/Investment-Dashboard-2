"""Tests for the Overview positions-table component.

The builder moved out of overview.py into app/ui/components/positions_table.py
(TICKET-RD1). These cover the HTML-leak regressions (TICKET-008b), the
HTML-escaping invariant (TICKET-ROBUST-1), the CCY/name/price-tooltip behaviour
(TICKET-CSV-10), and the RD1 redesign decision to drop the Thesis/Horizon
columns.
"""
from __future__ import annotations

from app.domain.positions import LivePosition
from app.ui.components.positions_table import (
    build_positions_table_html,
    render_positions_table,
)
from tests.unit.ui.test_overview_render import (
    _make_live_position,
    _make_live_position_usd,
    _make_position_with_lot,
    _make_summary,
)

# ---------------------------------------------------------------------------
# TICKET-008b: positions-table HTML leak (no leading whitespace / one table)
# ---------------------------------------------------------------------------

def test_positions_table_html_no_leading_whitespace() -> None:
    """Regression: HTML must start with '<', never whitespace (markdown code-block bug)."""
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary)
    assert html[0] == "<", (
        f"HTML must start with '<' at index 0 to avoid markdown code-block rendering. "
        f"Got: {html[:40]!r}"
    )


def test_positions_table_html_not_four_spaces() -> None:
    """4+ leading spaces triggers markdown code block."""
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary)
    assert not html.startswith("    "), f"Got: {html[:40]!r}"


def test_positions_table_html_one_table_tag() -> None:
    positions = {
        "NVDA": _make_live_position("NVDA", "5", "400"),
        "ANET": _make_live_position("ANET", "10", "100"),
    }
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary)
    assert html.count("<table") == 1


def test_positions_table_html_tr_per_position() -> None:
    positions = {
        "NVDA": _make_live_position("NVDA", "5", "400"),
        "ANET": _make_live_position("ANET", "10", "100"),
    }
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary)
    assert html.count("<tr") >= len(positions)


def test_positions_table_html_no_double_escaping() -> None:
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary)
    assert "&lt;" not in html, "Found &lt; — HTML is double-escaped"


def test_positions_table_html_empty_positions() -> None:
    summary = _make_summary({})
    html = build_positions_table_html({}, summary)
    assert "<table" in html
    assert html[0] == "<"


# ---------------------------------------------------------------------------
# TICKET-ROBUST-1: data-derived strings must be HTML-escaped before render_html.
# RD1 must preserve this when moving the table into a component.
# ---------------------------------------------------------------------------

def test_positions_table_escapes_company_name() -> None:
    """A company name containing markup renders as literal text, not as HTML."""
    positions = {"ACME": _make_live_position("ACME", "5", "400")}
    summary = _make_summary(positions)
    name_lookup = {"ACME": 'Acme <b>test</b> & "Co"'}

    html = build_positions_table_html(positions, summary, name_lookup=name_lookup)

    # Raw markup must NOT appear — it would break layout / inject into the page.
    assert "<b>test</b>" not in html
    # Escaped form must appear instead.
    assert "Acme &lt;b&gt;test&lt;/b&gt; &amp; &quot;Co&quot;" in html


def test_positions_table_escapes_ticker() -> None:
    """A ticker containing markup is escaped in both the cell and the sim link."""
    evil = 'X<img src=x>'
    positions = {evil: _make_live_position(evil, "5", "400")}
    summary = _make_summary(positions)

    html = build_positions_table_html(positions, summary)

    assert "<img src=x>" not in html
    assert "X&lt;img src=x&gt;" in html


# ---------------------------------------------------------------------------
# TICKET-RD1: Thesis/Horizon columns dropped from the positions table.
# ---------------------------------------------------------------------------

def test_no_thesis_or_horizon_headers() -> None:
    """The redesigned table has no Thesis or Horizon columns."""
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary)
    assert ">Thesis<" not in html
    assert ">Horizon<" not in html


def test_table_cells_use_classes_not_inline_styles() -> None:
    """The table's own markup is class-driven (the embedded weight-bar component
    keeps its own inline styles — that is out of scope for RD1)."""
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary)
    # The header row and cells the table owns carry classes, not style attrs.
    assert 'class="positions-table"' in html
    assert "style=" not in html.split("<tbody>")[0]  # header has no inline styles


# ---------------------------------------------------------------------------
# TICKET-CSV-10: CCY column removed, name lookup, price tooltip
# ---------------------------------------------------------------------------

def test_ccy_column_not_in_header() -> None:
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary)
    assert ">CCY<" not in html, "CCY header column should have been removed"


def test_ccy_value_not_in_body() -> None:
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary)
    assert ">EUR<" not in html, "EUR CCY cell should not appear as a standalone table cell"


def test_name_resolved_from_lookup() -> None:
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary, name_lookup={"NVDA": "NVIDIA Corp"})
    assert "NVIDIA Corp" in html


def test_name_fallback_to_ticker_when_not_in_lookup() -> None:
    positions = {"QDVE": _make_live_position("QDVE", "10", "50")}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary, name_lookup={})
    assert "QDVE" in html


def test_name_fallback_when_no_lookup_provided() -> None:
    positions = {"ANET": _make_live_position("ANET", "3", "200")}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary)
    assert "ANET" in html


def test_price_tooltip_usd_shows_native_in_tooltip() -> None:
    positions = {"NVDA": _make_live_position_usd("NVDA", shares="5", price_usd="225.32")}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary)
    assert 'title="USD 225.32"' in html, "Non-EUR price cell must show native currency in tooltip"


def test_price_eur_position_displays_eur_no_tooltip() -> None:
    positions = {"RHM.DE": _make_live_position("RHM.DE", "2", "800")}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary)
    assert 'title="EUR' not in html, "EUR-native price cell needs no tooltip"


def test_stale_price_renders_dash_no_tooltip() -> None:
    position = _make_position_with_lot("STALE", "3", "100")
    stale_p = LivePosition(
        position=position,
        live_price_native=None,
        live_value_eur=None,
        unrealised_gain_eur=None,
        unrealised_gain_pct=None,
        current_fx_rate=None,
        staleness_reason="price feed unavailable",
    )
    positions = {"STALE": stale_p}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary)
    assert "—" in html, "Stale row must render dash"
    assert 'title="USD' not in html, "Stale row must not have price tooltip"
    assert 'title="EUR' not in html, "Stale row must not have price tooltip"


# ---------------------------------------------------------------------------
# render_positions_table wrapper
# ---------------------------------------------------------------------------

def test_render_positions_table_wraps_in_scroll_card(monkeypatch) -> None:
    """The render wrapper emits the table inside a scrollable card via render_html."""
    captured: list[str] = []
    monkeypatch.setattr(
        "app.ui.components.positions_table.render_html",
        lambda html: captured.append(html),
    )
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    summary = _make_summary(positions)

    render_positions_table(positions, summary)

    assert len(captured) == 1
    assert 'class="metric-card table-card"' in captured[0]
    assert "<table" in captured[0]
