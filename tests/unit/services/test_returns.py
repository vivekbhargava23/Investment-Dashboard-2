from datetime import UTC, date, datetime
from decimal import Decimal

from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries
from app.domain.money import Currency
from app.domain.returns import ALL_WINDOWS, ReturnWindow
from app.services.returns import (
    compute_return_stats_by_period,
    compute_returns_by_period,
)
from tests.fakes.ohlc import FakeOhlcDataProvider

# The returns service fetches a 2Y daily window so the 1Y window is covered.
_FETCH_PERIOD = ChartPeriod.TWO_YEAR


def _bar(day: str, close: str) -> OhlcBar:
    c = Decimal(close)
    return OhlcBar(
        timestamp=datetime.fromisoformat(day).replace(tzinfo=UTC),
        open=c, high=c, low=c, close=c, volume=None,
    )


def _series(ticker: str, *bars: OhlcBar) -> OhlcSeries:
    return OhlcSeries(
        ticker=ticker,
        currency=Currency.USD,
        period=ChartPeriod.ONE_YEAR,
        bars=tuple(bars),
        fetched_at=datetime(2024, 7, 1, tzinfo=UTC),
    )


_AAA = _series(
    "AAA",
    _bar("2024-05-01", "100"),  # as_of - 30d
    _bar("2024-05-24", "120"),  # as_of - 7d
    _bar("2024-05-30", "125"),  # prev close
    _bar("2024-05-31", "130"),  # end close
)
_AS_OF = date(2024, 5, 31)


def _provider(**series: OhlcSeries) -> FakeOhlcDataProvider:
    series_map = {(ticker, _FETCH_PERIOD): s for ticker, s in series.items()}
    return FakeOhlcDataProvider(series_map=series_map)


def test_computes_every_window_for_a_served_ticker() -> None:
    fake = _provider(AAA=_AAA)
    result = compute_returns_by_period(["AAA"], as_of=_AS_OF, provider=fake)

    assert set(result["AAA"]) == set(ALL_WINDOWS)
    assert result["AAA"][ReturnWindow.D1] == Decimal("4")
    assert result["AAA"][ReturnWindow.D30] == Decimal("30")
    # No prior-year data → YTD falls back to first current-year bar (100 → 130).
    assert result["AAA"][ReturnWindow.YTD] == Decimal("30")


def test_history_fetched_once_for_the_batch() -> None:
    fake = _provider(AAA=_AAA)
    compute_returns_by_period(["AAA", "AAA"], as_of=_AS_OF, provider=fake)
    assert fake.batch_call_count == 1


def test_tickers_are_normalised_to_upper() -> None:
    fake = _provider(AAA=_AAA)
    result = compute_returns_by_period([" aaa "], as_of=_AS_OF, provider=fake)
    assert "AAA" in result
    assert result["AAA"][ReturnWindow.D1] == Decimal("4")


def test_unservable_ticker_yields_all_none_and_others_still_returned() -> None:
    # BBB has no series → provider omits it → all-None, AAA unaffected.
    fake = _provider(AAA=_AAA)
    result = compute_returns_by_period(["AAA", "BBB"], as_of=_AS_OF, provider=fake)

    assert result["BBB"] == {window: None for window in ALL_WINDOWS}
    assert result["AAA"][ReturnWindow.D30] == Decimal("30")


def test_windows_argument_restricts_computed_windows() -> None:
    fake = _provider(AAA=_AAA)
    result = compute_returns_by_period(
        ["AAA"], as_of=_AS_OF, provider=fake, windows=[ReturnWindow.D1]
    )
    assert set(result["AAA"]) == {ReturnWindow.D1}


def test_empty_ticker_list_returns_empty_map() -> None:
    fake = _provider(AAA=_AAA)
    assert compute_returns_by_period([], as_of=_AS_OF, provider=fake) == {}


def test_stats_carry_pct_and_window_high_low() -> None:
    fake = _provider(AAA=_AAA)
    result = compute_return_stats_by_period(["AAA"], as_of=_AS_OF, provider=fake)

    d30 = result["AAA"][ReturnWindow.D30]
    assert d30 is not None
    assert d30.pct == Decimal("30")
    # _AAA bars collapse OHLC to close → window high/low are the max/min closes.
    assert d30.high == Decimal("130")
    assert d30.low == Decimal("100")


def test_stats_unservable_ticker_yields_all_none() -> None:
    fake = _provider(AAA=_AAA)
    result = compute_return_stats_by_period(["BBB"], as_of=_AS_OF, provider=fake)
    assert result["BBB"] == {window: None for window in ALL_WINDOWS}
