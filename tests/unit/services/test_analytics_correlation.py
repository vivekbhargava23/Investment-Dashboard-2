from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from app.domain import analytics
from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.services.analytics_correlation import (
    CorrelationView,
    build_correlation_view,
    diversification_bucket,
)


class FakeRepo:
    def __init__(self, transactions: list[Transaction]) -> None:
        self._transactions = transactions

    def load_all(self) -> list[Transaction]:
        return self._transactions

    def save_all(self, transactions: Sequence[Transaction]) -> None:
        self._transactions = list(transactions)

    def add(self, transaction: Transaction) -> None:
        self._transactions.append(transaction)

    def update(self, transaction: Transaction) -> None:
        self._transactions = [
            transaction if item.id == transaction.id else item
            for item in self._transactions
        ]

    def delete(self, transaction_id: str) -> None:
        self._transactions = [
            transaction
            for transaction in self._transactions
            if transaction.id != transaction_id
        ]

    def get(self, transaction_id: str) -> Transaction:
        return next(
            transaction
            for transaction in self._transactions
            if transaction.id == transaction_id
        )


class FakePriceProvider:
    def get_current_price(self, ticker: str) -> Money:
        return Money(amount=Decimal("100"), currency=Currency.USD)

    def get_historical_close(self, ticker: str, on_date: date) -> Money:
        return Money(amount=Decimal("100"), currency=Currency.USD)

    def clear_cache(self) -> None:
        return None


class FakeFxProvider:
    def get_current_rate(self, base: Currency, quote: Currency) -> Decimal:
        return Decimal("1")

    def get_historical_rate(
        self,
        base: Currency,
        quote: Currency,
        on_date: date,
    ) -> Decimal:
        return Decimal("1")

    def clear_cache(self) -> None:
        return None


class FakeOhlcProvider:
    def __init__(self, closes: dict[str, list[tuple[date, Decimal]]]) -> None:
        self._closes = closes

    def get_ohlc_history(self, ticker: str, period: ChartPeriod) -> OhlcSeries:
        bars = tuple(
            OhlcBar(
                timestamp=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=None,
            )
            for day, close in self._closes[ticker]
        )
        return OhlcSeries(
            ticker=ticker,
            currency=Currency.USD,
            period=period,
            bars=bars,
            fetched_at=datetime(2026, 5, 9, tzinfo=UTC),
        )

    def clear_cache(self) -> None:
        return None


def _buy(ticker: str, shares: str = "10") -> Transaction:
    return Transaction(
        id=f"{ticker}-buy",
        type=TransactionType.BUY,
        ticker=ticker,
        trade_date=date(2026, 1, 1),
        shares=Decimal(shares),
        price_native=Money(amount=Decimal("10"), currency=Currency.USD),
        fx_rate_eur=Decimal("1"),
    )


def _sell(ticker: str, shares: str = "10") -> Transaction:
    return Transaction(
        id=f"{ticker}-sell",
        type=TransactionType.SELL,
        ticker=ticker,
        trade_date=date(2026, 2, 1),
        shares=Decimal(shares),
        price_native=Money(amount=Decimal("12"), currency=Currency.USD),
        fx_rate_eur=Decimal("1"),
    )


def _dated_closes(
    ticker_index: int,
    *,
    days: int,
    start: date = date(2026, 3, 1),
    missing: date | None = None,
) -> list[tuple[date, Decimal]]:
    values: list[tuple[date, Decimal]] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        if day == missing:
            continue
        close = Decimal("100") + Decimal(ticker_index * 10) + Decimal(offset)
        values.append((day, close))
    return values


def _view(
    transactions: list[Transaction],
    closes: dict[str, list[tuple[date, Decimal]]],
    *,
    window_days: int = 30,
) -> CorrelationView:
    return build_correlation_view(
        repo=FakeRepo(transactions),
        price_feed=FakePriceProvider(),
        fx_feed=FakeFxProvider(),
        ohlc=FakeOhlcProvider(closes),
        as_of=date(2026, 5, 9),
        window_days=window_days,
    )


def test_universe_filtering_excludes_closed_positions() -> None:
    view = _view(
        [_buy("A"), _buy("B"), _buy("C"), _sell("C")],
        {
            "A": _dated_closes(1, days=30),
            "B": _dated_closes(2, days=30),
        },
    )

    assert view.included_tickers == ["A", "B"]
    assert "C" not in view.matrix
    assert all(item.ticker != "C" for item in view.skipped)


def test_insufficient_history_is_skipped() -> None:
    view = _view(
        [_buy("A"), _buy("SHORT")],
        {
            "A": _dated_closes(1, days=60),
            "SHORT": _dated_closes(2, days=30),
        },
        window_days=60,
    )

    assert view.included_tickers == ["A"]
    assert view.skipped[0].ticker == "SHORT"
    assert view.skipped[0].available_days == 30
    assert view.skipped[0].required_days == 60
    assert "SHORT" not in view.matrix
    assert "SHORT" not in view.avg_correlation


def test_trading_date_intersection_drops_dates_missing_from_any_ticker() -> None:
    missing_day = date(2026, 4, 3)
    a_closes = _dated_closes(1, days=60)
    b_closes = _dated_closes(2, days=60, missing=missing_day)

    view = _view(
        [_buy("A"), _buy("B")],
        {"A": a_closes, "B": b_closes},
        window_days=60,
    )

    common_dates = sorted({day for day, _ in a_closes} & {day for day, _ in b_closes})
    expected_returns = {
        "A": analytics.daily_returns([dict(a_closes)[day] for day in common_dates]),
        "B": analytics.daily_returns([dict(b_closes)[day] for day in common_dates]),
    }
    expected = analytics.correlation_matrix(expected_returns)

    assert view.included_tickers == ["A", "B"]
    assert view.skipped == []
    assert view.matrix["A"]["B"] == expected["A"]["B"]
    assert len(common_dates) == 59


def test_avg_correlation_excludes_diagonal() -> None:
    fixed_matrix = {
        "A": {"A": Decimal("1"), "B": Decimal("0.5"), "C": Decimal("0.5")},
        "B": {"A": Decimal("0.5"), "B": Decimal("1"), "C": Decimal("0.1")},
        "C": {"A": Decimal("0.5"), "B": Decimal("0.1"), "C": Decimal("1")},
    }
    with patch(
        "app.services.analytics_correlation.analytics.correlation_matrix",
        return_value=fixed_matrix,
    ):
        view = _view(
            [_buy("A"), _buy("B"), _buy("C")],
            {
                "A": _dated_closes(1, days=30),
                "B": _dated_closes(2, days=30),
                "C": _dated_closes(3, days=30),
            },
        )

    assert view.avg_correlation["A"] == Decimal("0.5")


def test_empty_universe_returns_empty_view() -> None:
    view = _view([], {})

    assert view.matrix == {}
    assert view.included_tickers == []
    assert view.skipped == []
    assert view.avg_correlation == {}
    assert view.clusters == []


def test_single_open_position_has_undefined_average_correlation() -> None:
    view = _view([_buy("A")], {"A": _dated_closes(1, days=30)})

    assert view.included_tickers == ["A"]
    assert view.matrix == {"A": {"A": Decimal("1")}}
    assert view.avg_correlation == {}


def test_diversification_bucket_thresholds() -> None:
    assert diversification_bucket(Decimal("0.19")) == ("high", "green")
    assert diversification_bucket(Decimal("0.2")) == ("moderate", "amber")
    assert diversification_bucket(Decimal("0.4")) == ("low", "amber")
    assert diversification_bucket(Decimal("0.6")) == ("very low", "red")
