"""Performance-tab orchestration for the Analytics page.

Fetches portfolio NAV and benchmark OHLC series, aligns them, indexes both to
100, and computes KPI facts. No Streamlit imports and no concrete adapters.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.domain import analytics
from app.domain.market_data import ChartPeriod, OhlcSeries, OhlcUnavailableError
from app.domain.nav import DailyNavPoint
from app.ports.market_data import OhlcDataProvider

BenchmarkLabel = Literal["SPY", "EUNL", "None"]

_BENCHMARK_SYMBOLS: dict[str, str] = {
    "SPY": "SPY",
    "EUNL": "EUNL.DE",
}


class PerformancePeriod(StrEnum):
    ONE_WEEK = "1W"
    ONE_MONTH = "1M"
    THREE_MONTH = "3M"
    SIX_MONTH = "6M"
    ONE_YEAR = "1Y"
    MAX = "MAX"


class NavSeriesProvider(Protocol):
    def get_nav_series(self, start: date, end: date) -> list[DailyNavPoint]:
        """Return NAV points in the closed interval [start, end]."""
        ...


class PerformanceView(BaseModel):
    model_config = ConfigDict(frozen=True)

    period: PerformancePeriod
    benchmark_label: BenchmarkLabel

    dates: list[date]
    portfolio_indexed: list[Decimal]
    benchmark_indexed: list[Decimal] | None
    portfolio_navs_raw: list[Decimal]

    period_return_pct: Decimal | None
    alpha_pct: Decimal | None
    max_drawdown_pct: Decimal
    volatility_annualised_pct: Decimal | None
    sharpe: Decimal | None

    requested_period_days: int
    available_days: int
    benchmark_fetch_error: str | None = None


def get_performance_view(
    period: PerformancePeriod,
    benchmark: BenchmarkLabel,
    *,
    nav_service: NavSeriesProvider,
    ohlc_provider: OhlcDataProvider,
    today: date | None = None,
) -> PerformanceView:
    """Build the complete render model for the Analytics Performance tab."""
    resolved_today = today or date.today()
    requested_days = _requested_days(period)
    start = (
        date.min
        if period is PerformancePeriod.MAX
        else resolved_today - timedelta(days=requested_days)
    )
    nav_points = sorted(
        nav_service.get_nav_series(start, resolved_today),
        key=lambda point: point.snapshot_date,
    )

    if len(nav_points) < 2:
        return _empty_view(period, benchmark, requested_days)

    nav_dates = [point.snapshot_date for point in nav_points]
    nav_values = [point.nav_eur.amount for point in nav_points]
    available_days = (nav_dates[-1] - nav_dates[0]).days

    benchmark_fetch_error: str | None = None
    benchmark_values: list[Decimal] | None = None
    aligned_dates = nav_dates
    aligned_navs = nav_values

    if benchmark != "None":
        try:
            symbol = _BENCHMARK_SYMBOLS[benchmark]
            benchmark_series = ohlc_provider.get_ohlc_history(symbol, _chart_period(period))
            benchmark_by_date = _benchmark_closes_by_date(benchmark_series)
            aligned = _align_on_dates(list(zip(nav_dates, nav_values)), benchmark_by_date)
            aligned_dates = [row[0] for row in aligned]
            aligned_navs = [row[1] for row in aligned]
            benchmark_values = [row[2] for row in aligned]
        except OhlcUnavailableError as exc:
            benchmark_fetch_error = exc.reason

    if len(aligned_dates) < 2:
        return _empty_view(
            period,
            benchmark,
            requested_days,
            benchmark_fetch_error=benchmark_fetch_error,
        )

    portfolio_indexed = _index_to_100(aligned_navs)
    benchmark_indexed = _index_to_100(benchmark_values) if benchmark_values is not None else None
    returns = analytics.daily_returns(aligned_navs)
    period_return = (aligned_navs[-1] / aligned_navs[0] - Decimal("1")) * Decimal("100")
    benchmark_return = (
        (benchmark_values[-1] / benchmark_values[0] - Decimal("1")) * Decimal("100")
        if benchmark_values is not None
        else None
    )
    volatility = _maybe_volatility_pct(returns)
    sharpe = _maybe_sharpe(returns)

    return PerformanceView(
        period=period,
        benchmark_label=benchmark,
        dates=aligned_dates,
        portfolio_indexed=portfolio_indexed,
        benchmark_indexed=benchmark_indexed,
        portfolio_navs_raw=aligned_navs,
        period_return_pct=period_return,
        alpha_pct=period_return - benchmark_return if benchmark_return is not None else None,
        max_drawdown_pct=analytics.max_drawdown(aligned_navs) * Decimal("100"),
        volatility_annualised_pct=volatility,
        sharpe=sharpe,
        requested_period_days=requested_days,
        available_days=available_days,
        benchmark_fetch_error=benchmark_fetch_error,
    )


def _align_on_dates(
    nav_series: list[tuple[date, Decimal]],
    benchmark_series: dict[date, Decimal],
    max_forward_fill_days: int = 3,
) -> list[tuple[date, Decimal, Decimal]]:
    """Align benchmark closes to portfolio NAV dates.

    The portfolio NAV date set is authoritative. Exact benchmark closes are used
    when present. For short benchmark-market gaps, the previous benchmark close
    is carried forward only when the gap between surrounding benchmark closes is
    at most ``max_forward_fill_days``. Longer gaps are dropped from both series.
    """
    benchmark_dates = sorted(benchmark_series)
    aligned: list[tuple[date, Decimal, Decimal]] = []
    for nav_date, nav_value in nav_series:
        if nav_date in benchmark_series:
            aligned.append((nav_date, nav_value, benchmark_series[nav_date]))
            continue

        previous_dates = [d for d in benchmark_dates if d < nav_date]
        next_dates = [d for d in benchmark_dates if d > nav_date]
        previous_date = previous_dates[-1] if previous_dates else None
        next_date = next_dates[0] if next_dates else None

        if previous_date is None:
            if next_date is not None and (next_date - nav_date).days <= max_forward_fill_days:
                aligned.append((nav_date, nav_value, benchmark_series[next_date]))
            continue

        if next_date is not None:
            if (next_date - previous_date).days <= max_forward_fill_days:
                aligned.append((nav_date, nav_value, benchmark_series[previous_date]))
            continue

        if (nav_date - previous_date).days <= max_forward_fill_days:
            aligned.append((nav_date, nav_value, benchmark_series[previous_date]))

    return aligned


def _benchmark_closes_by_date(series: OhlcSeries) -> dict[date, Decimal]:
    return {bar.timestamp.date(): bar.close for bar in series.bars}


def _requested_days(period: PerformancePeriod) -> int:
    return {
        PerformancePeriod.ONE_WEEK: 7,
        PerformancePeriod.ONE_MONTH: 30,
        PerformancePeriod.THREE_MONTH: 90,
        PerformancePeriod.SIX_MONTH: 180,
        PerformancePeriod.ONE_YEAR: 365,
        PerformancePeriod.MAX: 0,
    }[period]


def _chart_period(period: PerformancePeriod) -> ChartPeriod:
    return {
        PerformancePeriod.ONE_WEEK: ChartPeriod.ONE_MONTH,
        PerformancePeriod.ONE_MONTH: ChartPeriod.ONE_MONTH,
        PerformancePeriod.THREE_MONTH: ChartPeriod.THREE_MONTH,
        PerformancePeriod.SIX_MONTH: ChartPeriod.SIX_MONTH,
        PerformancePeriod.ONE_YEAR: ChartPeriod.ONE_YEAR,
        PerformancePeriod.MAX: ChartPeriod.FIVE_YEAR,
    }[period]


def _index_to_100(values: list[Decimal]) -> list[Decimal]:
    first = values[0]
    return [(value / first) * Decimal("100") for value in values]


def _maybe_volatility_pct(returns: list[Decimal]) -> Decimal | None:
    try:
        return analytics.volatility_annualised(returns) * Decimal("100")
    except ValueError:
        return None


def _maybe_sharpe(returns: list[Decimal]) -> Decimal | None:
    try:
        return analytics.sharpe(returns)
    except ValueError:
        return None


def _empty_view(
    period: PerformancePeriod,
    benchmark: BenchmarkLabel,
    requested_days: int,
    *,
    benchmark_fetch_error: str | None = None,
) -> PerformanceView:
    return PerformanceView(
        period=period,
        benchmark_label=benchmark,
        dates=[],
        portfolio_indexed=[],
        benchmark_indexed=None,
        portfolio_navs_raw=[],
        period_return_pct=None,
        alpha_pct=None,
        max_drawdown_pct=Decimal("0"),
        volatility_annualised_pct=None,
        sharpe=None,
        requested_period_days=requested_days,
        available_days=0,
        benchmark_fetch_error=benchmark_fetch_error,
    )
