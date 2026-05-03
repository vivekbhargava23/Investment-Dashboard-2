from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money


def test_valid_eur_transaction():
    t = Transaction(
        type=TransactionType.BUY,
        ticker="SAP.DE",
        trade_date=date(2024, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("150"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )
    assert t.ticker == "SAP.DE"
    assert t.cost_native == Money(amount=Decimal("1500"), currency=Currency.EUR)
    assert t.cost_eur == Money(amount=Decimal("1500"), currency=Currency.EUR)
    assert t.id is not None


def test_valid_usd_transaction():
    t = Transaction(
        type=TransactionType.BUY,
        ticker="AAPL",
        trade_date=date(2024, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("180"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.92"),
    )
    assert t.cost_native == Money(amount=Decimal("1800"), currency=Currency.USD)
    # 1800 * 0.92 = 1656
    assert t.cost_eur == Money(amount=Decimal("1656"), currency=Currency.EUR)


def test_eur_transaction_invalid_fx_rate():
    with pytest.raises(ValidationError, match="fx_rate_eur must be 1 for EUR"):
        Transaction(
            type=TransactionType.BUY,
            ticker="SAP.DE",
            trade_date=date(2024, 1, 1),
            shares=Decimal("10"),
            price_native=Money(amount=Decimal("150"), currency=Currency.EUR),
            fx_rate_eur=Decimal("1.0001"),
        )


def test_invalid_ticker_lowercase():
    with pytest.raises(ValidationError, match="Ticker must be uppercase"):
        Transaction(
            type=TransactionType.BUY,
            ticker="sap.de",
            trade_date=date(2024, 1, 1),
            shares=Decimal("10"),
            price_native=Money(amount=Decimal("150"), currency=Currency.EUR),
            fx_rate_eur=Decimal("1"),
        )


def test_invalid_shares_non_positive():
    with pytest.raises(ValidationError, match="Shares must be positive"):
        Transaction(
            type=TransactionType.BUY,
            ticker="SAP.DE",
            trade_date=date(2024, 1, 1),
            shares=Decimal("0"),
            price_native=Money(amount=Decimal("150"), currency=Currency.EUR),
            fx_rate_eur=Decimal("1"),
        )
    with pytest.raises(ValidationError, match="Shares must be positive"):
        Transaction(
            type=TransactionType.BUY,
            ticker="SAP.DE",
            trade_date=date(2024, 1, 1),
            shares=Decimal("-1"),
            price_native=Money(amount=Decimal("150"), currency=Currency.EUR),
            fx_rate_eur=Decimal("1"),
        )


def test_invalid_fees_currency_mismatch():
    with pytest.raises(ValidationError, match="Fees must be in the same currency"):
        Transaction(
            type=TransactionType.BUY,
            ticker="AAPL",
            trade_date=date(2024, 1, 1),
            shares=Decimal("10"),
            price_native=Money(amount=Decimal("180"), currency=Currency.USD),
            fees_native=Money(amount=Decimal("1"), currency=Currency.EUR),
            fx_rate_eur=Decimal("0.92"),
        )


def test_cost_calculation_with_fees():
    t = Transaction(
        type=TransactionType.BUY,
        ticker="AAPL",
        trade_date=date(2024, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("180"), currency=Currency.USD),
        fees_native=Money(amount=Decimal("5"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.92"),
    )
    # (180 * 10) + 5 = 1805
    assert t.cost_native == Money(amount=Decimal("1805"), currency=Currency.USD)
    # 1805 * 0.92 = 1660.6
    assert t.cost_eur == Money(amount=Decimal("1660.6"), currency=Currency.EUR)


def test_transaction_frozen():
    t = Transaction(
        type=TransactionType.BUY,
        ticker="SAP.DE",
        trade_date=date(2024, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("150"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )
    with pytest.raises(ValidationError):
        t.shares = Decimal("20")


def test_transaction_id_unique():
    t1 = Transaction(
        type=TransactionType.BUY,
        ticker="SAP.DE",
        trade_date=date(2024, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("150"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )
    t2 = Transaction(
        type=TransactionType.BUY,
        ticker="SAP.DE",
        trade_date=date(2024, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("150"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )
    assert t1.id != t2.id
