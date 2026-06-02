from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries, OhlcUnavailableError
from app.domain.money import Currency


def _bar(ts: str, o: str, h: str, lo: str, c: str, vol: int | None = 1000) -> OhlcBar:
    return OhlcBar(
        timestamp=datetime.fromisoformat(ts).replace(tzinfo=UTC),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(lo),
        close=Decimal(c),
        volume=vol,
    )


FAKE_SERIES_NVDA_6MO = OhlcSeries(
    ticker="NVDA",
    currency=Currency.USD,
    period=ChartPeriod.SIX_MONTH,
    bars=(
        _bar("2024-01-02", "450.00", "460.00", "445.00", "455.00"),
        _bar("2024-01-03", "455.00", "470.00", "450.00", "465.00"),
        _bar("2024-01-04", "465.00", "475.00", "460.00", "472.00"),
    ),
    fetched_at=datetime(2024, 7, 1, tzinfo=UTC),
)

FAKE_SERIES_RHM_1Y = OhlcSeries(
    ticker="RHM.DE",
    currency=Currency.EUR,
    period=ChartPeriod.ONE_YEAR,
    bars=(
        _bar("2023-07-01", "200.00", "210.00", "198.00", "205.00"),
        _bar("2023-07-02", "205.00", "215.00", "203.00", "212.00"),
    ),
    fetched_at=datetime(2024, 7, 1, tzinfo=UTC),
)


class FakeOhlcDataProvider:
    """Fake OhlcDataProvider for testing. Returns hardcoded series by (ticker, period)."""

    def __init__(
        self,
        series_map: dict[tuple[str, ChartPeriod], OhlcSeries] | None = None,
        raise_for: set[tuple[str, ChartPeriod]] | None = None,
    ) -> None:
        self._series_map = series_map or {
            ("NVDA", ChartPeriod.SIX_MONTH): FAKE_SERIES_NVDA_6MO,
            ("RHM.DE", ChartPeriod.ONE_YEAR): FAKE_SERIES_RHM_1Y,
        }
        self._raise_for: set[tuple[str, ChartPeriod]] = raise_for or set()
        self.call_count = 0
        self.batch_call_count = 0
        self.clear_cache_count = 0

    def get_ohlc_history(self, ticker: str, period: ChartPeriod) -> OhlcSeries:
        self.call_count += 1
        key = (ticker, period)
        if key in self._raise_for:
            raise OhlcUnavailableError(reason=f"Fake: no data for {ticker} {period}")
        if key in self._series_map:
            return self._series_map[key]
        raise OhlcUnavailableError(reason=f"Fake: {ticker} {period} not in series_map")

    def get_ohlc_histories(
        self, tickers: Sequence[str], period: ChartPeriod
    ) -> dict[str, OhlcSeries]:
        self.batch_call_count += 1
        result: dict[str, OhlcSeries] = {}
        for ticker in tickers:
            try:
                result[ticker] = self.get_ohlc_history(ticker, period)
            except OhlcUnavailableError:
                pass
        return result

    def clear_cache(self) -> None:
        self.clear_cache_count += 1
