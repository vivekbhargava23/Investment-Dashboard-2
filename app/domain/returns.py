"""Per-window return math over an OhlcSeries.

Pure domain. No I/O, no `datetime.now()` — `as_of` is always passed in. Returns
are close-to-close percentage changes expressed as `Decimal` percent
(`Decimal("4.2")` == +4.2%).

The existing `OhlcSeries.period_change_pct` measures the full span open→latest
close; it does not cover fixed calendar windows anchored on `as_of`, so this
module adds `period_return` rather than reusing it.

`period_stats` additionally surfaces the window's high/low (from the daily bars'
high/low fields, candlestick-style) so the treemap hover can show a price range,
not just the colour-driving return.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.domain.market_data import OhlcBar, OhlcSeries


class ReturnWindow(StrEnum):
    """Return-measurement windows, mirroring the app-wide ``ChartPeriod`` labels.

    Using the same label set as ``ChartPeriod`` (1D / 5D / 1M / 3M / 6M / 1Y / 2Y /
    5Y / YTD) keeps the treemap/heatmap colour windows consistent with every chart
    page's period selector, instead of inventing a separate ``7D``/``30D`` set.
    """

    D1 = "1D"
    D5 = "5D"
    M1 = "1M"
    M3 = "3M"
    M6 = "6M"
    Y1 = "1Y"
    Y2 = "2Y"
    Y5 = "5Y"
    YTD = "YTD"


ALL_WINDOWS: tuple[ReturnWindow, ...] = (
    ReturnWindow.D1,
    ReturnWindow.D5,
    ReturnWindow.M1,
    ReturnWindow.M3,
    ReturnWindow.M6,
    ReturnWindow.Y1,
    ReturnWindow.Y2,
    ReturnWindow.Y5,
    ReturnWindow.YTD,
)

# Bar-count lookback for the short, trading-session windows. ``D1`` is the latest
# close vs the prior close (2 bars); ``D5`` is a trading-week return (6 bars span 5
# sessions). Anchoring these on bar count, not calendar days, keeps "5D" honest as
# five trading days rather than a calendar week.
_LOOKBACK_BARS: dict[ReturnWindow, int] = {
    ReturnWindow.D1: 2,
    ReturnWindow.D5: 6,
}

# Calendar-day lookback per fixed-day window.
_LOOKBACK_DAYS: dict[ReturnWindow, int] = {
    ReturnWindow.M1: 30,
    ReturnWindow.M3: 90,
    ReturnWindow.M6: 180,
    ReturnWindow.Y1: 365,
    ReturnWindow.Y2: 730,
    ReturnWindow.Y5: 1825,
}


class WindowStats(BaseModel):
    """Return percent plus the high/low over a window (native price, candlestick-style)."""

    model_config = ConfigDict(frozen=True)

    pct: Decimal | None
    high: Decimal
    low: Decimal


def _pct_change(start: Decimal, end: Decimal) -> Decimal | None:
    if start == 0:
        return None
    return (end - start) / start * Decimal("100")


def _window_bars(
    series: OhlcSeries, window: ReturnWindow, as_of: date
) -> list[OhlcBar] | None:
    """Bars from the window's start anchor through the latest bar on/before `as_of`.

    The first element is the close-to-close baseline; the slice as a whole is the
    span over which high/low are measured. Returns ``None`` when the series has
    fewer than two bars on/before `as_of`, or the window can't be covered.
    """
    bars = [bar for bar in series.bars if bar.timestamp.date() <= as_of]
    if len(bars) < 2:
        return None

    if window in _LOOKBACK_BARS:
        count = _LOOKBACK_BARS[window]
        if len(bars) < count:
            return None
        return bars[-count:]

    if window in _LOOKBACK_DAYS:
        cutoff = as_of - timedelta(days=_LOOKBACK_DAYS[window])
        start_idx: int | None = None
        for i, bar in enumerate(bars):
            if bar.timestamp.date() <= cutoff:
                start_idx = i
            else:
                break
        if start_idx is None:
            return None
        return bars[start_idx:]

    # YTD — anchor on the last prior-year bar, else the first current-year bar.
    prior_year_idx: int | None = None
    first_current_year_idx: int | None = None
    for i, bar in enumerate(bars):
        bar_year = bar.timestamp.date().year
        if bar_year < as_of.year:
            prior_year_idx = i
        elif bar_year == as_of.year and first_current_year_idx is None:
            first_current_year_idx = i
    anchor = prior_year_idx if prior_year_idx is not None else first_current_year_idx
    if anchor is None:
        return None
    return bars[anchor:]


def period_return(
    series: OhlcSeries, window: ReturnWindow, *, as_of: date
) -> Decimal | None:
    """Percent close-to-close return over `window`, or `None` if history is too short.

    All windows end at the latest bar dated on/before `as_of`:
      - ``D1``  — vs the immediately preceding available close.
      - ``D5``  — vs the close five trading sessions back (6-bar span).
      - ``M1`` / ``M3`` / ``M6`` / ``Y1`` / ``Y2`` / ``Y5`` — vs the most recent
        close on/before ``as_of − N days``.
      - ``YTD`` — vs the last close of the prior calendar year, or the first close
        of the current year if the series does not reach into the prior year.

    Returns ``None`` when the series has fewer than two bars on/before `as_of`, or
    when the requested window cannot be covered by the available history.
    """
    bars = _window_bars(series, window, as_of)
    if bars is None:
        return None
    return _pct_change(bars[0].close, bars[-1].close)


def period_stats(
    series: OhlcSeries, window: ReturnWindow, *, as_of: date
) -> WindowStats | None:
    """`period_return` plus the high/low over the same window span.

    ``high``/``low`` are the max/min of the daily bars' ``high``/``low`` across the
    window slice — a true period range, like a candlestick's wick. Returns ``None``
    on the same too-short/uncovered conditions as `period_return`.
    """
    bars = _window_bars(series, window, as_of)
    if bars is None:
        return None
    return WindowStats(
        pct=_pct_change(bars[0].close, bars[-1].close),
        high=max(bar.high for bar in bars),
        low=min(bar.low for bar in bars),
    )
