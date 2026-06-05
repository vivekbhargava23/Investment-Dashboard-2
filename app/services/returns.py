"""Returns-by-period service.

Computes per-ticker percentage returns over the standard windows (1D / 5D / 1M /
3M / 6M / 1Y / 2Y / 5Y / YTD) from a single OHLC fetch, so the Overview treemap
(RD10) and heatmap (RD11) share one source of return numbers instead of each
recomputing them.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from app.domain.market_data import ChartPeriod
from app.domain.returns import ALL_WINDOWS, ReturnWindow, WindowStats, period_stats
from app.ports.market_data import OhlcDataProvider
from app.services.market_data import get_ohlc_histories

# Five years of *daily* bars covers every window: the 5Y window needs a bar ~1825
# days back, which sits at the edge of a 5Y fetch, so fetch 5Y outright. The default
# aggregation is weekly (too coarse for D1/D5), so force daily.
_FETCH_PERIOD = ChartPeriod.FIVE_YEAR


def compute_return_stats_by_period(
    tickers: Sequence[str],
    *,
    as_of: date,
    provider: OhlcDataProvider,
    windows: Sequence[ReturnWindow] = ALL_WINDOWS,
) -> dict[str, dict[ReturnWindow, WindowStats | None]]:
    """Return ``{ticker: {window: WindowStats | None}}`` for every requested window.

    Each ``WindowStats`` carries the close-to-close return percent plus the window
    high/low. History is fetched once for all tickers. Per-ticker provider failures
    are omitted by ``get_ohlc_histories`` (never raised); a ticker with no series
    yields all-``None``. Keys are the normalised (stripped/upper-cased) tickers.
    """
    normalised = [ticker.strip().upper() for ticker in tickers]
    series_map = get_ohlc_histories(
        normalised, _FETCH_PERIOD, provider=provider, freq="day"
    )
    result: dict[str, dict[ReturnWindow, WindowStats | None]] = {}
    for ticker in normalised:
        series = series_map.get(ticker)
        if series is None:
            result[ticker] = {window: None for window in windows}
            continue
        result[ticker] = {
            window: period_stats(series, window, as_of=as_of) for window in windows
        }
    return result


def compute_returns_by_period(
    tickers: Sequence[str],
    *,
    as_of: date,
    provider: OhlcDataProvider,
    windows: Sequence[ReturnWindow] = ALL_WINDOWS,
) -> dict[str, dict[ReturnWindow, Decimal | None]]:
    """Return ``{ticker: {window: pct | None}}`` — the pct projection of the stats map.

    Thin wrapper over ``compute_return_stats_by_period`` for callers that only need
    the return percent (e.g. the heatmap's colour metric).
    """
    stats = compute_return_stats_by_period(
        tickers, as_of=as_of, provider=provider, windows=windows
    )
    return {
        ticker: {
            window: (stat.pct if stat is not None else None)
            for window, stat in window_map.items()
        }
        for ticker, window_map in stats.items()
    }
