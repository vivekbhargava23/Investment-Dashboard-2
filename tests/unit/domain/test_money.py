from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from app.domain.money import Currency, CurrencyMismatchError, Money


def test_money_creation_and_normalization():
    m = Money(amount=Decimal("100.12345"), currency=Currency.EUR)
    assert m.amount == Decimal("100.1235")  # Rounded HALF_UP to 4 dp
    assert m.currency == Currency.EUR


def test_money_zero():
    m = Money.zero(Currency.USD)
    assert m.amount == Decimal("0")
    assert m.currency == Currency.USD


def test_money_addition():
    m1 = Money(amount=Decimal("100"), currency=Currency.EUR)
    m2 = Money(amount=Decimal("50.5"), currency=Currency.EUR)
    assert m1 + m2 == Money(amount=Decimal("150.5"), currency=Currency.EUR)


def test_money_subtraction():
    m1 = Money(amount=Decimal("100"), currency=Currency.EUR)
    m2 = Money(amount=Decimal("50.5"), currency=Currency.EUR)
    assert m1 - m2 == Money(amount=Decimal("49.5"), currency=Currency.EUR)


def test_money_currency_mismatch():
    m1 = Money(amount=Decimal("100"), currency=Currency.EUR)
    m2 = Money(amount=Decimal("100"), currency=Currency.USD)

    with pytest.raises(CurrencyMismatchError):
        _ = m1 + m2
    with pytest.raises(CurrencyMismatchError):
        _ = m1 - m2
    with pytest.raises(CurrencyMismatchError):
        _ = m1 < m2


def test_money_multiplication():
    m = Money(amount=Decimal("100"), currency=Currency.EUR)
    assert m * 2 == Money(amount=Decimal("200"), currency=Currency.EUR)
    assert m * Decimal("1.5") == Money(amount=Decimal("150"), currency=Currency.EUR)
    assert 2 * m == Money(amount=Decimal("200"), currency=Currency.EUR)


def test_money_division():
    m1 = Money(amount=Decimal("100"), currency=Currency.EUR)
    m2 = Money(amount=Decimal("50"), currency=Currency.EUR)

    # Money / Money -> Decimal
    assert m1 / m2 == Decimal("2")

    # Money / Decimal -> Money
    assert m1 / 2 == Money(amount=Decimal("50"), currency=Currency.EUR)
    assert m1 / Decimal("0.5") == Money(amount=Decimal("200"), currency=Currency.EUR)


def test_money_negation():
    m = Money(amount=Decimal("100"), currency=Currency.EUR)
    assert -m == Money(amount=Decimal("-100"), currency=Currency.EUR)


def test_money_comparison():
    m1 = Money(amount=Decimal("100"), currency=Currency.EUR)
    m2 = Money(amount=Decimal("200"), currency=Currency.EUR)
    m3 = Money(amount=Decimal("100"), currency=Currency.EUR)

    assert m1 < m2
    assert m1 <= m2
    assert m1 <= m3
    assert m2 > m1
    assert m2 >= m1
    assert m1 >= m3
    assert m1 == m3
    assert m1 != m2
    assert m1 != "not money"


def test_money_frozen():
    m = Money(amount=Decimal("100"), currency=Currency.EUR)
    with pytest.raises(ValidationError):
        m.amount = Decimal("200")


def test_money_string_formatting():
    assert str(Money(amount=Decimal("1234.5"), currency=Currency.EUR)) == "€1,234.50"
    assert str(Money(amount=Decimal("1234.5"), currency=Currency.USD)) == "$1,234.50"
    assert str(Money(amount=Decimal("0.0001"), currency=Currency.EUR)) == "€0.00"
    assert (
        str(Money(amount=Decimal("1000000.12"), currency=Currency.USD)) == "$1,000,000.12"
    )


def test_jpy_construction_and_formatting():
    m = Money(amount=Decimal("9049"), currency=Currency.JPY)
    assert m.currency == Currency.JPY
    assert m.amount == Decimal("9049.0000")
    assert str(m) == "¥9,049"


def test_jpy_large_amount_formatting():
    m = Money(amount=Decimal("1234567"), currency=Currency.JPY)
    assert str(m) == "¥1,234,567"


def test_jpy_zero():
    m = Money.zero(Currency.JPY)
    assert m.amount == Decimal("0")
    assert m.currency == Currency.JPY
    assert str(m) == "¥0"


def test_jpy_usd_mismatch_raises():
    m1 = Money(amount=Decimal("9000"), currency=Currency.JPY)
    m2 = Money(amount=Decimal("100"), currency=Currency.USD)
    with pytest.raises(CurrencyMismatchError):
        _ = m1 + m2


def test_jpy_eur_mismatch_raises():
    m1 = Money(amount=Decimal("9000"), currency=Currency.JPY)
    m2 = Money(amount=Decimal("55"), currency=Currency.EUR)
    with pytest.raises(CurrencyMismatchError):
        _ = m1 + m2


# Property-based tests
@given(
    a_amount=st.decimals(
        min_value=-10**9, max_value=10**9, places=4, allow_nan=False, allow_infinity=False
    ),
    b_amount=st.decimals(
        min_value=-10**9, max_value=10**9, places=4, allow_nan=False, allow_infinity=False
    ),
    currency=st.sampled_from(Currency),
)
def test_money_addition_subtraction_property(a_amount, b_amount, currency):
    a = Money(amount=a_amount, currency=currency)
    b = Money(amount=b_amount, currency=currency)

    # a + b - b == a (within normalization)
    result = (a + b) - b
    assert result.amount == a.amount
