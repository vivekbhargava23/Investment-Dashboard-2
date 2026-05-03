from datetime import date
from decimal import Decimal

from app.domain.money import Currency, Money
from app.ui.format import format_date, format_eur, format_pct, format_shares, gain_class

EUR = Currency.EUR

def test_format_eur():
    assert format_eur(Money(amount=Decimal("25045.38"), currency=EUR)) == "€25.045,38"
    assert format_eur(Money(amount=Decimal("4003.60"), currency=EUR), signed=True) == "+€4.003,60"
    assert format_eur(Money(amount=Decimal("-150.00"), currency=EUR), signed=True) == "-€150,00"
    assert format_eur(Money(amount=Decimal("0"), currency=EUR)) == "€0,00"
    # Test rounding
    assert format_eur(
        Money(amount=Decimal("25045.385"), currency=EUR)
    ) == "€25.045,38" # quantize behavior

def test_format_pct():
    assert format_pct(Decimal("19.0")) == "19.0%"
    assert format_pct(Decimal("19.0"), signed=True) == "+19.0%"
    assert format_pct(Decimal("-21.8"), signed=True) == "-21.8%"
    # Test rounding
    assert format_pct(Decimal("19.05")) == "19.0%" # quantize behavior

def test_format_shares():
    assert format_shares(Decimal("12.5")) == "12,5000"
    assert format_shares(Decimal("120.0000")) == "120,0000"
    assert format_shares(Decimal("12.55555")) == "12,5556"

def test_format_date():
    assert format_date(date(2026, 5, 2)) == "2026-05-02"

def test_gain_class():
    assert gain_class(Decimal("100")) == "gain-positive"
    assert gain_class(Decimal("-100")) == "gain-negative"
    assert gain_class(Decimal("0")) == "gain-neutral"
