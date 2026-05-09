"""Unit tests for app.services.analytics_technicals."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest

from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries, OhlcUnavailableError
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.ports.price_feed import PriceUnavailableError
from app.services.analytics_technicals import (
    OhlcUnavailable,
    build_technicals_view,
)

# ── Fakes ──────────────────────────────────────────────────────────────────────


class FakeRepo:
    def __init__(self, transactions: list[Transaction]) -> None:
        self._txns = transactions

    def load_all(self) -> list[Transaction]:
        return self._txns

    def save_all(self, transactions: Sequence[Transaction]) -> None:
        self._txns = list(transactions)

    def add(self, transaction: Transaction) -> None:
        self._txns.append(transaction)

    def update(self, transaction: Transaction) -> None:
        self._txns = [t if t.id != transaction.id else transaction for t in self._txns]

    def delete(self, transaction_id: str) -> None:
        self._txns = [t for t in self._txns if t.id != transaction_id]

    def get(self, transaction_id: str) -> Transaction:
        return next(t for t in self._txns if t.id == transaction_id)


class FakePriceProvider:
    def __init__(self, price: Decimal = Decimal("105"), currency: Currency = Currency.EUR) -> None:
        self._price = price
        self._currency = currency

    def get_current_price(self, ticker: str) -> Money:
        return Money(amount=self._price, currency=self._currency)

    def get_historical_close(self, ticker: str, on_date: date) -> Money:
        return Money(amount=self._price, currency=self._currency)

    def clear_cache(self) -> None:
        pass


class FailingPriceProvider:
    def get_current_price(self, ticker: str) -> Money:
        raise PriceUnavailableError(ticker, "network error")

    def get_historical_close(self, ticker: str, on_date: date) -> Money:
        raise PriceUnavailableError(ticker, "network error")

    def clear_cache(self) -> None:
        pass


class FakeOhlcProvider:
    def __init__(self, bars: list[OhlcBar], currency: Currency = Currency.EUR) -> None:
        self._bars = bars
        self._currency = currency

    def get_ohlc_history(self, ticker: str, period: ChartPeriod) -> OhlcSeries:
        if not self._bars:
            raise OhlcUnavailableError("no bars")
        return OhlcSeries(
            ticker=ticker,
            currency=self._currency,
            period=period,
            bars=tuple(self._bars),
            fetched_at=datetime(2026, 5, 9, tzinfo=UTC),
        )

    def clear_cache(self) -> None:
        pass


class RaisingOhlcProvider:
    def get_ohlc_history(self, ticker: str, period: ChartPeriod) -> OhlcSeries:
        raise OhlcUnavailableError("feed offline")

    def clear_cache(self) -> None:
        pass


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_bar(day: date, close: Decimal) -> OhlcBar:
    return OhlcBar(
        timestamp=datetime.combine(day, time(12, 0), tzinfo=UTC),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=None,
    )


def _make_bars(
    n: int,
    close: Decimal,
    *,
    start: date = date(2022, 1, 1),
) -> list[OhlcBar]:
    return [_make_bar(start + timedelta(days=i), close) for i in range(n)]


def _make_bars_varied(
    closes: list[Decimal],
    *,
    start: date = date(2022, 1, 1),
) -> list[OhlcBar]:
    return [_make_bar(start + timedelta(days=i), c) for i, c in enumerate(closes)]


def _buy(ticker: str = "RHM.DE", currency: Currency = Currency.EUR) -> Transaction:
    price_currency = currency
    return Transaction(
        id=f"{ticker}-buy",
        type=TransactionType.BUY,
        ticker=ticker,
        trade_date=date(2024, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("100"), currency=price_currency),
        fx_rate_eur=Decimal("1"),
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestBuildTechnicalsView:
    def test_universe_validation_raises_for_unknown_ticker(self) -> None:
        repo = FakeRepo([_buy("RHM.DE")])
        ohlc = FakeOhlcProvider(_make_bars(50, Decimal("100")))
        with pytest.raises(ValueError, match="not in open positions"):
            build_technicals_view(
                ticker="AAPL",
                period="6M",
                repo=repo,
                price_feed=FakePriceProvider(),
                ohlc=ohlc,
                as_of=date(2026, 5, 9),
            )

    def test_insufficient_history_for_sma50(self) -> None:
        """Position with 30 days of OHLC: SMA(50) is all None for visible window."""
        repo = FakeRepo([_buy("RHM.DE")])
        bars = _make_bars(30, Decimal("100"))
        ohlc = FakeOhlcProvider(bars)
        view = build_technicals_view(
            ticker="RHM.DE",
            period="6M",
            repo=repo,
            price_feed=FakePriceProvider(),
            ohlc=ohlc,
            as_of=date(2026, 5, 9),
        )
        assert view.signals.trend_50 == "insufficient"
        assert all(v is None for v in view.sma_50)
        # Chart data still populated
        assert len(view.ohlc) == 30

    def test_insufficient_history_for_sma200_but_enough_for_sma50(self) -> None:
        """Position with 80 days: SMA50 computed, SMA200 insufficient, cross insufficient."""
        repo = FakeRepo([_buy("RHM.DE")])
        bars = _make_bars(80, Decimal("100"))
        ohlc = FakeOhlcProvider(bars)
        view = build_technicals_view(
            ticker="RHM.DE",
            period="6M",
            repo=repo,
            price_feed=FakePriceProvider(),
            ohlc=ohlc,
            as_of=date(2026, 5, 9),
        )
        assert view.signals.trend_50 in ("above", "below")
        assert view.signals.trend_200 == "insufficient"
        assert view.signals.cross == "insufficient"

    def test_insufficient_history_for_rsi(self) -> None:
        """Position with 10 days: RSI requires 15, so view.rsi is None."""
        repo = FakeRepo([_buy("RHM.DE")])
        bars = _make_bars(10, Decimal("100"))
        ohlc = FakeOhlcProvider(bars)
        view = build_technicals_view(
            ticker="RHM.DE",
            period="6M",
            repo=repo,
            price_feed=FakePriceProvider(),
            ohlc=ohlc,
            as_of=date(2026, 5, 9),
        )
        assert view.rsi is None
        assert view.signals.rsi_level == "insufficient"

    def test_live_change_pct_is_none_when_price_unavailable(self) -> None:
        """If price feed fails, live_price is None and live_change_pct is None."""
        repo = FakeRepo([_buy("RHM.DE")])
        bars = _make_bars(30, Decimal("100"))
        ohlc = FakeOhlcProvider(bars)
        view = build_technicals_view(
            ticker="RHM.DE",
            period="6M",
            repo=repo,
            price_feed=FailingPriceProvider(),  # type: ignore[arg-type]
            ohlc=ohlc,
            as_of=date(2026, 5, 9),
        )
        assert view.live_price is None
        assert view.signals.live_change_pct is None

    def test_ohlc_fetch_failure_raises_ohlc_unavailable(self) -> None:
        """Provider raising OhlcUnavailableError → service raises OhlcUnavailable."""
        repo = FakeRepo([_buy("RHM.DE")])
        with pytest.raises(OhlcUnavailable) as exc_info:
            build_technicals_view(
                ticker="RHM.DE",
                period="6M",
                repo=repo,
                price_feed=FakePriceProvider(),
                ohlc=RaisingOhlcProvider(),
                as_of=date(2026, 5, 9),
            )
        # The original reason is preserved in args[0]
        assert "feed offline" in exc_info.value.args[0]

    def test_sma_seeded_from_before_visible_window(self) -> None:
        """250 bars + period='1M' (≈21 visible days): first visible SMA(200) is non-None.

        This proves the buffer is applied: SMA(200) is computed from all 250 bars,
        so by the time we reach the last 21 bars (the visible window), SMA(200) has
        already been seeded from the preceding 229 bars.
        """
        repo = FakeRepo([_buy("RHM.DE")])
        bars = _make_bars(250, Decimal("100"))
        ohlc = FakeOhlcProvider(bars)
        view = build_technicals_view(
            ticker="RHM.DE",
            period="1M",
            repo=repo,
            price_feed=FakePriceProvider(),
            ohlc=ohlc,
            as_of=date(2026, 5, 9),
        )
        # Visible window is last ≈21 bars; SMA(200) should be non-None throughout
        assert view.sma_200[0] is not None, "SMA(200) should be seeded for the entire 1M window"

    def test_cross_detection_on_real_sequence(self) -> None:
        """300 bars with a designed golden cross at index 239 → days_ago == 60.

        Close price phases:
          bars[0..99]   = 200  (high phase)
          bars[100..199] = 50  (low phase: SMA50 drops below SMA200)
          bars[200..299] = 126 (recovery: SMA50 rises and crosses SMA200 at index 239)

        Analytically verified: diff[238] < 0, diff[239] > 0 → golden cross at 239.
        days_ago = (300 - 1) - 239 = 60.
        """
        repo = FakeRepo([_buy("RHM.DE")])
        closes: list[Decimal] = (
            [Decimal("200")] * 100
            + [Decimal("50")] * 100
            + [Decimal("126")] * 100
        )
        bars = _make_bars_varied(closes)
        ohlc = FakeOhlcProvider(bars)
        view = build_technicals_view(
            ticker="RHM.DE",
            period="5Y",
            repo=repo,
            price_feed=FakePriceProvider(Decimal("126")),
            ohlc=ohlc,
            as_of=date(2026, 5, 9),
        )
        assert view.signals.cross == "golden"
        assert view.signals.cross_days_ago == 60

    def test_currency_usd_for_unsuffixed_ticker(self) -> None:
        """An unsuffixed ticker (AAPL) → view.currency == Currency.USD."""
        repo = FakeRepo([
            Transaction(
                id="aapl-buy",
                type=TransactionType.BUY,
                ticker="AAPL",
                trade_date=date(2024, 1, 1),
                shares=Decimal("10"),
                price_native=Money(amount=Decimal("150"), currency=Currency.USD),
                fx_rate_eur=Decimal("0.9"),
            )
        ])
        bars = _make_bars(30, Decimal("150"))
        ohlc = FakeOhlcProvider(bars, currency=Currency.USD)
        view = build_technicals_view(
            ticker="AAPL",
            period="6M",
            repo=repo,
            price_feed=FakePriceProvider(currency=Currency.USD),
            ohlc=ohlc,
            as_of=date(2026, 5, 9),
        )
        assert view.currency == Currency.USD

    def test_currency_eur_for_de_suffix_ticker(self) -> None:
        """An .DE-suffix ticker → view.currency == Currency.EUR."""
        repo = FakeRepo([_buy("RHM.DE")])
        bars = _make_bars(30, Decimal("100"))
        ohlc = FakeOhlcProvider(bars, currency=Currency.EUR)
        view = build_technicals_view(
            ticker="RHM.DE",
            period="6M",
            repo=repo,
            price_feed=FakePriceProvider(),
            ohlc=ohlc,
            as_of=date(2026, 5, 9),
        )
        assert view.currency == Currency.EUR
