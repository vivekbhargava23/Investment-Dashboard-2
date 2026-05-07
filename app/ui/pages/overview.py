# ruff: noqa: E501
from datetime import datetime
from decimal import Decimal
from typing import Literal

import streamlit as st

from app.domain.market_data import ChartPeriod, OhlcSeries, OhlcUnavailableError
from app.domain.positions import LivePosition, PortfolioSummary
from app.domain.tax.models import TaxProfile, TaxYearSummary
from app.services.market_data import get_ohlc_history
from app.services.tax_planning import compute_current_tax_summary
from app.services.valuation import compute_live_positions, compute_portfolio_summary
from app.ui.cache_keys import transactions_signature
from app.ui.components._chart_styles import CANDLE_DOWN, CANDLE_UP
from app.ui.components.badges import render_thesis_badge
from app.ui.components.charts import render_line_chart, render_sparkline
from app.ui.format import format_eur, format_pct
from app.ui.render import render_html
from app.ui.wiring import (
    get_fx_provider,
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
_PLACEHOLDER_NAME: dict[str, str] = {
    "NVDA": "NVIDIA", "RHM.DE": "Rheinmetall", "MU": "Micron", "HY9H.F": "SK Hynix",
    "MRVL": "Marvell", "APD": "Air Products", "ANET": "Arista", "AVGO": "Broadcom",
    "ETN": "Eaton", "ASX": "ASE Tech", "VUSA.DE": "S&P 500 ETF", "5631.T": "Japan Steel Works",
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


def _period_label(period: ChartPeriod) -> str:
    return _PERIOD_LABELS[period]


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


@st.cache_data(ttl=15 * 60, show_spinner=False)
def _cached_ohlc_for_overview(ticker: str, period_value: str) -> OhlcSeries:
    return get_ohlc_history(
        ticker,
        ChartPeriod(period_value),
        provider=get_ohlc_data_provider(),
    )


def _sorted_live_positions(positions: dict[str, LivePosition]) -> list[LivePosition]:
    return sorted(
        positions.values(),
        key=lambda p: float(p.live_value_eur.amount) if p.live_value_eur is not None else -1.0,
        reverse=True,
    )


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

        sim_link = (
            f'<a href="/?page=simulator&ticker={ticker}" target="_self" '
            f'title="Simulate sell" style="color: var(--text3); text-decoration: none; font-size: 14px;">⚡</a>'
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
            f'<td class="text-center">{sim_link}</td>'
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
        '<th style="padding: 8px 4px; text-align: center;">Sim</th>'
        '</tr>'
        '</thead>'
        '<tbody>'
    )
    return header + "".join(tbody_rows) + "</tbody></table>"


def _position_gain_class(position: LivePosition) -> str:
    if position.unrealised_gain_eur is None:
        return "gain-neutral"
    if position.unrealised_gain_eur.amount > 0:
        return "gain-positive"
    if position.unrealised_gain_eur.amount < 0:
        return "gain-negative"
    return "gain-neutral"


def _position_weight_pct(position: LivePosition, summary: PortfolioSummary) -> Decimal:
    if position.live_value_eur is None or summary.total_value_eur.amount <= 0:
        return Decimal("0")
    return position.live_value_eur.amount / summary.total_value_eur.amount * Decimal("100")


def _trend_placeholder() -> None:
    st.markdown("—")


def _render_trend_cell(ticker: str) -> None:
    try:
        series = _cached_ohlc_for_overview(ticker, ChartPeriod.ONE_MONTH.value)
    except OhlcUnavailableError:
        _trend_placeholder()
        return
    trend_cols = st.columns([0.76, 0.24], gap="small")
    with trend_cols[0]:
        render_sparkline(series, height=30, width=100)
    with trend_cols[1]:
        _render_chart_button(ticker)


def _render_chart_button(ticker: str) -> None:
    selected = st.session_state.get("overview_selected_ticker")
    label = "×" if selected == ticker else "🔍"
    help_text = "Close chart" if selected == ticker else f"Open {ticker} chart"
    if st.button(label, key=f"overview_chart_{ticker}", help=help_text):
        st.session_state["overview_selected_ticker"] = None if selected == ticker else ticker


def _render_sell_button(ticker: str) -> None:
    if st.button("📉", key=f"overview_sell_{ticker}", help=f"Simulate selling {ticker}"):
        st.session_state["simulator_default_ticker"] = ticker
        st.query_params["page"] = "simulator"


def _render_positions_table(
    positions: dict[str, LivePosition],
    summary: PortfolioSummary,
) -> None:
    render_html("""
        <div style="font-size: 15px; font-weight: 700; margin: 22px 0 8px;">
            Positions
        </div>
    """)
    col_spec = [1.0, 1.4, 0.8, 0.8, 1.2, 1.1, 1.1, 0.9, 0.45]
    header = st.columns(col_spec, gap="small")
    labels = ("Ticker", "Name", "Price", "Shares", "Trend", "Value", "Gain", "Weight", "Sell")
    for col, label in zip(header, labels, strict=True):
        with col:
            st.caption(label)

    for position in _sorted_live_positions(positions):
        ticker = position.position.ticker
        is_stale = (
            position.live_price_native is None
            or position.live_value_eur is None
            or position.unrealised_gain_eur is None
        )
        price = "—" if position.live_price_native is None else f"{position.live_price_native.amount:.2f}"
        shares = f"{position.position.open_shares:g}"
        value = "—" if position.live_value_eur is None else format_eur(position.live_value_eur)
        gain = "—" if position.unrealised_gain_eur is None else format_eur(
            position.unrealised_gain_eur,
            signed=True,
        )
        weight = _position_weight_pct(position, summary)
        gain_class = _position_gain_class(position)
        stale_style = "color: var(--text3);" if is_stale else ""

        cols = st.columns(col_spec, gap="small")
        with cols[0]:
            st.markdown(f"**{ticker}**")
        with cols[1]:
            st.caption(_PLACEHOLDER_NAME.get(ticker, ticker))
        with cols[2]:
            render_html(f"<span style='{stale_style}'>{price}</span>")
        with cols[3]:
            st.markdown(shares)
        with cols[4]:
            _render_trend_cell(ticker)
        with cols[5]:
            st.markdown(f"**{value}**")
        with cols[6]:
            render_html(f'<span class="{gain_class}">{gain}</span>')
        with cols[7]:
            st.markdown(f"{weight:.1f}%")
        with cols[8]:
            _render_sell_button(ticker)


def _mini_chart_color(series: OhlcSeries) -> str:
    change = series.period_change_pct or Decimal("0")
    return CANDLE_UP if change >= 0 else CANDLE_DOWN


def _render_mini_chart_panel() -> None:
    selected = st.session_state.get("overview_selected_ticker")
    if not selected:
        return

    periods = list(ChartPeriod)
    selected_period = st.radio(
        "Chart period",
        options=periods,
        horizontal=True,
        key="overview_chart_period",
        index=periods.index(ChartPeriod.SIX_MONTH),
        format_func=_period_label,
    )

    render_html(f"""
        <div style="font-size: 15px; font-weight: 700; margin: 22px 0 8px;">
            {selected} — {_period_label(selected_period)} price
        </div>
    """)
    try:
        series = _cached_ohlc_for_overview(selected, selected_period.value)
    except OhlcUnavailableError as exc:
        st.warning(f"Chart unavailable: {exc.reason}")
    else:
        render_line_chart(series, height=300, color=_mini_chart_color(series))

    if st.button("Close chart", key="overview_close_chart"):
        st.session_state["overview_selected_ticker"] = None
        st.rerun()


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

    _render_positions_table(live_positions, summary)
    _render_mini_chart_panel()

    status_text = f"● LIVE · refreshed {now.strftime('%H:%M')}"
    if summary.staleness == "stale" or summary.staleness == "partial":
        stale_count = sum(1 for p in live_positions.values() if p.live_price_native is None)
        status_text = f"● PARTIAL · {stale_count} of {len(live_positions)} positions stale"

    render_html(f"""
        <div style="margin-top: 16px; font-size: 11px; font-family: 'DM Mono', monospace; color: var(--text3); text-align: right;">
            {status_text}
        </div>
    """)
