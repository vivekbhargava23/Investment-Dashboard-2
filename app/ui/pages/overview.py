# ruff: noqa: E501
from datetime import date, datetime

import streamlit as st

from app.domain.market_data import ChartPeriod, OhlcUnavailableError
from app.domain.positions import LivePosition, PortfolioSummary
from app.domain.returns import ReturnWindow, WindowStats
from app.domain.tax.models import TaxProfile, TaxYearSummary
from app.services.market_data import get_ohlc_histories, get_ohlc_history
from app.services.returns import compute_return_stats_by_period
from app.services.tax_planning import compute_current_tax_summary
from app.services.valuation import compute_live_positions, compute_portfolio_summary
from app.ui.cache_keys import transactions_signature
from app.ui.components.charts import render_candlestick
from app.ui.components.metric_card import build_metric_card
from app.ui.components.period_selector import (
    render_aggregation_toggle,
    render_return_window_selector,
)
from app.ui.components.positions_table import render_positions_table
from app.ui.components.progress_bar import render_progress_bar
from app.ui.components.treemap import render_treemap
from app.ui.format import format_eur, format_pct
from app.ui.render import render_html
from app.ui.wiring import (
    get_isin_map_repo,
    get_live_fx_provider,
    get_ohlc_data_provider,
    get_price_provider,
    get_repository,
    get_tax_profile_repo,
)

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
    return compute_live_positions(transactions, get_price_provider(), get_live_fx_provider())


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


@st.cache_data(ttl=60, show_spinner=False)
def _cached_return_stats_by_period(
    tx_sig: str, as_of_iso: str
) -> dict[str, dict[ReturnWindow, WindowStats | None]]:
    """Per-ticker return stats (pct + high/low) over the standard windows, cached once.

    Keyed on the transactions signature + `as_of` date so the treemap window
    selector (and the RD11 heatmap) re-read from this cache instead of recomputing.
    The ticker set is taken from the current live positions.
    """
    live_positions = _cached_live_positions(tx_sig)
    tickers = [position.ticker for position in live_positions.values()]
    return compute_return_stats_by_period(
        tickers,
        as_of=date.fromisoformat(as_of_iso),
        provider=get_ohlc_data_provider(),
    )


def _fetch_trend_values(tickers: list[str]) -> dict[str, float | None]:
    """Fetch 30-day OHLC and return the numeric % change per ticker for the table's
    Trend column. Per-ticker errors are isolated: one failure never blocks other
    rows (its value is None → blank cell).
    """
    provider = get_ohlc_data_provider()
    series_map = get_ohlc_histories(tickers, ChartPeriod.ONE_MONTH, provider=provider)
    trend_value_map: dict[str, float | None] = {}
    for ticker in tickers:
        series = series_map.get(ticker.strip().upper())
        pct = series.period_change_pct if series is not None else None
        trend_value_map[ticker] = float(pct) if pct is not None else None
    return trend_value_map


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

    ur_sub_color = "green" if ur_gain > 0 else "red" if ur_gain < 0 else "grey"
    render_html(
        '<div class="metric-row cols-2">'
        + build_metric_card(
            "Total Portfolio Value", val_fmt, sub_value=f"{cost_basis_eur} cost basis"
        )
        + build_metric_card(
            "Total Unrealised Gain",
            ur_gain_fmt,
            value_class=ur_class,
            sub_value=ur_pct_fmt,
            sub_color=ur_sub_color,
        )
        + "</div>"
    )

    if tax_summary is not None:
        spb_value = format_eur(tax_summary.sparerpauschbetrag_consumed_eur)
        spb_sub = "used of " + format_eur(tax_summary.sparerpauschbetrag_total_eur)
        headroom_value = format_eur(
            tax_summary.sparerpauschbetrag_remaining_eur
            + tax_summary.aktien_pot.remaining_carryforward_eur
            + tax_summary.general_pot.remaining_carryforward_eur
        )
        headroom_sub: str | None = "gain you can realise tax-free"
    else:
        spb_value = "—"
        spb_sub = "Tax profile unavailable"
        headroom_value = "—"
        headroom_sub = None

    render_html(
        '<div class="metric-row cols-3">'
        + build_metric_card("Positions", str(len(live_positions)), size="sm")
        + build_metric_card("Sparerpauschbetrag", spb_value, size="sm", sub_value=spb_sub)
        + build_metric_card(
            "Tax Headroom",
            headroom_value,
            size="sm",
            value_class="gain-positive",
            sub_value=headroom_sub,
        )
        + "</div>"
    )

    spb_pct = 0.0
    if tax_summary is not None and tax_summary.sparerpauschbetrag_total_eur.amount > 0:
        spb_pct = float(
            tax_summary.sparerpauschbetrag_consumed_eur.amount
            / tax_summary.sparerpauschbetrag_total_eur.amount
            * 100
        )
    render_html(f'<div class="mb-24">{render_progress_bar(spb_pct, height_px=4)}</div>')

    isin_map_doc = get_isin_map_repo().load()
    name_lookup: dict[str, str] = {
        m.ticker: m.name
        for m in isin_map_doc.entries.values()
        if m.status == "mapped" and m.ticker
    }

    tickers = list(live_positions.keys())
    trend_value_map = _fetch_trend_values(tickers)

    render_positions_table(
        live_positions,
        summary,
        name_lookup=name_lookup,
        trend_values=trend_value_map,
    )

    status_text = f"● LIVE · refreshed {now.strftime('%H:%M')}"
    if summary.staleness == "stale" or summary.staleness == "partial":
        stale_count = sum(1 for p in live_positions.values() if p.live_price_native is None)
        status_text = f"● PARTIAL · {stale_count} of {len(live_positions)} positions stale"

    render_html(f'<div class="status-line mt-16">{status_text}</div>')

    # ── Allocation Treemap ────────────────────────────────────────────────────
    # Tiles sized by live EUR value, coloured by the selected window's return.
    # The returns map is cached (keyed on tx-signature + as_of), so changing the
    # window re-colours instantly with no OHLC refetch and no return recompute.
    if tickers:
        render_html('<div class="section-eyebrow mt-24 mb-8">Allocation</div>')
        treemap_window = render_return_window_selector(
            "overview_treemap_window", default="30D"
        )
        stats_map = _cached_return_stats_by_period(sig, now.date().isoformat())
        render_treemap(
            live_positions,
            stats_map,
            treemap_window,
            name_lookup=name_lookup,
        )

    # ── Position Chart ────────────────────────────────────────────────────────
    if tickers:
        render_html('<div class="section-eyebrow mt-24 mb-8">Position Chart</div>')
        col_ticker, col_period, col_freq = st.columns([1, 2, 1])
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
        with col_freq:
            chart_freq = render_aggregation_toggle("overview_chart_freq", chart_period)
        if chart_ticker:
            ohlc_provider = get_ohlc_data_provider()
            try:
                series = get_ohlc_history(chart_ticker, chart_period, provider=ohlc_provider, freq=chart_freq)
                render_candlestick(series, height=400)
            except OhlcUnavailableError as e:
                st.warning(f"Chart unavailable: {e.reason}")
