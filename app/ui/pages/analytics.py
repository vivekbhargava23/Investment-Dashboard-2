"""Analytics page.

The Performance tab calls ``analytics.drawdown_series`` directly to derive the
area-chart values from ``PerformanceView.portfolio_navs_raw``. That is the
explicit A1 exception to the usual page -> service -> domain flow: max drawdown
is a service fact, while the full drawdown series only feeds one visual.
"""

from __future__ import annotations

import html
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Literal, cast

import pandas as pd
import streamlit as st

from app.domain import analytics
from app.domain.analytics_views import ConcentrationView, SizerView
from app.domain.market_data import ChartPeriod
from app.domain.money import Currency
from app.domain.nav import DailyNavPoint
from app.domain.positions import LivePosition, PortfolioSummary
from app.ports.market_data import OhlcDataProvider
from app.ports.nav_repository import NavSnapshotRepository
from app.ports.repository import TransactionRepository
from app.services.analytics_concentration import (
    BAR_SCALE_MAX_PCT,
    HHI_GREEN_LT,
    HHI_RED_GTE,
    MAX_POSITION_WEIGHT_PCT,
    TOP_1_GREEN_LT_PCT,
    TOP_1_RED_GTE_PCT,
    TOP_3_GREEN_LT_PCT,
    TOP_3_RED_GTE_PCT,
    compute_concentration_view,
)
from app.services.analytics_correlation import (
    CLUSTER_THRESHOLD,
    CorrelationView,
    build_correlation_view,
    diversification_bucket,
)
from app.services.analytics_performance import (
    BenchmarkLabel,
    NavSeriesProvider,
    PerformancePeriod,
    PerformanceView,
    get_performance_view,
)
from app.services.analytics_sizer import (
    BAR_SCALE_MAX_PCT as SIZER_BAR_SCALE_MAX_PCT,
)
from app.services.analytics_sizer import (
    DEFAULT_RISK_PCT,
    DEFAULT_STOP_PCT,
    DEFAULT_TARGET_WEIGHT_PCT,
    compute_sizer_view,
)
from app.services.analytics_sizer import (
    MAX_POSITION_WEIGHT_PCT as SIZER_MAX_POSITION_WEIGHT_PCT,
)
from app.services.nav import get_nav_series
from app.services.valuation import compute_live_positions, compute_portfolio_summary
from app.ui.cache_keys import transactions_signature
from app.ui.components._chart_styles import CORRELATION_COLORSCALE_OPTIONS
from app.ui.components.charts import (
    ChartPoint,
    ChartSeries,
    render_correlation_heatmap,
    render_currency_donut,
    render_drawdown_chart,
    render_line_chart,
    render_weight_bar_chart,
)
from app.ui.components.metric_card import render_metric_card
from app.ui.components.weight_bar import render_weight_bar
from app.ui.format import format_eur, format_pct, format_shares, gain_class
from app.ui.render import render_html
from app.ui.wiring import (
    get_fx_provider,
    get_nav_snapshot_repo,
    get_ohlc_data_provider,
    get_price_provider,
    get_repository,
)

_BENCHMARK_OPTIONS: list[BenchmarkLabel] = ["SPY", "EUNL", "None"]
_EMPTY_STATE = "Performance data is being collected. Check back after the next NAV snapshot."
_CONCENTRATION_EMPTY_STATE = "No positions yet — add transactions in Manage Portfolio."
_SIZER_EMPTY_STATE = "No positions yet — add transactions in Manage Portfolio to enable sizing."
_CORRELATION_EMPTY_STATE = (
    "Need at least 2 positions with sufficient history to compute correlations."
)


class _WiredNavSeriesProvider:
    def __init__(
        self,
        *,
        nav_repo: NavSnapshotRepository,
        ohlc_provider: OhlcDataProvider,
        tx_repo: TransactionRepository,
    ) -> None:
        self._nav_repo = nav_repo
        self._ohlc_provider = ohlc_provider
        self._tx_repo = tx_repo

    def get_nav_series(self, start: date, end: date) -> list[DailyNavPoint]:
        return get_nav_series(
            start,
            end,
            nav_repo=self._nav_repo,
            ohlc_provider=self._ohlc_provider,
            tx_repo=self._tx_repo,
        )


def render() -> None:
    st.markdown("# 📊 Analytics")
    st.caption(
        "Five lenses on your portfolio: performance, correlation, technicals,"
        " position sizing, concentration."
    )

    tab_labels = [
        "Performance",
        "Correlation",
        "Technicals",
        "Position Sizer",
        "Concentration",
    ]
    perf_tab, corr_tab, tech_tab, sizing_tab, conc_tab = st.tabs(
        tab_labels,
        key="analytics_tabs",
        default="Performance",
    )

    with perf_tab:
        _render_performance_tab()
    with corr_tab:
        _render_correlation_tab()
    with tech_tab:
        st.info("Coming in TICKET-A3")
    with sizing_tab:
        _render_sizer_tab()
    with conc_tab:
        _render_concentration_tab()


def _render_performance_tab() -> None:
    ohlc_provider = get_ohlc_data_provider()
    nav_service: NavSeriesProvider = _WiredNavSeriesProvider(
        nav_repo=get_nav_snapshot_repo(),
        ohlc_provider=ohlc_provider,
        tx_repo=get_repository(),
    )

    period_col, benchmark_col = st.columns([0.7, 0.3])
    with period_col:
        period: PerformancePeriod = st.radio(
            "Period",
            options=list(PerformancePeriod),
            horizontal=True,
            key="performance_period",
            index=3,
            format_func=lambda p: p.value,
        )
    with benchmark_col:
        benchmark: BenchmarkLabel = st.selectbox(
            "Benchmark",
            options=_BENCHMARK_OPTIONS,
            index=0,
            key="performance_benchmark",
        )

    view = get_performance_view(
        period,
        benchmark,
        nav_service=nav_service,
        ohlc_provider=ohlc_provider,
    )
    _render_performance_view(view)


def _render_performance_view(view: PerformanceView) -> None:
    if view.benchmark_fetch_error is not None:
        st.warning(
            f"Benchmark data unavailable: {view.benchmark_fetch_error}. "
            "Showing portfolio only."
        )

    if not view.dates:
        st.info(_EMPTY_STATE)
        return

    if (
        view.requested_period_days > 0
        and view.available_days < view.requested_period_days
    ):
        st.caption(f"{view.period.value} (showing {view.available_days} days available)")

    _render_kpis(view)

    portfolio_series = _series_from_dates(
        "Portfolio",
        view.dates,
        view.portfolio_indexed,
    )
    benchmark_series = (
        _series_from_dates(view.benchmark_label, view.dates, view.benchmark_indexed)
        if view.benchmark_indexed is not None
        else None
    )
    render_line_chart(
        portfolio_series,
        secondary_series=benchmark_series,
        height=360,
        y_axis_mode="plain",
        y_axis_title="Index, start = 100",
        primary_name="Portfolio",
        secondary_name=view.benchmark_label,
        show_legend=True,
        fill_to_zero=False,
    )

    drawdowns = analytics.drawdown_series(view.portfolio_navs_raw)
    drawdown_series = _series_from_dates("Drawdown", view.dates, drawdowns)
    render_drawdown_chart(drawdown_series, height=180, chart_title="Drawdown")


def _render_kpis(view: PerformanceView) -> None:
    cols = st.columns(5)
    kpis = [
        (
            "Period Return",
            _format_optional_pct(view.period_return_pct, signed=True),
            gain_class(view.period_return_pct or Decimal("0")),
            "Return from the first to last available NAV in this period"
            if view.period_return_pct is not None
            else "Need at least two NAV snapshots",
        ),
        (
            "Alpha",
            _format_optional_pct(view.alpha_pct, signed=True),
            _alpha_class(view.alpha_pct),
            "Portfolio return minus benchmark return"
            if view.alpha_pct is not None
            else "Select a benchmark to see alpha",
        ),
        (
            "Max Drawdown",
            _format_optional_pct(view.max_drawdown_pct),
            "gain-neutral" if view.max_drawdown_pct == 0 else "gain-negative",
            "Worst peak-to-trough decline in the selected period",
        ),
        (
            "Annualised Vol",
            _format_optional_pct(view.volatility_annualised_pct),
            "gain-neutral",
            "Need at least three NAV snapshots"
            if view.volatility_annualised_pct is None
            else "Annualised volatility from daily returns",
        ),
        (
            "Sharpe",
            _format_optional_decimal(view.sharpe),
            _sharpe_class(view.sharpe),
            "Need at least three non-flat NAV snapshots"
            if view.sharpe is None
            else "Annualised return per unit of volatility",
        ),
    ]
    for col, (label, value, value_class, tooltip) in zip(cols, kpis):
        with col:
            render_metric_card(label, value, value_class=value_class, tooltip=tooltip)


def _series_from_dates(
    ticker: str,
    dates: list[date],
    values: list[Decimal],
) -> ChartSeries:
    points = tuple(
        ChartPoint(
            timestamp=datetime.combine(day, time(hour=16), tzinfo=UTC),
            value=value,
        )
        for day, value in zip(dates, values)
    )
    return ChartSeries(
        ticker=ticker,
        currency=Currency.EUR,
        period=_chart_period_for_dates(dates),
        points=points,
    )


def _chart_period_for_dates(dates: list[date]) -> ChartPeriod:
    if not dates:
        return ChartPeriod.FIVE_YEAR
    span = (dates[-1] - dates[0]).days
    if span <= 7:
        return ChartPeriod.ONE_MONTH
    if span <= 30:
        return ChartPeriod.ONE_MONTH
    if span <= 90:
        return ChartPeriod.THREE_MONTH
    if span <= 180:
        return ChartPeriod.SIX_MONTH
    if span <= 365:
        return ChartPeriod.ONE_YEAR
    return ChartPeriod.FIVE_YEAR


def _format_optional_pct(value: Decimal | None, *, signed: bool = False) -> str:
    return "—" if value is None else format_pct(value, signed=signed)


def _format_optional_decimal(value: Decimal | None) -> str:
    return "—" if value is None else str(value.quantize(Decimal("0.01")))


def _alpha_class(value: Decimal | None) -> str:
    if value is None:
        return "gain-neutral"
    if abs(value) < Decimal("0.5"):
        return "gain-amber"
    return gain_class(value)


def _sharpe_class(value: Decimal | None) -> str:
    if value is None or value < 0:
        return "gain-neutral"
    if value <= Decimal("1"):
        return "gain-amber"
    return "gain-positive"


def _render_correlation_tab() -> None:
    if "correlation_window" not in st.session_state:
        st.session_state["correlation_window"] = 30

    window_days = st.radio(
        "Window",
        [30, 60, 90],
        horizontal=True,
        key="correlation_window",
        format_func=lambda value: f"{value}D",
    )
    view = build_correlation_view(
        repo=get_repository(),
        price_feed=get_price_provider(),
        fx_feed=get_fx_provider(),
        ohlc=get_ohlc_data_provider(),
        as_of=date.today(),
        window_days=int(window_days),
    )
    _render_correlation_view(view)


def _render_correlation_view(
    view: CorrelationView,
    *,
    color_scheme: str | None = None,
) -> None:
    if view.skipped:
        skipped = "; ".join(
            f"{item.ticker} ({item.available_days} days available, "
            f"window requires {item.required_days})"
            for item in view.skipped
        )
        st.warning(f"Skipped: {skipped}")

    if len(view.included_tickers) < 2:
        st.info(_CORRELATION_EMPTY_STATE)
        return

    heatmap_col, table_col = st.columns([2, 1])
    with table_col:
        selected_color_scheme = _render_correlation_side_panel(view, color_scheme)
    with heatmap_col:
        render_correlation_heatmap(
            view.matrix,
            colorscale=_correlation_colorscale(selected_color_scheme),
            title=selected_color_scheme,
        )

    for cluster in view.clusters:
        members = ", ".join(cluster)
        st.warning(
            f"{len(cluster)} positions move together (avg corr > {CLUSTER_THRESHOLD}): "
            f"{members}. They may not be acting as independent diversifiers."
        )


def _render_correlation_side_panel(
    view: CorrelationView,
    color_scheme: str | None,
) -> str:
    selected_color_scheme = color_scheme or str(
        st.selectbox(
            "Color scheme",
            [name for name, _ in CORRELATION_COLORSCALE_OPTIONS],
            key="correlation_color_scheme",
        )
    )
    with st.expander("How to read this table", expanded=False):
        st.markdown(
            "Avg Correlation is the average correlation between this position and "
            "every other included position in the selected window. The diagonal "
            "self-correlation is excluded. Lower values suggest the position moves "
            "more independently; higher values suggest it moves more with the rest "
            "of the portfolio. The diversification label is based on fixed "
            "thresholds: <0.20 high, <0.40 moderate, <0.60 low, >=0.60 very low."
        )
    _render_correlation_table(view)
    return selected_color_scheme


def _render_correlation_table(view: CorrelationView) -> None:
    rows: list[dict[str, object]] = []
    for ticker, avg_corr in sorted(
        view.avg_correlation.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        bucket_label, _ = diversification_bucket(avg_corr)
        rows.append(
            {
                "Ticker": ticker,
                "Avg Correlation": float(avg_corr.quantize(Decimal("0.0001"))),
                "Diversification": bucket_label,
            }
        )
    table = pd.DataFrame(rows, columns=["Ticker", "Avg Correlation", "Diversification"])
    styled_table = table.style.map(
        _diversification_cell_style,
        subset=["Diversification"],
    )
    st.dataframe(
        styled_table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker"),
            "Avg Correlation": st.column_config.NumberColumn(
                "Avg Correlation",
                format="%.4f",
            ),
            "Diversification": st.column_config.TextColumn("Diversification"),
        },
    )


def _diversification_cell_style(value: object) -> str:
    styles = {
        "high": "background-color: rgba(20, 184, 166, 0.14); color: #99F6E4;",
        "moderate": "background-color: rgba(245, 158, 11, 0.14); color: #FCD34D;",
        "low": "background-color: rgba(249, 115, 22, 0.14); color: #FDBA74;",
        "very low": "background-color: rgba(239, 68, 68, 0.14); color: #FCA5A5;",
    }
    return styles.get(str(value), "")


def _correlation_colorscale(name: str | None) -> list[list[float | str]]:
    for option_name, colorscale in CORRELATION_COLORSCALE_OPTIONS:
        if option_name == name:
            return colorscale
    return CORRELATION_COLORSCALE_OPTIONS[0][1]


@st.cache_data(ttl=60, show_spinner=False)
def _cached_concentration_live_positions(tx_sig: str) -> dict[str, LivePosition]:
    transactions = get_repository().load_all()
    return compute_live_positions(transactions, get_price_provider(), get_fx_provider())


@st.cache_data(ttl=60, show_spinner=False)
def _cached_concentration_summary(tx_sig: str, as_of_iso: str) -> PortfolioSummary:
    live_positions = _cached_concentration_live_positions(tx_sig)
    return compute_portfolio_summary(live_positions, datetime.fromisoformat(as_of_iso))


def _render_concentration_tab() -> None:
    transactions = get_repository().load_all()
    sig = transactions_signature(transactions)
    now_iso = datetime.now().isoformat()
    live_positions = _cached_concentration_live_positions(sig)
    summary = _cached_concentration_summary(sig, now_iso)
    view = compute_concentration_view(list(live_positions.values()), summary)
    _render_concentration_view(view)


def _render_sizer_tab() -> None:
    transactions = get_repository().load_all()
    sig = transactions_signature(transactions)
    now_iso = datetime.now().isoformat()
    live_positions = _cached_concentration_live_positions(sig)
    if not live_positions:
        st.info(_SIZER_EMPTY_STATE)
        return

    summary = _cached_concentration_summary(sig, now_iso)
    sorted_tickers = sorted(live_positions)
    default_ticker = st.session_state.get("sizer_ticker", sorted_tickers[0])
    selected_index = (
        sorted_tickers.index(default_ticker) if default_ticker in sorted_tickers else 0
    )

    input_col, result_col = st.columns([1, 1])
    with input_col:
        selected_ticker = st.selectbox(
            "Ticker",
            sorted_tickers,
            index=selected_index,
            key="sizer_ticker",
        )
        direction = st.radio(
            "Direction",
            ["buy", "sell"],
            horizontal=True,
            key="sizer_direction",
            format_func=lambda value: str(value).title(),
        )
        risk_pct = Decimal(
            str(
                st.number_input(
                    "Risk %",
                    min_value=0.1,
                    max_value=5.0,
                    step=0.1,
                    value=float(DEFAULT_RISK_PCT),
                )
            )
        )
        stop_pct = Decimal(
            str(
                st.number_input(
                    "Stop Loss %",
                    min_value=1.0,
                    max_value=30.0,
                    step=0.5,
                    value=float(DEFAULT_STOP_PCT),
                )
            )
        )
        target_weight_pct = Decimal(
            str(
                st.number_input(
                    "Target Weight %",
                    min_value=1.0,
                    max_value=40.0,
                    step=0.5,
                    value=float(DEFAULT_TARGET_WEIGHT_PCT),
                )
            )
        )

        view = compute_sizer_view(
            positions=list(live_positions.values()),
            summary=summary,
            selected_ticker=str(selected_ticker),
            direction=cast(Literal["buy", "sell"], direction),
            risk_pct=risk_pct,
            stop_pct=stop_pct,
            target_weight_pct=target_weight_pct,
        )
        _render_current_position_card(view)

    with result_col:
        _render_sizer_view(view)


def _render_sizer_view(view: SizerView) -> None:
    if view.degraded_reason is not None:
        if view.risk_based is None:
            st.error(view.degraded_reason)
            return
        st.warning(view.degraded_reason)

    if (
        view.risk_based is None
        or view.weight_based is None
        or view.post_trade is None
    ):
        return

    render_html(_build_risk_result_card_html(view))
    render_html(_build_weight_result_card_html(view))
    render_html(_build_post_trade_preview_html(view))


def _render_current_position_card(view: SizerView) -> None:
    current = view.current
    status = current.staleness or "live"
    render_html(
        '<div class="metric-card">'
        '<div class="metric-label">Current Position</div>'
        f'<div class="metric-value">{html.escape(current.ticker)}</div>'
        '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; '
        'margin-top: 12px; font-size: 13px;">'
        f"<div>Weight<br><strong>{format_pct(current.weight_pct)}</strong></div>"
        f"<div>Value<br><strong>{format_eur(current.market_value_eur)}</strong></div>"
        f"<div>Last<br><strong>{html.escape(str(current.last_price_native))}</strong></div>"
        f"<div>EUR<br><strong>{format_eur(current.last_price_eur)}</strong></div>"
        f"<div>Lots<br><strong>{current.open_lot_count}</strong></div>"
        f"<div>Status<br><strong>{html.escape(status)}</strong></div>"
        "</div></div>"
    )


def _build_risk_result_card_html(view: SizerView) -> str:
    result = view.risk_based
    assert result is not None
    return (
        '<div class="metric-card" style="border-left: 3px solid var(--green);">'
        '<div class="metric-label">Method 1 — Risk-Based</div>'
        f'<div class="metric-value">{format_shares(result.shares)}</div>'
        f'<div class="metric-delta">Trade value {format_eur(result.trade_value_eur)}</div>'
        '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; '
        'margin-top: 12px; font-size: 13px;">'
        f"<div>Risk<br><strong>{format_eur(result.risk_eur)}</strong></div>"
        f"<div>Risk %<br><strong>{format_pct(result.risk_pct_input)}</strong></div>"
        f"<div>Stop<br><strong>{html.escape(str(result.stop_price_native))}</strong></div>"
        "</div></div>"
    )


def _build_weight_result_card_html(view: SizerView) -> str:
    result = view.weight_based
    assert result is not None
    return (
        '<div class="metric-card" style="border-left: 3px solid var(--blue);">'
        '<div class="metric-label">Method 2 — Weight-Based</div>'
        f'<div class="metric-value">{format_shares(result.shares)}</div>'
        f'<div class="metric-delta">Delta {format_eur(result.delta_eur, signed=True)}</div>'
        '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; '
        'margin-top: 12px; font-size: 13px;">'
        f"<div>Current<br><strong>{format_pct(result.current_weight_pct)}</strong></div>"
        f"<div>Target<br><strong>{format_pct(result.target_weight_pct)}</strong></div>"
        "</div></div>"
    )


def _build_post_trade_preview_html(view: SizerView) -> str:
    preview = view.post_trade
    assert preview is not None
    marker_pct = min(
        Decimal("100"),
        SIZER_MAX_POSITION_WEIGHT_PCT / SIZER_BAR_SCALE_MAX_PCT * Decimal("100"),
    )
    bar = render_weight_bar(
        preview.new_weight_pct,
        scale_max=SIZER_BAR_SCALE_MAX_PCT,
        danger_threshold=SIZER_MAX_POSITION_WEIGHT_PCT,
        label=format_pct(preview.new_weight_pct),
    )
    return (
        '<div class="metric-card">'
        '<div class="metric-label">New Weight After Method 1</div>'
        f'<div class="metric-value">{format_pct(preview.new_weight_pct)}</div>'
        f'<div class="metric-delta">Current {format_pct(preview.current_weight_pct)}</div>'
        '<div style="position: relative; margin-top: 12px;">'
        f"{bar}"
        f'<div title="35% cap" style="position: absolute; left: {marker_pct}%; '
        'top: 18px; width: 2px; height: 12px; background: var(--red);"></div>'
        "</div></div>"
    )


def _render_concentration_view(view: ConcentrationView) -> None:
    if not view.rows:
        st.info(_CONCENTRATION_EMPTY_STATE)
        return

    stale_count = sum(1 for row in view.rows if row.staleness_reason is not None)
    if stale_count:
        st.warning(
            f"{stale_count} positions have stale or missing data — affecting weights below"
        )

    _render_concentration_kpis(view)

    chart_col, donut_col = st.columns([1, 1])
    with chart_col:
        render_weight_bar_chart(
            view.weights_by_ticker,
            max_position_pct=MAX_POSITION_WEIGHT_PCT,
        )
    with donut_col:
        render_currency_donut(view.currency_split)

    render_html(_build_concentration_table_html(view))


def _render_concentration_kpis(view: ConcentrationView) -> None:
    cols = st.columns(3)
    kpis = [
        (
            "Top-1",
            format_pct(view.top_1_pct),
            _threshold_class(
                view.top_1_pct,
                green_lt=TOP_1_GREEN_LT_PCT,
                red_gte=TOP_1_RED_GTE_PCT,
            ),
            "Largest single position by current market value",
        ),
        (
            "Top-3",
            format_pct(view.top_3_pct),
            _threshold_class(
                view.top_3_pct,
                green_lt=TOP_3_GREEN_LT_PCT,
                red_gte=TOP_3_RED_GTE_PCT,
            ),
            "Combined weight of the three largest positions",
        ),
        (
            "Herfindahl",
            str(view.herfindahl.quantize(Decimal("1"))),
            _threshold_class(
                view.herfindahl,
                green_lt=HHI_GREEN_LT,
                red_gte=HHI_RED_GTE,
            ),
            "Concentration score on a 0-10000 scale",
        ),
    ]
    for col, (label, value, value_class, tooltip) in zip(cols, kpis):
        with col:
            render_metric_card(label, value, value_class=value_class, tooltip=tooltip)


def _threshold_class(value: Decimal, *, green_lt: Decimal, red_gte: Decimal) -> str:
    if value < green_lt:
        return "gain-positive"
    if value >= red_gte:
        return "gain-negative"
    return "gain-amber"


def _build_concentration_table_html(view: ConcentrationView) -> str:
    rows: list[str] = []
    for row in view.rows:
        value = format_eur(row.value_eur, signed=False).replace("€", "")
        weight_bar = render_weight_bar(row.weight_pct, scale_max=BAR_SCALE_MAX_PCT)
        stale_label = (
            f'<span style="color: var(--text3);">{row.staleness_reason}</span>'
            if row.staleness_reason is not None
            else '<span class="gain-positive">live</span>'
        )
        rows.append(
            "<tr>"
            f"<td><strong>{row.ticker}</strong></td>"
            f'<td style="color: var(--text2);">{row.name}</td>'
            f'<td style="color: var(--text3);">{row.currency.value}</td>'
            f'<td class="font-mono text-right">{value}</td>'
            f'<td class="font-mono">{weight_bar}</td>'
            f'<td>{stale_label}</td>'
            "</tr>"
        )

    table_style = (
        "width: 100%; border-collapse: collapse; text-align: left; "
        "font-size: 13px;"
    )
    header_style = (
        "border-bottom: 1px solid var(--border); color: var(--text3); "
        "text-transform: uppercase; font-size: 10px; letter-spacing: 0.05em;"
    )
    return (
        '<div class="metric-card" style="padding: 0; overflow-x: auto;">'
        f'<table class="positions-table" style="{table_style}">'
        '<thead>'
        f'<tr style="{header_style}">'
        '<th style="padding: 8px 4px;">Ticker</th>'
        '<th style="padding: 8px 4px;">Name</th>'
        '<th style="padding: 8px 4px;">CCY</th>'
        '<th style="padding: 8px 4px; text-align: right;">Value (€)</th>'
        '<th style="padding: 8px 4px;">Weight</th>'
        '<th style="padding: 8px 4px;">Status</th>'
        "</tr>"
        "</thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )
