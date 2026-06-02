"""OHLC market data service.

Aggregation is applied after fetch so callers receive display-ready data:
  - 5D  → daily bars   (avoids intraday-gap artefacts from 15m bars)
  - 1Y/2Y → weekly bars (252 daily bars → 52 weekly; readable candle widths)
  - 5Y  → monthly bars (~60 monthly bars for a 5-year view)
  - YTD → weekly bars  (variable length, weekly gives stable bar count)

Caching is handled by the adapter (YfinanceAdapter._ohlc_cache), which already
holds OhlcSeries with matching TTLs. The former service-level _cache was redundant
after TICKET-022a added adapter-level OHLC caching.
"""

from app.domain.market_data import (
    AggregationFreq,
    ChartPeriod,
    OhlcSeries,
    aggregate_ohlc_series,
)
from app.ports.market_data import OhlcDataProvider

# Periods that need coarser bars to look good on a candlestick chart.
# None = keep the yfinance-native interval (daily for 1M–6M, intraday for 1D).
_AGGREGATION: dict[ChartPeriod, AggregationFreq | None] = {
    ChartPeriod.ONE_DAY: None,
    ChartPeriod.FIVE_DAY: "day",
    ChartPeriod.ONE_MONTH: None,
    ChartPeriod.THREE_MONTH: None,
    ChartPeriod.SIX_MONTH: None,
    ChartPeriod.ONE_YEAR: "week",
    ChartPeriod.TWO_YEAR: "week",
    ChartPeriod.FIVE_YEAR: "month",
    ChartPeriod.YEAR_TO_DATE: "week",
}


def get_ohlc_history(
    ticker: str,
    period: ChartPeriod,
    *,
    provider: OhlcDataProvider,
    freq: AggregationFreq | None = None,
) -> OhlcSeries:
    """Return OHLC history with period-appropriate aggregation.

    freq: explicit override; None falls back to _AGGREGATION default for the period.
    Caching is handled by the adapter; this service only owns aggregation.
    Raises OhlcUnavailableError if the provider has no data.
    """
    ticker = ticker.strip().upper()
    series = provider.get_ohlc_history(ticker, period)
    effective_freq = freq if freq is not None else _AGGREGATION.get(period)
    if effective_freq is not None:
        series = aggregate_ohlc_series(series, effective_freq)
    return series


def clear_market_data_caches(provider: OhlcDataProvider) -> None:
    """Clear the live-positions cache and the adapter's cache in one call.

    This is the single entry point for the Refresh button.
    """
    from app.services.valuation import clear_live_positions_cache
    clear_live_positions_cache()
    provider.clear_cache()
