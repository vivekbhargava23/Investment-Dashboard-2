from unittest.mock import patch

import pytest

import app.services.market_data as svc
from app.domain.market_data import ChartPeriod, OhlcUnavailableError
from tests.fakes.ohlc import FAKE_SERIES_NVDA_6MO, FakeOhlcDataProvider


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
