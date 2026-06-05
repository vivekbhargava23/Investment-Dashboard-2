# ruff: noqa: E501
"""Live Overview positions table.

Moved out of ``overview.py`` (TICKET-RD1) into a reusable component so RD2
(sorting) and RD6 (tranche expansion) can build on it. All styling lives in
dark.css — no inline ``style=`` attributes. Data-derived strings (ticker,
company name) are escaped via ``html.escape`` before interpolation because the
result is emitted through ``render_html`` (``unsafe_allow_html=True``); this
preserves the escaping TICKET-ROBUST-1 added.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from app.domain.positions import LivePosition, PortfolioSummary
from app.ui.components.weight_bar import render_weight_bar
from app.ui.format import format_eur
from app.ui.render import render_html

# Sortable columns and the keys the URL accepts (TICKET-RD2). The two trailing
# columns (Lots, Sim) carry ``None`` because they are decoration, not data.
_COLUMNS: tuple[tuple[str | None, str, str], ...] = (
    ("ticker", "Ticker", ""),
    ("name", "Name", ""),
    ("price", "Price (€)", "text-right"),
    ("shares", "Shares", "text-right"),
    ("cost", "Cost (€)", "text-right"),
    ("value", "Value (€)", "text-right"),
    ("gain", "Gain (€)", "text-right"),
    ("weight", "Weight", ""),
    ("trend", "Trend 30D", "text-right"),
    (None, "Lots", "text-center"),
    (None, "Sim", "text-center"),
)
SORT_KEYS: frozenset[str] = frozenset(key for key, _, _ in _COLUMNS if key)
DEFAULT_SORT_KEY = "value"
DEFAULT_DIRECTION = "desc"
# Text columns read more naturally A→Z on first click; numeric columns biggest-first.
_TEXT_KEYS: frozenset[str] = frozenset({"ticker", "name"})


def _is_stale(p: LivePosition) -> bool:
    return (
        p.live_price_native is None
        or p.live_value_eur is None
        or p.unrealised_gain_eur is None
    )


def _sort_value(
    p: LivePosition,
    sort_key: str,
    name_lookup: dict[str, str],
    trend_values: dict[str, float | None],
) -> Any:
    """Sortable scalar for a *non-stale* position. Stale rows are partitioned out
    before this is called, so the live-price fields are safe to read."""
    ticker = p.position.ticker
    if sort_key == "ticker":
        return ticker.lower()
    if sort_key == "name":
        return (name_lookup.get(ticker) or ticker).lower()
    if sort_key == "shares":
        return float(p.position.open_shares)
    if sort_key == "cost":
        return float(p.position.cost_basis_eur.amount)
    if sort_key == "gain":
        return float(p.unrealised_gain_eur.amount) if p.unrealised_gain_eur else 0.0
    if sort_key == "price":
        if p.live_value_eur is not None and p.position.open_shares:
            return float(p.live_value_eur.amount) / float(p.position.open_shares)
        return 0.0
    if sort_key == "trend":
        v = trend_values.get(ticker)
        return float(v) if v is not None else 0.0
    # "value" and "weight" share an ordering — weight is value / total.
    return float(p.live_value_eur.amount) if p.live_value_eur is not None else 0.0


def sort_positions(
    positions: Sequence[LivePosition],
    sort_key: str = DEFAULT_SORT_KEY,
    direction: str = DEFAULT_DIRECTION,
    *,
    name_lookup: dict[str, str] | None = None,
    trend_values: dict[str, float | None] | None = None,
) -> list[LivePosition]:
    """Return positions ordered by ``sort_key`` / ``direction``.

    Stale rows (missing live price/value/gain) always sort to the bottom in both
    directions — they never displace real data. Unknown keys/directions fall back
    to the default (value descending), so a junk URL degrades gracefully.
    """
    name_lookup = name_lookup or {}
    trend_values = trend_values or {}
    if sort_key not in SORT_KEYS:
        sort_key = DEFAULT_SORT_KEY
    if direction not in ("asc", "desc"):
        direction = DEFAULT_DIRECTION

    live = [p for p in positions if not _is_stale(p)]
    stale = [p for p in positions if _is_stale(p)]
    live.sort(
        key=lambda p: _sort_value(p, sort_key, name_lookup, trend_values),
        reverse=direction == "desc",
    )
    # Deterministic, direction-independent order for the always-last stale rows.
    stale.sort(key=lambda p: p.position.ticker)
    return live + stale


def _build_header(sort_key: str, direction: str) -> str:
    """Header row where each data column is a link toggling ``?sort=&dir=``.

    The active column shows ▲/▼ and its link flips the direction; an inactive
    column links to its natural default (A→Z for text, biggest-first for numbers).
    """
    cells: list[str] = []
    for key, label, css in _COLUMNS:
        cls = f' class="{css}"' if css else ""
        if key is None:
            cells.append(f"<th{cls}>{label}</th>")
            continue
        is_active = key == sort_key
        if is_active:
            next_dir = "asc" if direction == "desc" else "desc"
            arrow = " ▼" if direction == "desc" else " ▲"
            link_cls = "sort-link active"
        else:
            next_dir = "asc" if key in _TEXT_KEYS else "desc"
            arrow = ""
            link_cls = "sort-link"
        href = f"/?page=overview&sort={key}&dir={next_dir}"
        cells.append(
            f"<th{cls}>"
            f'<a class="{link_cls}" href="{href}" target="_self">{label}{arrow}</a>'
            f"</th>"
        )
    return (
        '<table class="positions-table"><thead><tr>'
        + "".join(cells)
        + "</tr></thead><tbody>"
    )


def build_positions_table_html(
    positions: dict[str, LivePosition],
    summary: PortfolioSummary,
    trend_data: dict[str, str] | None = None,
    name_lookup: dict[str, str] | None = None,
    *,
    sort_key: str = DEFAULT_SORT_KEY,
    direction: str = DEFAULT_DIRECTION,
    trend_values: dict[str, float | None] | None = None,
) -> str:
    """trend_data maps ticker → pre-formatted trend cell HTML (e.g. '↑ +2.3%' or '—').

    trend_values maps ticker → numeric 30D change (used only for sorting by trend).
    """
    if sort_key not in SORT_KEYS:
        sort_key = DEFAULT_SORT_KEY
    if direction not in ("asc", "desc"):
        direction = DEFAULT_DIRECTION

    _name_lookup = name_lookup or {}
    sorted_positions = sort_positions(
        list(positions.values()),
        sort_key,
        direction,
        name_lookup=_name_lookup,
        trend_values=trend_values,
    )

    tbody_rows: list[str] = []
    for p in sorted_positions:
        ticker = p.position.ticker
        name = _name_lookup.get(ticker, ticker)
        # Data-derived strings (portfolio ticker, isin_map name) must be escaped
        # before interpolation — render_html emits with unsafe_allow_html=True.
        ticker_safe = html.escape(ticker)
        name_safe = html.escape(name)

        shares = f"{p.position.open_shares:g}"
        cost = format_eur(p.position.cost_basis_eur, signed=False).replace("€", "")
        lots = len(p.position.open_lots)

        is_stale = p.live_price_native is None or p.live_value_eur is None or p.unrealised_gain_eur is None
        row_class = "stale" if is_stale else ""

        if is_stale or p.live_price_native is None or p.live_value_eur is None:
            price_cell = '<td class="font-mono text-right">—</td>'
        else:
            native_ccy = p.live_price_native.currency.value
            native_amt = float(p.live_price_native.amount)
            eur_per_share = float(p.live_value_eur.amount) / float(p.position.open_shares)
            if native_ccy != "EUR":
                tooltip = f"{native_ccy} {native_amt:.2f}"
                price_cell = (
                    f'<td class="font-mono text-right" title="{tooltip}">'
                    f'{eur_per_share:.2f}'
                    f'</td>'
                )
            else:
                price_cell = (
                    f'<td class="font-mono text-right">'
                    f'{eur_per_share:.2f}'
                    f'</td>'
                )

        val = "—" if is_stale or p.live_value_eur is None else format_eur(p.live_value_eur, signed=False).replace("€", "")
        gain = "—" if is_stale or p.unrealised_gain_eur is None else format_eur(p.unrealised_gain_eur, signed=True).replace("€", "")

        unrealised_gain_eur_amount = Decimal("0")
        if not is_stale and p.unrealised_gain_eur is not None:
            unrealised_gain_eur_amount = p.unrealised_gain_eur.amount

        gain_class = "gain-neutral" if is_stale else ("gain-positive" if unrealised_gain_eur_amount > 0 else "gain-negative" if unrealised_gain_eur_amount < 0 else "gain-neutral")

        weight_pct = Decimal("0")
        if not is_stale and p.live_value_eur is not None and summary.total_value_eur.amount > 0:
            weight_pct = p.live_value_eur.amount / summary.total_value_eur.amount * Decimal("100")

        weight_html = render_weight_bar(weight_pct, scale_max=Decimal("100"))

        sim_link = (
            f'<a class="sim-link" href="/?page=simulator&ticker={ticker_safe}" target="_self" '
            f'title="Simulate sell">⚡</a>'
        )
        trend_cell = (trend_data or {}).get(ticker, "—")
        tbody_rows.append(
            f'<tr class="{row_class}">'
            f'<td><strong>{ticker_safe}</strong></td>'
            f'<td class="col-name">{name_safe}</td>'
            f'{price_cell}'
            f'<td class="font-mono text-right">{shares}</td>'
            f'<td class="font-mono text-right">{cost}</td>'
            f'<td class="font-mono text-right"><strong>{val}</strong></td>'
            f'<td class="font-mono text-right {gain_class}">{gain}</td>'
            f'<td class="font-mono">{weight_html}</td>'
            f'<td class="font-mono text-right col-trend">{trend_cell}</td>'
            f'<td class="font-mono text-center col-meta">{lots}</td>'
            f'<td class="text-center">{sim_link}</td>'
            f'</tr>'
        )

    return _build_header(sort_key, direction) + "".join(tbody_rows) + "</tbody></table>"


def render_positions_table(
    positions: dict[str, LivePosition],
    summary: PortfolioSummary,
    trend_data: dict[str, str] | None = None,
    name_lookup: dict[str, str] | None = None,
    *,
    sort_key: str = DEFAULT_SORT_KEY,
    direction: str = DEFAULT_DIRECTION,
    trend_values: dict[str, float | None] | None = None,
) -> None:
    """Render the positions table inside a scrollable card."""
    table_html = build_positions_table_html(
        positions,
        summary,
        trend_data=trend_data,
        name_lookup=name_lookup,
        sort_key=sort_key,
        direction=direction,
        trend_values=trend_values,
    )
    render_html(f'<div class="metric-card table-card">{table_html}</div>')
