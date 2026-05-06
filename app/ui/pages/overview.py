# ruff: noqa: E501
from datetime import datetime
from decimal import Decimal
from typing import Literal

import streamlit as st

from app.domain.positions import LivePosition, PortfolioSummary
from app.domain.tax.models import TaxProfile, TaxYearSummary
from app.services.tax_planning import compute_current_tax_summary
from app.services.valuation import compute_live_positions, compute_portfolio_summary
from app.ui.cache_keys import transactions_signature
from app.ui.components.badges import render_thesis_badge
from app.ui.format import format_eur, format_pct
from app.ui.render import render_html
from app.ui.wiring import get_fx_provider, get_price_provider, get_repository, get_tax_profile_repo

_PLACEHOLDER_THESIS_STATUS: dict[str, Literal["intact", "watch", "broken"]] = {
    "NVDA": "intact", "RHM.DE": "intact", "MU": "intact", "HY9H.F": "intact",
    "MRVL": "intact", "APD": "watch", "ANET": "intact", "AVGO": "intact",
    "ETN": "intact", "ASX": "intact", "VUSA.DE": "intact", "5631.T": "intact",
}
_PLACEHOLDER_HORIZON: dict[str, Literal["H1", "H2", "H3"]] = {
    "NVDA": "H1", "ETN": "H1", "ANET": "H1",
    "RHM.DE": "H2", "MU": "H2", "HY9H.F": "H2", "MRVL": "H2", "APD": "H2",
    "AVGO": "H2", "ASX": "H2", "VUSA.DE": "H3", "5631.T": "H3",
}
_PLACEHOLDER_NAME: dict[str, str] = {
    "NVDA": "NVIDIA", "RHM.DE": "Rheinmetall", "MU": "Micron", "HY9H.F": "SK Hynix",
    "MRVL": "Marvell", "APD": "Air Products", "ANET": "Arista", "AVGO": "Broadcom",
    "ETN": "Eaton", "ASX": "ASE Tech", "VUSA.DE": "S&P 500 ETF", "5631.T": "Japan Steel Works",
}


@st.cache_data(ttl=60, show_spinner=False)
def _cached_live_positions(tx_sig: str) -> dict[str, LivePosition]:
    transactions = get_repository().load_all()
    return compute_live_positions(transactions, get_price_provider(), get_fx_provider())


@st.cache_data(ttl=60, show_spinner=False)
def _cached_portfolio_summary(tx_sig: str, as_of_iso: str) -> PortfolioSummary:
    live_positions = _cached_live_positions(tx_sig)
    return compute_portfolio_summary(live_positions, datetime.fromisoformat(as_of_iso))


@st.cache_data(ttl=60, show_spinner=False)
def _cached_tax_summary_for_overview(tx_sig: str, year: int) -> TaxYearSummary | None:
    try:
        repo = get_tax_profile_repo()
        doc = repo.load()
        inputs = doc.inputs_for_year(year)
        profile = TaxProfile(filing_status=doc.filing_status)
        txs = get_repository().load_all()
        return compute_current_tax_summary(
            transactions=txs,
            profile=profile,
            carryforward_eur_aktien=inputs.carryforward_aktien_eur,
            carryforward_eur_general=inputs.carryforward_general_eur,
            additional_dividend_income_eur=inputs.additional_dividend_income_eur,
            additional_interest_income_eur=inputs.additional_interest_income_eur,
            as_of=datetime(year, 12, 31),
        )
    except Exception:
        return None


def _build_positions_table_html(
    positions: dict[str, LivePosition],
    summary: PortfolioSummary,
) -> str:
    sorted_positions = sorted(
        positions.values(),
        key=lambda p: float(p.live_value_eur.amount) if p.live_value_eur is not None else -1.0,
        reverse=True,
    )

    tbody_rows: list[str] = []
    for p in sorted_positions:
        ticker = p.position.ticker
        name = _PLACEHOLDER_NAME.get(ticker, ticker)

        ccy = "EUR"
        if len(p.position.open_lots) > 0:
            ccy = p.position.open_lots[0].cost_per_share_native.currency.value

        shares = f"{p.position.open_shares:g}"
        cost = format_eur(p.position.cost_basis_eur, signed=False).replace("€", "")
        lots = len(p.position.open_lots)
        horizon = _PLACEHOLDER_HORIZON.get(ticker, "H2")
        thesis = render_thesis_badge(_PLACEHOLDER_THESIS_STATUS.get(ticker, "intact"))

        is_stale = p.live_price_native is None or p.live_value_eur is None or p.unrealised_gain_eur is None
        row_class = "stale" if is_stale else ""

        price = "—" if is_stale or p.live_price_native is None else f"{float(p.live_price_native.amount):.2f}"
        val = "—" if is_stale or p.live_value_eur is None else format_eur(p.live_value_eur, signed=False).replace("€", "")
        gain = "—" if is_stale or p.unrealised_gain_eur is None else format_eur(p.unrealised_gain_eur, signed=True).replace("€", "")

        unrealised_gain_eur_amount = Decimal("0")
        if not is_stale and p.unrealised_gain_eur is not None:
            unrealised_gain_eur_amount = p.unrealised_gain_eur.amount

        gain_class = "gain-neutral" if is_stale else ("gain-positive" if unrealised_gain_eur_amount > 0 else "gain-negative" if unrealised_gain_eur_amount < 0 else "gain-neutral")

        weight_pct = 0.0
        if not is_stale and p.live_value_eur is not None and summary.total_value_eur.amount > 0:
            weight_pct = float(p.live_value_eur.amount / summary.total_value_eur.amount) * 100

        weight_html = (
            f'<div style="display: flex; align-items: center; gap: 4px;">'
            f'<span>{weight_pct:.1f}%</span>'
            f'<div style="width: 30px; height: 4px; background: var(--surface2); border-radius: 2px; overflow: hidden;">'
            f'<div style="width: {weight_pct}%; height: 100%; background: var(--blue);"></div>'
            f'</div></div>'
        )

        tbody_rows.append(
            f'<tr class="{row_class}">'
            f'<td><strong>{ticker}</strong></td>'
            f'<td style="color: var(--text2);">{name}</td>'
            f'<td style="color: var(--text3);">{ccy}</td>'
            f'<td class="font-mono text-right">{price}</td>'
            f'<td class="font-mono text-right">{shares}</td>'
            f'<td class="font-mono text-right">{cost}</td>'
            f'<td class="font-mono text-right"><strong>{val}</strong></td>'
            f'<td class="font-mono text-right {gain_class}">{gain}</td>'
            f'<td class="font-mono">{weight_html}</td>'
            f'<td class="text-center">{horizon}</td>'
            f'<td class="text-center">{thesis}</td>'
            f'<td class="font-mono text-center" style="color: var(--text3);">{lots}</td>'
            f'</tr>'
        )

    header = (
        '<table class="positions-table" style="width: 100%; border-collapse: collapse; text-align: left; font-size: 13px;">'
        '<thead>'
        '<tr style="border-bottom: 1px solid var(--border); color: var(--text3); text-transform: uppercase; font-size: 10px; letter-spacing: 0.05em;">'
        '<th style="padding: 8px 4px;">Ticker</th>'
        '<th style="padding: 8px 4px;">Name</th>'
        '<th style="padding: 8px 4px;">CCY</th>'
        '<th style="padding: 8px 4px; text-align: right;">Price</th>'
        '<th style="padding: 8px 4px; text-align: right;">Shares</th>'
        '<th style="padding: 8px 4px; text-align: right;">Cost (€)</th>'
        '<th style="padding: 8px 4px; text-align: right;">Value (€)</th>'
        '<th style="padding: 8px 4px; text-align: right;">Gain (€)</th>'
        '<th style="padding: 8px 4px;">Weight</th>'
        '<th style="padding: 8px 4px; text-align: center;">Horizon</th>'
        '<th style="padding: 8px 4px; text-align: center;">Thesis</th>'
        '<th style="padding: 8px 4px; text-align: center;">Lots</th>'
        '</tr>'
        '</thead>'
        '<tbody>'
    )
    return header + "".join(tbody_rows) + "</tbody></table>"


def render() -> None:
    repo = get_repository()
    transactions = repo.load_all()
    sig = transactions_signature(transactions)
    now = datetime.now()
    now_iso = now.isoformat()

    live_positions = _cached_live_positions(sig)
    summary = _cached_portfolio_summary(sig, now_iso)
    tax_summary = _cached_tax_summary_for_overview(sig, now.year)

    cost_basis_eur = format_eur(summary.total_cost_basis_eur)
    ur_gain = summary.total_unrealised_gain_eur.amount
    ur_class = (
        "gain-positive" if ur_gain > 0
        else "gain-negative" if ur_gain < 0
        else "gain-neutral"
    )
    ur_gain_fmt = format_eur(summary.total_unrealised_gain_eur, signed=True)
    ur_pct_fmt = format_pct(summary.total_unrealised_gain_pct, signed=True)
    val_fmt = format_eur(summary.total_value_eur)

    render_html(f"""
        <div class="metric-row cols-2">
            <div class="metric-card">
                <div class="metric-label">Total Portfolio Value</div>
                <div class="metric-value">{val_fmt}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">
                    {cost_basis_eur} cost basis
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Unrealised Gain</div>
                <div class="metric-value {ur_class}">{ur_gain_fmt}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;" class="{ur_class}">
                    {ur_pct_fmt}
                </div>
            </div>
        </div>
    """)

    # Intentionally split sum across lines to avoid E501
    intact_count = sum(
        1 for t in live_positions
        if _PLACEHOLDER_THESIS_STATUS.get(t, "intact") == "intact"
    )
    watch_count = sum(
        1 for t in live_positions
        if _PLACEHOLDER_THESIS_STATUS.get(t, "intact") == "watch"
    )
    broken_count = sum(
        1 for t in live_positions
        if _PLACEHOLDER_THESIS_STATUS.get(t, "intact") == "broken"
    )

    thesis_pill_html = "".join([
        f'<span class="badge {"badge-green" if _PLACEHOLDER_THESIS_STATUS.get(t, "intact") == "intact" else "badge-amber" if _PLACEHOLDER_THESIS_STATUS.get(t, "intact") == "watch" else "badge-red"}" style="margin-right: 2px;">{t}</span>'
        for t in live_positions
    ])

    render_html(f"""
        <div class="metric-row cols-4">
            <div class="metric-card">
                <div class="metric-label">Positions</div>
                <div class="metric-value sm">{len(live_positions)}</div>
                <div style="margin-top: 6px;">{thesis_pill_html}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Thesis Status</div>
                <div class="metric-value sm" style="font-size: 14px;">
                    <span class="gain-positive">{intact_count} intact</span> ·
                    <span class="gain-amber">{watch_count} watch</span> ·
                    <span class="gain-negative">{broken_count} broken</span>
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Sparerpauschbetrag</div>
                <div class="metric-value sm">{format_eur(tax_summary.sparerpauschbetrag_consumed_eur) if tax_summary else "—"}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">
                    {"used of " + format_eur(tax_summary.sparerpauschbetrag_total_eur) if tax_summary else "Tax profile unavailable"}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Tax Headroom</div>
                <div class="metric-value sm gain-positive">{format_eur(tax_summary.sparerpauschbetrag_remaining_eur + tax_summary.aktien_pot.remaining_carryforward_eur + tax_summary.general_pot.remaining_carryforward_eur) if tax_summary else "—"}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">
                    {"gain you can realise tax-free" if tax_summary else ""}
                </div>
            </div>
        </div>
        <div style="width: 100%; height: 4px; background: var(--surface2); border-radius: 2px; margin-bottom: 24px; overflow: hidden;">
            <div style="width: {min(100.0, float(tax_summary.sparerpauschbetrag_consumed_eur.amount / tax_summary.sparerpauschbetrag_total_eur.amount * 100)) if tax_summary and tax_summary.sparerpauschbetrag_total_eur.amount > 0 else 0:.1f}%; height: 100%; background: var(--green);"></div>
        </div>
    """)

    table_html = _build_positions_table_html(live_positions, summary)
    render_html(f'<div class="metric-card" style="padding: 0; overflow-x: auto;">{table_html}</div>')

    status_text = f"● LIVE · refreshed {now.strftime('%H:%M')}"
    if summary.staleness == "stale" or summary.staleness == "partial":
        stale_count = sum(1 for p in live_positions.values() if p.live_price_native is None)
        status_text = f"● PARTIAL · {stale_count} of {len(live_positions)} positions stale"

    render_html(f"""
        <div style="margin-top: 16px; font-size: 11px; font-family: 'DM Mono', monospace; color: var(--text3); text-align: right;">
            {status_text}
        </div>
    """)
