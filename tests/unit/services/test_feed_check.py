from datetime import date
from decimal import Decimal

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.services.feed_check import check_feeds
from tests.fakes.fx_feed import FakeFxProvider
from tests.fakes.price_feed import FakePriceProvider

_ISIN = "US67066G1040"


def _tx(
    trade_date: date,
    price_eur: str,
    *,
    tx_id: str | None = None,
    isin: str = _ISIN,
    source: str = "scalable_csv",
) -> Transaction:
    return Transaction(
        id=tx_id or trade_date.isoformat(),
        type=TransactionType.BUY,
        ticker="NVDA",
        trade_date=trade_date,
        shares=Decimal("1"),
        price_native=Money(amount=Decimal(price_eur), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
        isin=isin,
        csv_reference=f"REF-{tx_id or trade_date.isoformat()}",
        source=source,  # type: ignore[arg-type]
    )


def _mapped_doc(ticker: str = "NVDA") -> IsinMapDocument:
    return IsinMapDocument(
        entries={
            _ISIN: IsinMapping(ticker=ticker, name="NVIDIA", status="mapped")
        }
    )


def test_eur_close_is_compared_directly() -> None:
    on_date = date(2026, 8, 14)
    result = check_feeds(
        [_tx(on_date, "101")],
        _mapped_doc(),
        FakePriceProvider(
            historical_prices={
                ("NVDA", on_date): Money(amount=Decimal("100"), currency=Currency.EUR)
            }
        ),
        FakeFxProvider(),
    )[_ISIN]

    assert result.status == "ok"
    assert result.compared == 1
    assert result.avg_close_eur == Decimal("100")


def test_usd_close_is_converted_with_historical_fx() -> None:
    on_date = date(2026, 8, 14)
    result = check_feeds(
        [_tx(on_date, "90")],
        _mapped_doc(),
        FakePriceProvider(
            historical_prices={
                ("NVDA", on_date): Money(amount=Decimal("100"), currency=Currency.USD)
            }
        ),
        FakeFxProvider(
            historical_rates={(Currency.USD, Currency.EUR, on_date): Decimal("0.90")}
        ),
    )[_ISIN]

    assert result.status == "ok"
    assert result.avg_close_eur == Decimal("90")


def test_unavailable_trade_is_skipped_but_other_two_are_compared() -> None:
    dates = [date(2026, 6, day) for day in (1, 2, 3)]
    prices = {
        ("NVDA", dates[0]): Money(amount=Decimal("100"), currency=Currency.EUR),
        ("NVDA", dates[2]): Money(amount=Decimal("100"), currency=Currency.EUR),
    }

    result = check_feeds(
        [_tx(on_date, "100") for on_date in dates],
        _mapped_doc(),
        FakePriceProvider(historical_prices=prices),
        FakeFxProvider(),
    )[_ISIN]

    assert result.status == "ok"
    assert result.compared == 2


def test_all_unavailable_trades_produce_no_feed() -> None:
    result = check_feeds(
        [_tx(date(2026, 6, 1), "100")],
        _mapped_doc(),
        FakePriceProvider(),
        FakeFxProvider(),
    )[_ISIN]

    assert result.status == "no_feed"
    assert result.compared == 0


def test_unmapped_isin_is_unchecked_without_calling_feeds() -> None:
    doc = IsinMapDocument(
        entries={
            _ISIN: IsinMapping(ticker=None, name="NVIDIA", status="unmapped")
        }
    )
    result = check_feeds(
        [_tx(date(2026, 6, 1), "100")],
        doc,
        FakePriceProvider(),
        FakeFxProvider(),
    )[_ISIN]

    assert result.status == "unchecked"
    assert result.compared == 0


def test_only_last_three_trades_are_checked_by_date_then_id() -> None:
    dates = [date(2026, month, 1) for month in (1, 2, 3, 4)]
    transactions = [_tx(on_date, "100") for on_date in dates]
    prices = {
        ("NVDA", on_date): Money(amount=Decimal("100"), currency=Currency.EUR)
        for on_date in dates[1:]
    }

    result = check_feeds(
        transactions,
        _mapped_doc(),
        FakePriceProvider(historical_prices=prices),
        FakeFxProvider(),
    )[_ISIN]

    assert result.status == "ok"
    assert result.compared == 3
