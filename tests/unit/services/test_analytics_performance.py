from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries, OhlcUnavailableError
from app.domain.money import Currency, Money
from app.domain.nav import DailyNavPoint
from app.services.analytics_performance import (
    PerformancePeriod,
    _align_on_dates,
    get_performance_view,
)


def _nav_point(day: date, amount: str) -> DailyNavPoint:
    return DailyNavPoint(
        snapshot_date=day,
        nav_eur=Money(amount=Decimal(amount), currency=Currency.EUR),
        cost_basis_eur=Money(amount=Decimal("100"), currency=Currency.EUR),
        n_positions=1,
        is_reconstructed=True,
    )


def _bar(day: date, close: str) -> OhlcBar:
    value = Decimal(close)
    return OhlcBar(
        timestamp=datetime(day.year, day.month, day.day, 16, tzinfo=UTC),
        open=value,
        high=value,
        low=value,
        close=value,
        volume=1000,
    )


def _series(ticker: str, dates: list[date], closes: list[str]) -> OhlcSeries:
    return OhlcSeries(
        ticker=ticker,
        currency=Currency.USD,
        period=ChartPeriod.SIX_MONTH,
        bars=tuple(_bar(day, close) for day, close in zip(dates, closes)),
        fetched_at=datetime(2025, 1, 31, tzinfo=UTC),
    )


class FakeNavSeriesProvider:
    def __init__(self, points: list[DailyNavPoint]) -> None:
        self.points = points
        self.calls: list[tuple[date, date]] = []

    def get_nav_series(self, start: date, end: date) -> list[DailyNavPoint]:
        self.calls.append((start, end))
        return [point for point in self.points if start <= point.snapshot_date <= end]


class FakeOhlcProvider:
    def __init__(
        self,
        series_by_ticker: dict[str, OhlcSeries],
        raise_for: set[str] | None = None,
    ) -> None:
        self.series_by_ticker = series_by_ticker
        self.raise_for = raise_for or set()
        self.calls: list[tuple[str, ChartPeriod]] = []

    def get_ohlc_history(self, ticker: str, period: ChartPeriod) -> OhlcSeries:
        self.calls.append((ticker, period))
        if ticker in self.raise_for:
            raise OhlcUnavailableError(f"rate limit for {ticker}")
        return self.series_by_ticker[ticker]

    def clear_cache(self) -> None:
        pass


def _dates(start: date, n: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def test_happy_path_computes_indexed_series_and_kpis() -> None:
    days = _dates(date(2025, 1, 1), 30)
    navs = [_nav_point(day, str(100 + i)) for i, day in enumerate(days)]
    spy = _series("SPY", days, [str(200 + i) for i in range(30)])

    view = get_performance_view(
        PerformancePeriod.SIX_MONTH,
        "SPY",
        nav_service=FakeNavSeriesProvider(navs),
        ohlc_provider=FakeOhlcProvider({"SPY": spy}),
        today=date(2025, 1, 30),
    )

    assert view.dates == days
    assert view.portfolio_indexed[0] == Decimal("100")
    assert view.benchmark_indexed is not None
    assert view.benchmark_indexed[0] == Decimal("100")
    assert view.period_return_pct == Decimal("29.00")
    assert view.alpha_pct == Decimal("14.500")
    assert view.max_drawdown_pct <= Decimal("0")


def test_benchmark_none_populates_portfolio_only() -> None:
    days = _dates(date(2025, 1, 1), 4)
    navs = [_nav_point(day, str(100 + i)) for i, day in enumerate(days)]

    view = get_performance_view(
        PerformancePeriod.ONE_MONTH,
        "None",
        nav_service=FakeNavSeriesProvider(navs),
        ohlc_provider=FakeOhlcProvider({}),
        today=date(2025, 1, 4),
    )

    assert view.benchmark_indexed is None
    assert view.alpha_pct is None
    assert view.period_return_pct is not None
    assert view.sharpe is not None


def test_benchmark_fetch_failure_returns_portfolio_view_with_error() -> None:
    days = _dates(date(2025, 1, 1), 4)
    navs = [_nav_point(day, str(100 + i)) for i, day in enumerate(days)]

    view = get_performance_view(
        PerformancePeriod.ONE_MONTH,
        "SPY",
        nav_service=FakeNavSeriesProvider(navs),
        ohlc_provider=FakeOhlcProvider({}, raise_for={"SPY"}),
        today=date(2025, 1, 4),
    )

    assert view.benchmark_fetch_error == "rate limit for SPY"
    assert view.benchmark_indexed is None
    assert view.alpha_pct is None
    assert view.portfolio_indexed[0] == Decimal("100")


def test_empty_nav_returns_empty_view_contract() -> None:
    view = get_performance_view(
        PerformancePeriod.ONE_MONTH,
        "SPY",
        nav_service=FakeNavSeriesProvider([]),
        ohlc_provider=FakeOhlcProvider({}),
        today=date(2025, 1, 4),
    )

    assert view.dates == []
    assert view.period_return_pct is None
    assert view.alpha_pct is None
    assert view.max_drawdown_pct == Decimal("0")
    assert view.volatility_annualised_pct is None
    assert view.sharpe is None


def test_single_nav_point_returns_empty_view_contract() -> None:
    view = get_performance_view(
        PerformancePeriod.ONE_MONTH,
        "None",
        nav_service=FakeNavSeriesProvider([_nav_point(date(2025, 1, 1), "100")]),
        ohlc_provider=FakeOhlcProvider({}),
        today=date(2025, 1, 1),
    )

    assert view.dates == []
    assert view.period_return_pct is None
    assert view.max_drawdown_pct == Decimal("0")


def test_sharpe_can_be_negative() -> None:
    days = _dates(date(2025, 1, 1), 4)
    navs = [
        _nav_point(days[0], "100"),
        _nav_point(days[1], "99"),
        _nav_point(days[2], "97"),
        _nav_point(days[3], "96"),
    ]

    view = get_performance_view(
        PerformancePeriod.ONE_MONTH,
        "None",
        nav_service=FakeNavSeriesProvider(navs),
        ohlc_provider=FakeOhlcProvider({}),
        today=date(2025, 1, 4),
    )

    assert view.sharpe is not None
    assert view.sharpe < Decimal("0")


def test_two_nav_points_make_volatility_uncomputable() -> None:
    days = _dates(date(2025, 1, 1), 2)
    navs = [_nav_point(days[0], "100"), _nav_point(days[1], "101")]

    view = get_performance_view(
        PerformancePeriod.ONE_MONTH,
        "None",
        nav_service=FakeNavSeriesProvider(navs),
        ohlc_provider=FakeOhlcProvider({}),
        today=date(2025, 1, 2),
    )

    assert view.volatility_annualised_pct is None
    assert view.sharpe is None


def test_date_alignment_carries_previous_close_across_short_gap() -> None:
    mon = date(2025, 1, 6)
    tue = date(2025, 1, 7)
    wed = date(2025, 1, 8)

    aligned = _align_on_dates(
        [(mon, Decimal("100")), (tue, Decimal("101")), (wed, Decimal("102"))],
        {mon: Decimal("200"), wed: Decimal("204")},
    )

    assert aligned == [
        (mon, Decimal("100"), Decimal("200")),
        (tue, Decimal("101"), Decimal("200")),
        (wed, Decimal("102"), Decimal("204")),
    ]


def test_date_alignment_drops_long_benchmark_gap() -> None:
    mon = date(2025, 1, 6)
    tue = date(2025, 1, 7)
    wed = date(2025, 1, 8)
    thu = date(2025, 1, 9)
    fri = date(2025, 1, 10)

    aligned = _align_on_dates(
        [
            (mon, Decimal("100")),
            (tue, Decimal("101")),
            (wed, Decimal("102")),
            (thu, Decimal("103")),
            (fri, Decimal("104")),
        ],
        {mon: Decimal("200"), fri: Decimal("208")},
    )

    assert aligned == [
        (mon, Decimal("100"), Decimal("200")),
        (fri, Decimal("104"), Decimal("208")),
    ]


def test_indexed_to_100_invariant() -> None:
    days = _dates(date(2025, 1, 1), 3)
    navs = [_nav_point(days[0], "50"), _nav_point(days[1], "55"), _nav_point(days[2], "60")]

    view = get_performance_view(
        PerformancePeriod.ONE_MONTH,
        "None",
        nav_service=FakeNavSeriesProvider(navs),
        ohlc_provider=FakeOhlcProvider({}),
        today=date(2025, 1, 3),
    )

    assert view.portfolio_indexed[0] == Decimal("100")


def test_max_drawdown_is_never_positive() -> None:
    days = _dates(date(2025, 1, 1), 5)
    navs = [
        _nav_point(days[0], "100"),
        _nav_point(days[1], "110"),
        _nav_point(days[2], "90"),
        _nav_point(days[3], "95"),
        _nav_point(days[4], "120"),
    ]

    view = get_performance_view(
        PerformancePeriod.ONE_MONTH,
        "None",
        nav_service=FakeNavSeriesProvider(navs),
        ohlc_provider=FakeOhlcProvider({}),
        today=date(2025, 1, 5),
    )

    assert view.max_drawdown_pct <= Decimal("0")
