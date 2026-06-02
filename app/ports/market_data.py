from collections.abc import Sequence
from typing import Protocol

from app.domain.market_data import ChartPeriod, OhlcSeries


class OhlcDataProvider(Protocol):
    def get_ohlc_history(self, ticker: str, period: ChartPeriod) -> OhlcSeries:
        """Fetch OHLC history for a ticker over a period.

        Raises OhlcUnavailableError if the ticker has no data for this period.
        """
        ...

    def get_ohlc_histories(
        self, tickers: Sequence[str], period: ChartPeriod
    ) -> dict[str, OhlcSeries]:
        """Batch OHLC fetch.

        Per-ticker failures are omitted from the result, never raised.
        """
        ...

    def clear_cache(self) -> None: ...
