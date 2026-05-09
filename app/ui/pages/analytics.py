"""Analytics page.

The Performance tab calls ``analytics.drawdown_series`` directly to derive the
area-chart values from ``PerformanceView.portfolio_navs_raw``. That is the
explicit A1 exception to the usual page -> service -> domain flow: max drawdown
is a service fact, while the full drawdown series only feeds one visual.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal

import streamlit as st

from app.domain import analytics
from app.domain.market_data import ChartPeriod
from app.domain.money import Currency
from app.domain.nav import DailyNavPoint
from app.ports.market_data import OhlcDataProvider
from app.ports.nav_repository import NavSnapshotRepository
from app.ports.repository import TransactionRepository
from app.services.analytics_performance import (
    BenchmarkLabel,
    NavSeriesProvider,
    PerformancePeriod,
    PerformanceView,
    get_performance_view,
)
from app.services.nav import get_nav_series
from app.ui.components.charts import (
    ChartPoint,
    ChartSeries,
    render_drawdown_chart,
    render_line_chart,
)
from app.ui.components.metric_card import render_metric_card
from app.ui.format import format_pct, gain_class
from app.ui.wiring import get_nav_snapshot_repo, get_ohlc_data_provider, get_repository

_BENCHMARK_OPTIONS: list[BenchmarkLabel] = ["SPY", "EUNL", "None"]
_EMPTY_STATE = "Performance data is being collected. Check back after the next NAV snapshot."


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

    perf_tab, corr_tab, tech_tab, sizing_tab, conc_tab = st.tabs(
        ["Performance", "Correlation", "Technicals", "Position Sizer", "Concentration"]
    )

    with perf_tab:
        _render_performance_tab()
    with corr_tab:
        st.info("Coming in TICKET-A2")
    with tech_tab:
        st.info("Coming in TICKET-A3")
    with sizing_tab:
        st.info("Coming in TICKET-A4")
    with conc_tab:
        st.info("Coming in TICKET-A5")


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
        show_legend=benchmark_series is not None,
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
