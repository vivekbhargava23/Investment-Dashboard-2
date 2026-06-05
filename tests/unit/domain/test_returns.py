from datetime import UTC, date, datetime
from decimal import Decimal

from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries
from app.domain.money import Currency
from app.domain.returns import ALL_WINDOWS, ReturnWindow, period_return


def _bar(day: str, close: str) -> OhlcBar:
    """A daily bar whose OHLC collapses to `close` (integrity-valid, positive)."""
    c = Decimal(close)
    return OhlcBar(
        timestamp=datetime.fromisoformat(day).replace(tzinfo=UTC),
        open=c,
        high=c,
        low=c,
        close=c,
        volume=None,
    )


def _series(*bars: OhlcBar, period: ChartPeriod = ChartPeriod.ONE_YEAR) -> OhlcSeries:
    return OhlcSeries(
        ticker="NVDA",
        currency=Currency.USD,
        period=period,
        bars=tuple(bars),
        fetched_at=datetime(2024, 7, 1, tzinfo=UTC),
    )


# --- ReturnWindow enum ---

def test_all_windows_covers_the_four_named_windows() -> None:
    assert ALL_WINDOWS == (
        ReturnWindow.D1,
        ReturnWindow.D7,
        ReturnWindow.D30,
        ReturnWindow.YTD,
    )


# --- Test case 1: known close path → exact percentages ---

def test_known_close_path_yields_exact_window_percentages() -> None:
    # Closes 30 calendar days back, 7 days back, the day before, and on as_of.
    series = _series(
        _bar("2024-05-01", "100"),  # as_of - 30d
        _bar("2024-05-24", "120"),  # as_of - 7d
        _bar("2024-05-30", "125"),  # as_of - 1d (prev close)
        _bar("2024-05-31", "130"),  # as_of (end close)
    )
    as_of = date(2024, 5, 31)

    # D1: 125 → 130 = +4%
    assert period_return(series, ReturnWindow.D1, as_of=as_of) == Decimal("4")
    # D7: 120 → 130 = +8.333...%
    d7 = period_return(series, ReturnWindow.D7, as_of=as_of)
    assert d7 is not None and d7 == (Decimal("10") / Decimal("120") * Decimal("100"))
    # D30: 100 → 130 = +30%
    assert period_return(series, ReturnWindow.D30, as_of=as_of) == Decimal("30")


def test_d7_uses_most_recent_bar_on_or_before_cutoff() -> None:
    # No bar exactly on as_of - 7d; the most recent bar on/before it is used.
    series = _series(
        _bar("2024-05-20", "100"),  # 4 days before cutoff (as_of-7d = 05-24)
        _bar("2024-05-31", "110"),
    )
    # cutoff = 05-24; most recent bar on/before = 05-20 (close 100). 100→110 = +10%
    assert period_return(series, ReturnWindow.D7, as_of=date(2024, 5, 31)) == Decimal("10")


# --- Test case 2: series shorter than the window → None (not a wrong number) ---

def test_window_not_covered_returns_none() -> None:
    # Only 5 days of history: D30 cannot be covered.
    series = _series(
        _bar("2024-05-27", "100"),
        _bar("2024-05-31", "110"),
    )
    assert period_return(series, ReturnWindow.D30, as_of=date(2024, 5, 31)) is None


def test_single_bar_on_or_before_as_of_returns_none() -> None:
    series = _series(
        _bar("2024-05-31", "100"),
        _bar("2024-06-15", "200"),  # after as_of, ignored
    )
    for window in ALL_WINDOWS:
        assert period_return(series, window, as_of=date(2024, 5, 31)) is None


# --- Test case 3: YTD straddling Jan 1 measures from prior-year-end close ---

def test_ytd_measures_from_prior_year_end_close() -> None:
    series = _series(
        _bar("2023-12-29", "200"),  # prior-year end
        _bar("2024-01-02", "210"),
        _bar("2024-03-15", "250"),
    )
    # 200 → 250 = +25%
    assert period_return(series, ReturnWindow.YTD, as_of=date(2024, 3, 15)) == Decimal("25")


def test_ytd_falls_back_to_first_current_year_bar_when_no_prior_year() -> None:
    series = _series(
        _bar("2024-01-02", "100"),  # first bar of current year (no prior-year data)
        _bar("2024-03-15", "150"),
    )
    # 100 → 150 = +50%
    assert period_return(series, ReturnWindow.YTD, as_of=date(2024, 3, 15)) == Decimal("50")


def test_negative_return_is_signed() -> None:
    series = _series(
        _bar("2024-05-30", "200"),
        _bar("2024-05-31", "150"),
    )
    # 200 → 150 = -25%
    assert period_return(series, ReturnWindow.D1, as_of=date(2024, 5, 31)) == Decimal("-25")
