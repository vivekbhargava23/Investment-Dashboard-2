# ruff: noqa: E501
from datetime import datetime
from decimal import Decimal
from typing import Literal

import streamlit as st

from app.domain.market_data import ChartPeriod, OhlcUnavailableError
from app.domain.positions import LivePosition, PortfolioSummary
from app.domain.tax.models import TaxProfile, TaxYearSummary
from app.services.market_data import get_ohlc_history
from app.services.tax_planning import compute_current_tax_summary
from app.services.valuation import compute_live_positions, compute_portfolio_summary
from app.ui.cache_keys import transactions_signature
from app.ui.components.badges import render_thesis_badge
from app.ui.components.charts import render_candlestick
from app.ui.components.weight_bar import render_weight_bar
from app.ui.format import format_eur, format_pct
from app.ui.render import render_html
from app.ui.wiring import (
    get_fx_provider,
    get_isin_map_repo,
    get_ohlc_data_provider,
    get_price_provider,
    get_repository,
    get_tax_profile_repo,
)

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
_PERIOD_LABELS: dict[ChartPeriod, str] = {
    ChartPeriod.ONE_DAY: "1D",
    ChartPeriod.FIVE_DAY: "5D",
    ChartPeriod.ONE_MONTH: "1M",
    ChartPeriod.THREE_MONTH: "3M",
    ChartPeriod.SIX_MONTH: "6M",
    ChartPeriod.ONE_YEAR: "1Y",
    ChartPeriod.TWO_YEAR: "2Y",
    ChartPeriod.FIVE_YEAR: "5Y",
    ChartPeriod.YEAR_TO_DATE: "YTD",
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

        shares = f"{p.position.open_shares:g}"
        cost = format_eur(p.position.cost_basis_eur, signed=False).replace("€", "")
        lots = len(p.position.open_lots)
        horizon = _PLACEHOLDER_HORIZON.get(ticker, "H2")
        thesis = render_thesis_badge(_PLACEHOLDER_THESIS_STATUS.get(ticker, "intact"))

        is_stale = p.live_price_native is None or p.live_value_eur is None or p.unrealised_gain_eur is None
        row_class = "stale" if is_stale else ""

        if is_stale or p.live_price_native is None:
            price_cell = '<td class="font-mono text-right">—</td>'
        else:
            native_ccy = p.live_price_native.currency.value
            native_amt = float(p.live_price_native.amount)
            native_str = f"{native_ccy} {native_amt:.2f}"
            if p.live_value_eur is not None and p.position.open_shares > 0:
                eur_per_share = float(p.live_value_eur.amount) / float(p.position.open_shares)
                tooltip = f"{native_str} · €{eur_per_share:.2f} per share"
            else:
                tooltip = native_str
            price_cell = (
                f'<td class="font-mono text-right" title="{tooltip}">'
                f'{native_amt:.2f}'
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
            f'<a href="/?page=simulator&ticker={ticker}" target="_self" '
            f'title="Simulate sell" style="color: var(--text3); text-decoration: none; font-size: 14px;">⚡</a>'
        )
        trend_cell = (trend_data or {}).get(ticker, "—")
        tbody_rows.append(
            f'<tr class="{row_class}">'
            f'<td><strong>{ticker}</strong></td>'
            f'<td style="color: var(--text2);">{name}</td>'
            f'{price_cell}'
            f'<td class="font-mono text-right">{shares}</td>'
            f'<td class="font-mono text-right">{cost}</td>'
            f'<td class="font-mono text-right"><strong>{val}</strong></td>'
            f'<td class="font-mono text-right {gain_class}">{gain}</td>'
            f'<td class="font-mono">{weight_html}</td>'
            f'<td class="font-mono text-right" style="font-size: 11px;">{trend_cell}</td>'
            f'<td class="text-center">{horizon}</td>'
            f'<td class="text-center">{thesis}</td>'
            f'<td class="font-mono text-center" style="color: var(--text3);">{lots}</td>'
            f'<td class="text-center">{sim_link}</td>'
            f'</tr>'
        )

    header = (
        '<table class="positions-table" style="width: 100%; border-collapse: collapse; text-align: left; font-size: 13px;">'
        '<thead>'
        '<tr style="border-bottom: 1px solid var(--border); color: var(--text3); text-transform: uppercase; font-size: 10px; letter-spacing: 0.05em;">'
        '<th style="padding: 8px 4px;">Ticker</th>'
        '<th style="padding: 8px 4px;">Name</th>'
        '<th style="padding: 8px 4px; text-align: right;">Price</th>'
        '<th style="padding: 8px 4px; text-align: right;">Shares</th>'
        '<th style="padding: 8px 4px; text-align: right;">Cost (€)</th>'
        '<th style="padding: 8px 4px; text-align: right;">Value (€)</th>'
        '<th style="padding: 8px 4px; text-align: right;">Gain (€)</th>'
        '<th style="padding: 8px 4px;">Weight</th>'
        '<th style="padding: 8px 4px; text-align: right;">Trend 30D</th>'
        '<th style="padding: 8px 4px; text-align: center;">Horizon</th>'
        '<th style="padding: 8px 4px; text-align: center;">Thesis</th>'
        '<th style="padding: 8px 4px; text-align: center;">Lots</th>'
        '<th style="padding: 8px 4px; text-align: center;">Sim</th>'
        '</tr>'
        '</thead>'
        '<tbody>'
    )
    return header + "".join(tbody_rows) + "</tbody></table>"


def _fetch_trend_texts(tickers: list[str]) -> dict[str, str]:
    """Fetch 30-day OHLC for each ticker and return HTML trend text for the table.

    ticker → HTML span like '↑ +2.3%' (green) or '↓ -1.1%' (red) or '—' on error.
    Per-ticker errors are isolated: one failure never blocks other rows.
    """
    provider = get_ohlc_data_provider()
    trend_text_map: dict[str, str] = {}

    for ticker in tickers:
        try:
            series = get_ohlc_history(ticker, ChartPeriod.ONE_MONTH, provider=provider)
            pct = series.period_change_pct
            if pct is None:
                trend_text_map[ticker] = "—"
            elif pct >= 0:
                color = "var(--green, #26a69a)"
                trend_text_map[ticker] = f'<span style="color:{color};">↑ +{float(pct):.1f}%</span>'
            else:
                color = "var(--red, #ef5350)"
                trend_text_map[ticker] = f'<span style="color:{color};">↓ {float(pct):.1f}%</span>'
        except OhlcUnavailableError:
            trend_text_map[ticker] = "—"

    return trend_text_map


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

    isin_map_doc = get_isin_map_repo().load()
    name_lookup: dict[str, str] = {
        m.ticker: m.name
        for m in isin_map_doc.entries.values()
        if m.status == "mapped" and m.ticker
    }

    tickers = list(live_positions.keys())
    trend_text_map = _fetch_trend_texts(tickers)

    table_html = _build_positions_table_html(live_positions, summary, trend_data=trend_text_map, name_lookup=name_lookup)
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

    # ── Position Chart ────────────────────────────────────────────────────────
    if tickers:
        render_html('<div style="margin-top: 24px; margin-bottom: 8px; font-size: 11px; color: var(--text3); text-transform: uppercase; letter-spacing: 0.05em;">Position Chart</div>')
        col_ticker, col_period = st.columns([1, 3])
        with col_ticker:
            chart_ticker = st.selectbox(
                "Ticker",
                options=tickers,
                key="overview_chart_ticker",
                label_visibility="collapsed",
            )
        with col_period:
            chart_period: ChartPeriod = st.radio(
                "Period",
                options=list(ChartPeriod),
                horizontal=True,
                key="overview_chart_period",
                index=4,
                format_func=lambda p: _PERIOD_LABELS[p],
                label_visibility="collapsed",
            )
        if chart_ticker:
            ohlc_provider = get_ohlc_data_provider()
            try:
                series = get_ohlc_history(chart_ticker, chart_period, provider=ohlc_provider)
                render_candlestick(series, height=400)
            except OhlcUnavailableError as e:
                st.warning(f"Chart unavailable: {e.reason}")
