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
    sort_positions,
)
from tests.unit.ui.test_overview_render import (
    _make_live_position,
    _make_live_position_usd,
    _make_position_with_lot,
    _make_summary,
)


def _make_stale(ticker: str) -> LivePosition:
    """A position with no live data — must always sort to the bottom."""
    return LivePosition(
        position=_make_position_with_lot(ticker, "1", "100"),
        live_price_native=None,
        live_value_eur=None,
        unrealised_gain_eur=None,
        unrealised_gain_pct=None,
        current_fx_rate=None,
        staleness_reason="price feed unavailable",
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


# ---------------------------------------------------------------------------
# TICKET-RD2: sort_positions — pure ordering by each key, both directions
# ---------------------------------------------------------------------------

def _tickers(positions: list[LivePosition]) -> list[str]:
    return [p.position.ticker for p in positions]


def test_sort_default_is_value_descending() -> None:
    """No args → value descending (the pre-RD2 behaviour) — regression guard."""
    # value = shares * 120, so SMALL=120, MID=600, BIG=1200.
    small = _make_live_position("SMALL", "1", "50")
    mid = _make_live_position("MID", "5", "50")
    big = _make_live_position("BIG", "10", "50")
    out = sort_positions([small, big, mid])
    assert _tickers(out) == ["BIG", "MID", "SMALL"]


def test_sort_value_ascending() -> None:
    small = _make_live_position("SMALL", "1", "50")
    big = _make_live_position("BIG", "10", "50")
    out = sort_positions([big, small], "value", "asc")
    assert _tickers(out) == ["SMALL", "BIG"]


def test_sort_ticker_both_directions() -> None:
    a = _make_live_position("AAA", "1", "50")
    z = _make_live_position("ZZZ", "1", "50")
    assert _tickers(sort_positions([z, a], "ticker", "asc")) == ["AAA", "ZZZ"]
    assert _tickers(sort_positions([a, z], "ticker", "desc")) == ["ZZZ", "AAA"]


def test_sort_name_uses_name_lookup() -> None:
    nv = _make_live_position("NV", "1", "50")
    ap = _make_live_position("AP", "1", "50")
    lookup = {"NV": "Nvidia", "AP": "Apple"}
    out = sort_positions([nv, ap], "name", "asc", name_lookup=lookup)
    assert _tickers(out) == ["AP", "NV"]  # Apple < Nvidia


def test_sort_shares_descending() -> None:
    few = _make_live_position("FEW", "2", "50")
    many = _make_live_position("MANY", "20", "50")
    out = sort_positions([few, many], "shares", "desc")
    assert _tickers(out) == ["MANY", "FEW"]


def test_sort_cost_ascending() -> None:
    # cost basis = shares * cost → CHEAP=100, PRICEY=1000
    cheap = _make_live_position("CHEAP", "2", "50")
    pricey = _make_live_position("PRICEY", "10", "100")
    out = sort_positions([pricey, cheap], "cost", "asc")
    assert _tickers(out) == ["CHEAP", "PRICEY"]


def test_sort_gain_descending() -> None:
    # gain = shares*120 - shares*cost. LOSER cost 200 → -160; WINNER cost 50 → +70.
    winner = _make_live_position("WINNER", "1", "50")
    loser = _make_live_position("LOSER", "2", "200")
    out = sort_positions([loser, winner], "gain", "desc")
    assert _tickers(out) == ["WINNER", "LOSER"]


def test_sort_trend_uses_trend_values() -> None:
    up = _make_live_position("UP", "1", "50")
    down = _make_live_position("DOWN", "1", "50")
    trend = {"UP": 5.0, "DOWN": -3.0}
    out = sort_positions([down, up], "trend", "desc", trend_values=trend)
    assert _tickers(out) == ["UP", "DOWN"]


def test_sort_weight_matches_value_order() -> None:
    small = _make_live_position("SMALL", "1", "50")
    big = _make_live_position("BIG", "10", "50")
    assert _tickers(sort_positions([small, big], "weight", "desc")) == ["BIG", "SMALL"]


def test_stale_rows_always_last_descending() -> None:
    live = _make_live_position("LIVE", "5", "50")
    stale = _make_stale("STALE")
    out = sort_positions([stale, live], "value", "desc")
    assert _tickers(out) == ["LIVE", "STALE"]


def test_stale_rows_always_last_ascending() -> None:
    """Even ascending, stale never floats to the top to displace real data."""
    live = _make_live_position("LIVE", "5", "50")
    stale = _make_stale("STALE")
    out = sort_positions([stale, live], "value", "asc")
    assert _tickers(out) == ["LIVE", "STALE"]


def test_multiple_stale_rows_kept_deterministic_and_last() -> None:
    live = _make_live_position("LIVE", "5", "50")
    s1 = _make_stale("ZSTALE")
    s2 = _make_stale("ASTALE")
    out = sort_positions([s1, live, s2], "value", "desc")
    assert _tickers(out) == ["LIVE", "ASTALE", "ZSTALE"]


def test_unknown_sort_key_falls_back_to_value_desc() -> None:
    small = _make_live_position("SMALL", "1", "50")
    big = _make_live_position("BIG", "10", "50")
    out = sort_positions([small, big], "bogus", "sideways")
    assert _tickers(out) == ["BIG", "SMALL"]


# ---------------------------------------------------------------------------
# TICKET-RD2: header renders sort links + active-column arrow
# ---------------------------------------------------------------------------

def test_header_columns_are_sort_links() -> None:
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary)
    header = html.split("<tbody>")[0]
    assert 'href="/?page=overview&sort=gain&dir=desc"' in header
    assert 'href="/?page=overview&sort=ticker&dir=asc"' in header


def test_active_column_shows_arrow_and_flips_direction() -> None:
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    summary = _make_summary(positions)
    html = build_positions_table_html(positions, summary, sort_key="value", direction="desc")
    header = html.split("<tbody>")[0]
    # active column shows ▼ and its link flips to asc
    assert "Value (€) ▼" in header
    assert 'href="/?page=overview&sort=value&dir=asc"' in header


def test_lots_and_sim_headers_are_not_links() -> None:
    positions = {"NVDA": _make_live_position("NVDA", "5", "400")}
    summary = _make_summary(positions)
    header = build_positions_table_html(positions, summary).split("<tbody>")[0]
    assert "<th class=\"text-center\">Lots</th>" in header
    assert "sort=lots" not in header
