from typing import Protocol

from app.domain.market_data import ChartPeriod, OhlcSeries


class OhlcDataProvider(Protocol):
    """Abstract contract for fetching OHLC market history."""

    def get_ohlc_history(self, ticker: str, period: ChartPeriod) -> OhlcSeries:
        """Fetch OHLC history for a ticker over a period.

        Raises OhlcUnavailableError if the ticker has no data for this period.
        """
        ...

    def clear_cache(self) -> None:
        """Invalidate all cached market data."""
        ...

