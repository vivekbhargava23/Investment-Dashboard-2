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
from decimal import Decimal

from app.domain.positions import LivePosition, PortfolioSummary
from app.ui.components.weight_bar import render_weight_bar
from app.ui.format import format_eur
from app.ui.render import render_html

_HEADER = (
    '<table class="positions-table">'
    "<thead>"
    "<tr>"
    "<th>Ticker</th>"
    "<th>Name</th>"
    '<th class="text-right">Price (€)</th>'
    '<th class="text-right">Shares</th>'
    '<th class="text-right">Cost (€)</th>'
    '<th class="text-right">Value (€)</th>'
    '<th class="text-right">Gain (€)</th>'
    "<th>Weight</th>"
    '<th class="text-right">Trend 30D</th>'
    '<th class="text-center">Lots</th>'
    '<th class="text-center">Sim</th>'
    "</tr>"
    "</thead>"
    "<tbody>"
)


def build_positions_table_html(
    positions: dict[str, LivePosition],
    summary: PortfolioSummary,
    trend_data: dict[str, str] | None = None,
    name_lookup: dict[str, str] | None = None,
) -> str:
    """trend_data maps ticker → pre-formatted trend cell HTML (e.g. '↑ +2.3%' or '—')."""
    sorted_positions = sorted(
        positions.values(),
        key=lambda p: float(p.live_value_eur.amount) if p.live_value_eur is not None else -1.0,
        reverse=True,
    )

    _name_lookup = name_lookup or {}
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

    return _HEADER + "".join(tbody_rows) + "</tbody></table>"


def render_positions_table(
    positions: dict[str, LivePosition],
    summary: PortfolioSummary,
    trend_data: dict[str, str] | None = None,
    name_lookup: dict[str, str] | None = None,
) -> None:
    """Render the positions table inside a scrollable card."""
    table_html = build_positions_table_html(
        positions, summary, trend_data=trend_data, name_lookup=name_lookup
    )
    render_html(f'<div class="metric-card table-card">{table_html}</div>')
