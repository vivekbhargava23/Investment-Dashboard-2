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


def test_ticker_currency_valid_nvda_usd():
    t = Transaction(
        type=TransactionType.BUY,
        ticker="NVDA",
        trade_date=date(2024, 1, 1),
        shares=Decimal("1"),
        price_native=Money(amount=Decimal("100"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.92"),
    )
    assert t.ticker == "NVDA"


def test_ticker_currency_eur_bypass_allows_nvda_eur_at_face_value():
    """EUR price + fx_rate_eur=1 bypasses native-currency check (Scalable CSV import path)."""
    t = Transaction(
        type=TransactionType.BUY,
        ticker="NVDA",
        trade_date=date(2024, 1, 1),
        shares=Decimal("1"),
        price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )
    assert t.ticker == "NVDA"
    assert t.price_native.currency == Currency.EUR


def test_ticker_currency_nvda_eur_with_nonunit_fx_still_raises():
    """EUR price with non-1 fx_rate for a USD ticker is inconsistent and must raise."""
    with pytest.raises(ValidationError, match="NVDA trades in USD"):
        Transaction(
            type=TransactionType.BUY,
            ticker="NVDA",
            trade_date=date(2024, 1, 1),
            shares=Decimal("1"),
            price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
            fx_rate_eur=Decimal("0.92"),
        )


def test_ticker_currency_valid_5631t_jpy():
    t = Transaction(
        type=TransactionType.BUY,
        ticker="5631.T",
        trade_date=date(2025, 11, 10),
        shares=Decimal("1"),
        price_native=Money(amount=Decimal("9000"), currency=Currency.JPY),
        fx_rate_eur=Decimal("0.0061"),
    )
    assert t.ticker == "5631.T"


def test_ticker_currency_invalid_5631t_usd_regression():
    """Regression test for the original JPY-as-USD bug (TICKET-008c)."""
    with pytest.raises(ValidationError, match="5631.T trades in JPY"):
        Transaction(
            type=TransactionType.BUY,
            ticker="5631.T",
            trade_date=date(2025, 11, 10),
            shares=Decimal("1"),
            price_native=Money(amount=Decimal("4200"), currency=Currency.USD),
            fx_rate_eur=Decimal("0.93"),
        )


def test_ticker_currency_valid_rhm_de_eur():
    t = Transaction(
        type=TransactionType.BUY,
        ticker="RHM.DE",
        trade_date=date(2026, 3, 27),
        shares=Decimal("1"),
        price_native=Money(amount=Decimal("1452"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )
    assert t.ticker == "RHM.DE"


def test_ticker_currency_invalid_rhm_de_usd():
    with pytest.raises(ValidationError, match="RHM.DE trades in EUR"):
        Transaction(
            type=TransactionType.BUY,
            ticker="RHM.DE",
            trade_date=date(2026, 3, 27),
            shares=Decimal("1"),
            price_native=Money(amount=Decimal("1452"), currency=Currency.USD),
            fx_rate_eur=Decimal("0.9"),
        )


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
