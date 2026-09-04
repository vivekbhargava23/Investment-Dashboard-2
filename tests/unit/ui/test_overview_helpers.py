from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.domain.models import Currency, Money, Transaction
from app.ui.cache_keys import transactions_signature as _transactions_signature


def test_transactions_signature_deterministic():
    tx1 = Transaction(
        id=str(uuid4()), ticker="AAPL", type="buy", trade_date=date(2024, 1, 1),
        shares=Decimal("10"), price_native=Money(amount=Decimal("150"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9")
    )
    tx2 = Transaction(
        id=str(uuid4()), ticker="MSFT", type="buy", trade_date=date(2024, 1, 2),
        shares=Decimal("5"), price_native=Money(amount=Decimal("200"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9")
    )
    
    sig1 = _transactions_signature([tx1, tx2])
    sig2 = _transactions_signature([tx1, tx2])
    assert sig1 == sig2
    
    sig3 = _transactions_signature([tx1])
    assert sig1 != sig3

def test_transactions_signature_empty():
    assert _transactions_signature([]) == "empty"

def test_transactions_signature_order_insensitive():
    tx1 = Transaction(
        id=str(uuid4()), ticker="AAPL", type="buy", trade_date=date(2024, 1, 1),
        shares=Decimal("10"), price_native=Money(amount=Decimal("150"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9")
    )
    tx2 = Transaction(
        id=str(uuid4()), ticker="MSFT", type="buy", trade_date=date(2024, 1, 2),
        shares=Decimal("5"), price_native=Money(amount=Decimal("200"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9")
    )
    
    sig1 = _transactions_signature([tx1, tx2])
    sig2 = _transactions_signature([tx2, tx1])
    assert sig1 == sig2


def test_transactions_signature_changes_when_only_a_ticker_is_rewritten():
    """ADR-014: a mapping change rewrites tickers in place, so the key must move."""
    tx = Transaction(
        id=str(uuid4()), ticker="DE000A0F5UF5", type="buy", trade_date=date(2024, 1, 1),
        shares=Decimal("10"), price_native=Money(amount=Decimal("150"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"), isin="DE000A0F5UF5", source="scalable_csv",
    )
    remapped = tx.model_copy(update={"ticker": "EXS1.DE"})

    assert _transactions_signature([tx]) != _transactions_signature([remapped])
