"""Returns-by-period service.

Computes per-ticker percentage returns over the standard windows (1D / 7D / 30D /
YTD) from a single OHLC fetch, so the Overview treemap (RD10) and heatmap (RD11)
share one source of return numbers instead of each recomputing them.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from app.domain.market_data import ChartPeriod
from app.domain.returns import ALL_WINDOWS, ReturnWindow, period_return
from app.ports.market_data import OhlcDataProvider
from app.services.market_data import get_ohlc_histories

# One year of *daily* bars covers every window: D30 and the YTD prior-year-end
# both sit inside a 1Y lookback. The default 1Y aggregation is weekly (too coarse
# for D1/D7), so force daily granularity with freq="day".
_FETCH_PERIOD = ChartPeriod.ONE_YEAR


def compute_returns_by_period(
    tickers: Sequence[str],
    *,
    as_of: date,
    provider: OhlcDataProvider,
    windows: Sequence[ReturnWindow] = ALL_WINDOWS,
) -> dict[str, dict[ReturnWindow, Decimal | None]]:
    """Return ``{ticker: {window: pct | None}}`` for every requested window.

    History is fetched once for all tickers. Per-ticker provider failures are
    omitted by ``get_ohlc_histories`` (never raised); a ticker with no series
    yields all-``None``. Keys are the normalised (stripped/upper-cased) tickers.
    """
    normalised = [ticker.strip().upper() for ticker in tickers]
    series_map = get_ohlc_histories(
        normalised, _FETCH_PERIOD, provider=provider, freq="day"
    )
    result: dict[str, dict[ReturnWindow, Decimal | None]] = {}
    for ticker in normalised:
        series = series_map.get(ticker)
        if series is None:
            result[ticker] = {window: None for window in windows}
            continue
        result[ticker] = {
            window: period_return(series, window, as_of=as_of) for window in windows
        }
    return result
