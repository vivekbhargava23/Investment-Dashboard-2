"""Per-window return math over an OhlcSeries.

Pure domain. No I/O, no `datetime.now()` — `as_of` is always passed in. Returns
are close-to-close percentage changes expressed as `Decimal` percent
(`Decimal("4.2")` == +4.2%).

The existing `OhlcSeries.period_change_pct` measures the full span open→latest
close; it does not cover fixed calendar windows anchored on `as_of`, so this
module adds `period_return` rather than reusing it.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from app.domain.market_data import OhlcSeries


class ReturnWindow(StrEnum):
    D1 = "1D"
    D7 = "7D"
    D30 = "30D"
    YTD = "YTD"


ALL_WINDOWS: tuple[ReturnWindow, ...] = (
    ReturnWindow.D1,
    ReturnWindow.D7,
    ReturnWindow.D30,
    ReturnWindow.YTD,
)

# Calendar-day lookback per fixed-day window.
_LOOKBACK_DAYS: dict[ReturnWindow, int] = {
    ReturnWindow.D7: 7,
    ReturnWindow.D30: 30,
}


def _pct_change(start: Decimal, end: Decimal) -> Decimal | None:
    if start == 0:
        return None
    return (end - start) / start * Decimal("100")


def period_return(
    series: OhlcSeries, window: ReturnWindow, *, as_of: date
) -> Decimal | None:
    """Percent close-to-close return over `window`, or `None` if history is too short.

    All windows end at the latest bar dated on/before `as_of`:
      - ``D1``  — vs the immediately preceding available close.
      - ``D7`` / ``D30`` — vs the most recent close on/before ``as_of − N days``.
      - ``YTD`` — vs the last close of the prior calendar year, or the first close
        of the current year if the series does not reach into the prior year.

    Returns ``None`` when the series has fewer than two bars on/before `as_of`, or
    when the requested window cannot be covered by the available history.
    """
    bars = [bar for bar in series.bars if bar.timestamp.date() <= as_of]
    if len(bars) < 2:
        return None
    end_close = bars[-1].close

    if window is ReturnWindow.D1:
        return _pct_change(bars[-2].close, end_close)

    if window in _LOOKBACK_DAYS:
        cutoff = as_of - timedelta(days=_LOOKBACK_DAYS[window])
        start_close: Decimal | None = None
        for bar in bars:
            if bar.timestamp.date() <= cutoff:
                start_close = bar.close
            else:
                break
        if start_close is None:
            return None
        return _pct_change(start_close, end_close)

    # YTD
    prior_year_close: Decimal | None = None
    first_current_year_close: Decimal | None = None
    for bar in bars:
        bar_year = bar.timestamp.date().year
        if bar_year < as_of.year:
            prior_year_close = bar.close
        elif bar_year == as_of.year and first_current_year_close is None:
            first_current_year_close = bar.close
    start = prior_year_close if prior_year_close is not None else first_current_year_close
    if start is None:
        return None
    return _pct_change(start, end_close)
