import pytest

from app.domain.market_data import ChartPeriod, OhlcUnavailableError
from app.services import market_data
from app.services.market_data import clear_market_data_caches, get_ohlc_history
from tests.fakes.ohlc import FakeOhlcDataProvider


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    market_data._cache.clear()


def test_cache_miss_calls_provider_then_caches() -> None:
    fake = FakeOhlcDataProvider()

    first = get_ohlc_history("nvda", ChartPeriod.SIX_MONTH, provider=fake)
    second = get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)

    assert first == second
    assert fake.call_count == 1


def test_intraday_ttl_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeOhlcDataProvider()
    now = 1000.0
    monkeypatch.setattr(market_data.time, "monotonic", lambda: now)

    get_ohlc_history("NVDA", ChartPeriod.ONE_DAY, provider=fake)
    now += 15 * 60 + 1
    get_ohlc_history("NVDA", ChartPeriod.ONE_DAY, provider=fake)

    assert fake.call_count == 2


def test_daily_ttl_hit_within_24h(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeOhlcDataProvider()
    now = 1000.0
    monkeypatch.setattr(market_data.time, "monotonic", lambda: now)

    get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)
    now += 24 * 60 * 60 - 60
    get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)

    assert fake.call_count == 1


def test_daily_ttl_miss_after_24h(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeOhlcDataProvider()
    now = 1000.0
    monkeypatch.setattr(market_data.time, "monotonic", lambda: now)

    get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)
    now += 24 * 60 * 60 + 1
    get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)

    assert fake.call_count == 2


def test_different_periods_cached_independently() -> None:
    fake = FakeOhlcDataProvider()

    get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)
    get_ohlc_history("NVDA", ChartPeriod.ONE_YEAR, provider=fake)

    assert fake.call_count == 2


def test_clear_market_data_caches_clears_service_and_provider_cache() -> None:
    fake = FakeOhlcDataProvider()
    get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)

    clear_market_data_caches(fake)
    get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)

    assert fake.clear_count == 1
    assert fake.call_count == 2


def test_ohlc_unavailable_error_propagates() -> None:
    fake = FakeOhlcDataProvider()
    fake.raise_for.add(("NVDA", ChartPeriod.SIX_MONTH))

    with pytest.raises(OhlcUnavailableError):
        get_ohlc_history("NVDA", ChartPeriod.SIX_MONTH, provider=fake)
