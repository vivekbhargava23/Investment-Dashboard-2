from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

import app.services.market_data as svc
from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries, OhlcUnavailableError
from app.domain.money import Currency
from tests.fakes.ohlc import FAKE_SERIES_NVDA_6MO, FakeOhlcDataProvider


def _bar(ts: str, o: str = "100", h: str = "110", lo: str = "95", c: str = "105") -> OhlcBar:
    return OhlcBar(
        timestamp=datetime.fromisoformat(ts).replace(tzinfo=UTC),
        open=Decimal(o), high=Decimal(h), low=Decimal(lo), close=Decimal(c), volume=1000,
    )


def _series(*bars: OhlcBar, period: ChartPeriod) -> OhlcSeries:
    return OhlcSeries(
        ticker="NVDA", currency=Currency.USD, period=period,
        bars=tuple(bars), fetched_at=datetime(2024, 7, 1, tzinfo=UTC),
    )


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    svc._cache.clear()
    yield  # type: ignore[misc]
    svc._cache.clear()


def test_cache_miss_calls_provider_once() -> None:
    fake = FakeOhlcDataProvider()
    result1 = svc.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)
    result2 = svc.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)
    assert result1 is result2
    assert fake.call_count == 1


def test_ticker_normalised_to_upper() -> None:
    fake = FakeOhlcDataProvider()
    result = svc.get_ohlc_history("nvda", ChartPeriod.SIX_MONTH, provider=fake)
    assert result is FAKE_SERIES_NVDA_6MO


def test_intraday_ttl_miss_after_15_minutes() -> None:
    fake = FakeOhlcDataProvider(
        series_map={("NVDA", ChartPeriod.ONE_DAY): FAKE_SERIES_NVDA_6MO}
    )
    with patch("app.services.market_data.time") as mock_time:
        mock_time.monotonic.return_value = 1000.0
        svc.get_ohlc_history("NVDA", ChartPeriod.ONE_DAY, provider=fake)
        assert fake.call_count == 1

        # Still within 15-min TTL
        mock_time.monotonic.return_value = 1000.0 + 14 * 60
        svc.get_ohlc_history("NVDA", ChartPeriod.ONE_DAY, provider=fake)
        assert fake.call_count == 1

        # Past 15-min TTL
        mock_time.monotonic.return_value = 1000.0 + 15 * 60 + 1
        svc.get_ohlc_history("NVDA", ChartPeriod.ONE_DAY, provider=fake)
        assert fake.call_count == 2


def test_daily_ttl_hit_within_24h() -> None:
    fake = FakeOhlcDataProvider()
    with patch("app.services.market_data.time") as mock_time:
        mock_time.monotonic.return_value = 1000.0
        svc.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)
        assert fake.call_count == 1

        # 23h59m later — still within 24h TTL
        mock_time.monotonic.return_value = 1000.0 + 23 * 3600 + 59 * 60
        svc.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)
        assert fake.call_count == 1


def test_daily_ttl_miss_after_24h() -> None:
    fake = FakeOhlcDataProvider()
    with patch("app.services.market_data.time") as mock_time:
        mock_time.monotonic.return_value = 1000.0
        svc.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)
        assert fake.call_count == 1

        # 24h + 1 minute later
        mock_time.monotonic.return_value = 1000.0 + 24 * 3600 + 60
        svc.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)
        assert fake.call_count == 2


def test_different_periods_cached_independently() -> None:
    fake = FakeOhlcDataProvider(
        series_map={
            ("NVDA", ChartPeriod.SIX_MONTH): FAKE_SERIES_NVDA_6MO,
            ("NVDA", ChartPeriod.ONE_YEAR): FAKE_SERIES_NVDA_6MO,
        }
    )
    svc.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)
    svc.get_ohlc_history("NVDA", ChartPeriod.ONE_YEAR, provider=fake)
    assert fake.call_count == 2
    assert len(svc._cache) == 2


def test_clear_market_data_caches() -> None:
    fake = FakeOhlcDataProvider()
    svc.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)
    assert len(svc._cache) == 1

    svc.clear_market_data_caches(fake)

    assert len(svc._cache) == 0
    assert fake.clear_cache_count == 1

    svc.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)
    assert fake.call_count == 2


def test_ohlc_unavailable_error_propagates() -> None:
    fake = FakeOhlcDataProvider(
        raise_for={("NVDA", ChartPeriod.SIX_MONTH)}
    )
    with pytest.raises(OhlcUnavailableError):
        svc.get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)


# --- aggregation applied per period ---

def test_one_month_period_no_aggregation() -> None:
    """ONE_MONTH has no aggregation — bar count unchanged."""
    raw = _series(
        _bar("2024-01-02"), _bar("2024-01-03"), _bar("2024-01-04"),
        period=ChartPeriod.ONE_MONTH,
    )
    fake = FakeOhlcDataProvider(series_map={("NVDA", ChartPeriod.ONE_MONTH): raw})
    result = svc.get_ohlc_history("NVDA", ChartPeriod.ONE_MONTH, provider=fake)
    assert len(result.bars) == 3


def test_five_day_period_aggregates_to_daily() -> None:
    """FIVE_DAY → daily aggregation: same-day 15m bars collapse to one daily bar."""
    raw = _series(
        _bar("2024-01-02T09:30"), _bar("2024-01-02T10:00"), _bar("2024-01-02T10:30"),
        _bar("2024-01-03T09:30"), _bar("2024-01-03T10:00"),
        period=ChartPeriod.FIVE_DAY,
    )
    fake = FakeOhlcDataProvider(series_map={("NVDA", ChartPeriod.FIVE_DAY): raw})
    result = svc.get_ohlc_history("NVDA", ChartPeriod.FIVE_DAY, provider=fake)
    assert len(result.bars) == 2  # 5 intraday bars → 2 daily bars


def test_one_year_period_aggregates_to_weekly() -> None:
    """ONE_YEAR → weekly aggregation: daily bars in same ISO week collapse to one weekly bar."""
    raw = _series(
        # Week 1 of 2024: Jan 2–5
        _bar("2024-01-02"), _bar("2024-01-03"), _bar("2024-01-05"),
        # Week 2 of 2024: Jan 8–12
        _bar("2024-01-08"), _bar("2024-01-09"),
        period=ChartPeriod.ONE_YEAR,
    )
    fake = FakeOhlcDataProvider(series_map={("NVDA", ChartPeriod.ONE_YEAR): raw})
    result = svc.get_ohlc_history("NVDA", ChartPeriod.ONE_YEAR, provider=fake)
    assert len(result.bars) == 2  # 5 daily bars across 2 weeks → 2 weekly bars


def test_five_year_period_aggregates_to_monthly() -> None:
    """FIVE_YEAR → monthly aggregation: daily bars in same month collapse to one bar."""
    raw = _series(
        _bar("2024-01-02"), _bar("2024-01-15"), _bar("2024-01-31"),
        _bar("2024-02-01"), _bar("2024-02-15"),
        period=ChartPeriod.FIVE_YEAR,
    )
    fake = FakeOhlcDataProvider(series_map={("NVDA", ChartPeriod.FIVE_YEAR): raw})
    result = svc.get_ohlc_history("NVDA", ChartPeriod.FIVE_YEAR, provider=fake)
    assert len(result.bars) == 2  # 5 daily bars across 2 months → 2 monthly bars


def test_aggregated_series_is_cached() -> None:
    """The post-aggregation result is what gets cached, not the raw series."""
    raw = _series(
        _bar("2024-01-02T09:30"), _bar("2024-01-02T10:00"),
        period=ChartPeriod.FIVE_DAY,
    )
    fake = FakeOhlcDataProvider(series_map={("NVDA", ChartPeriod.FIVE_DAY): raw})
    r1 = svc.get_ohlc_history("NVDA", ChartPeriod.FIVE_DAY, provider=fake)
    r2 = svc.get_ohlc_history("NVDA", ChartPeriod.FIVE_DAY, provider=fake)
    assert fake.call_count == 1
    assert r1 is r2
    assert len(r1.bars) == 1  # aggregated to 1 daily bar
