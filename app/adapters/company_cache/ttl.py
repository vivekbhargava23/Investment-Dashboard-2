from __future__ import annotations

from datetime import datetime, timedelta

PROFILE_TTL = timedelta(days=30)
PRICES_TTL_MARKET_HOURS = timedelta(minutes=15)
PRICES_TTL_AFTER_CLOSE = timedelta(hours=24)
FINANCIALS_TTL = timedelta(hours=24)

# NYSE market hours in UTC: 14:30–21:00 Mon–Fri
_NYSE_OPEN_H = 14
_NYSE_OPEN_M = 30
_NYSE_CLOSE_H = 21
_NYSE_CLOSE_M = 0


def prices_ttl(now: datetime) -> timedelta:
    """Return 15min during NYSE market hours (14:30–21:00 UTC Mon–Fri), 24h otherwise."""
    weekday = now.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    if weekday >= 5:
        return PRICES_TTL_AFTER_CLOSE

    open_minutes = _NYSE_OPEN_H * 60 + _NYSE_OPEN_M
    close_minutes = _NYSE_CLOSE_H * 60 + _NYSE_CLOSE_M
    current_minutes = now.hour * 60 + now.minute

    if open_minutes <= current_minutes < close_minutes:
        return PRICES_TTL_MARKET_HOURS
    return PRICES_TTL_AFTER_CLOSE
