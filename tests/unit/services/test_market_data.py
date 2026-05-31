from datetime import UTC, datetime
from decimal import Decimal

import pytest

import app.services.market_data as svc
import app.services.valuation as valuation_mod
from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries, OhlcUnavailableError
from app.domain.money import Currency
from app.services.valuation import clear_live_positions_cache
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
def _clear_caches() -> None:
    clear_live_positions_cache()
    yield  # type: ignore[misc]
    clear_live_positions_cache()


def test_ticker_normalised_to_upper() -> None:
    fake = FakeOhlcDataProvider()
    result = svc.get_ohlc_history("nvda", ChartPeriod.SIX_MONTH, provider=fake)
    assert result is FAKE_SERIES_NVDA_6MO


def test_clear_market_data_caches_clears_live_positions_and_adapter() -> None:
    fake = FakeOhlcDataProvider()
    # Prime the live positions cache
    valuation_mod._live_positions_cache["dummy"] = (1.0, {})
    assert valuation_mod._live_positions_cache

    svc.clear_market_data_caches(fake)

    assert not valuation_mod._live_positions_cache
    assert fake.clear_cache_count == 1


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


def test_aggregation_applied_on_every_call() -> None:
    """Aggregation runs on every call (caching is now adapter responsibility)."""
    raw = _series(
        _bar("2024-01-02T09:30"), _bar("2024-01-02T10:00"),
        period=ChartPeriod.FIVE_DAY,
    )
    fake = FakeOhlcDataProvider(series_map={("NVDA", ChartPeriod.FIVE_DAY): raw})
    r1 = svc.get_ohlc_history("NVDA", ChartPeriod.FIVE_DAY, provider=fake)
    r2 = svc.get_ohlc_history("NVDA", ChartPeriod.FIVE_DAY, provider=fake)
    assert fake.call_count == 2  # adapter is called each time (adapter owns caching)
    assert len(r1.bars) == 1
    assert len(r2.bars) == 1
