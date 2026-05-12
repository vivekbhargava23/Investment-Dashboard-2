from __future__ import annotations

from datetime import UTC, datetime

from app.adapters.company_cache.ttl import (
    PRICES_TTL_AFTER_CLOSE,
    PRICES_TTL_MARKET_HOURS,
    prices_ttl,
)


def _dt(weekday: int, hour: int, minute: int = 0) -> datetime:
    """Create a UTC datetime for the given weekday (0=Mon) and time."""
    # 2026-05-11 is a Monday (weekday=0)
    base_monday = datetime(2026, 5, 11, tzinfo=UTC)
    from datetime import timedelta
    return base_monday.replace(hour=hour, minute=minute) + timedelta(days=weekday)


def test_prices_ttl_during_nyse_hours_weekday() -> None:
    # Monday 15:00 UTC — within 14:30–21:00
    now = _dt(weekday=0, hour=15, minute=0)
    assert prices_ttl(now) == PRICES_TTL_MARKET_HOURS


def test_prices_ttl_saturday() -> None:
    # Saturday 15:00 UTC
    now = _dt(weekday=5, hour=15, minute=0)
    assert prices_ttl(now) == PRICES_TTL_AFTER_CLOSE


def test_prices_ttl_after_nyse_close() -> None:
    # Monday 22:00 UTC — after 21:00 close
    now = _dt(weekday=0, hour=22, minute=0)
    assert prices_ttl(now) == PRICES_TTL_AFTER_CLOSE


def test_prices_ttl_before_nyse_open() -> None:
    # Monday 13:00 UTC — before 14:30 open
    now = _dt(weekday=0, hour=13, minute=0)
    assert prices_ttl(now) == PRICES_TTL_AFTER_CLOSE


def test_prices_ttl_at_nyse_open() -> None:
    # Monday exactly 14:30 UTC — market opens
    now = _dt(weekday=0, hour=14, minute=30)
    assert prices_ttl(now) == PRICES_TTL_MARKET_HOURS


def test_prices_ttl_friday_during_hours() -> None:
    now = _dt(weekday=4, hour=16, minute=0)
    assert prices_ttl(now) == PRICES_TTL_MARKET_HOURS


def test_prices_ttl_sunday() -> None:
    now = _dt(weekday=6, hour=12, minute=0)
    assert prices_ttl(now) == PRICES_TTL_AFTER_CLOSE
