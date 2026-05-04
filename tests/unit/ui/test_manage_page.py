from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.ui.pages.manage import (
    _filter_by_ticker_substring,
    _propose_transactions_for_edit,
    _propose_transactions_for_validation,
)


def make_tx(tx_type: TransactionType, ticker: str, shares: str, date_str: str) -> Transaction:
    return Transaction(
        id=str(uuid4()),
        type=tx_type,
        ticker=ticker,
        trade_date=date.fromisoformat(date_str),
        shares=Decimal(shares),
        price_native=Money(amount=Decimal("100.0"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9"),
    )

def test_propose_transactions_for_validation():
    existing = [make_tx(TransactionType.BUY, "NVDA", "10", "2025-01-01")]
    new_tx = make_tx(TransactionType.SELL, "NVDA", "5", "2025-02-01")
    
    proposed = _propose_transactions_for_validation(existing, new_tx)
    assert len(proposed) == 2
    assert proposed[0].id == existing[0].id
    assert proposed[1].id == new_tx.id

def test_propose_transactions_for_edit():
    tx1 = make_tx(TransactionType.BUY, "NVDA", "10", "2025-01-01")
    tx2 = make_tx(TransactionType.BUY, "AAPL", "5", "2025-01-02")
    existing = [tx1, tx2]
    
    edited_tx1 = tx1.model_copy(update={"shares": Decimal("15")})
    
    proposed = _propose_transactions_for_edit(existing, edited_tx1)
    assert len(proposed) == 2
    assert proposed[0].id == tx1.id
    assert proposed[0].shares == Decimal("15")
    assert proposed[1].id == tx2.id

def test_filter_by_ticker_substring():
    tx1 = make_tx(TransactionType.BUY, "NVDA", "10", "2025-01-01")
    tx2 = make_tx(TransactionType.BUY, "AAPL", "5", "2025-01-02")
    tx3 = make_tx(TransactionType.BUY, "MSFT", "2", "2025-01-03")
    transactions = [tx1, tx2, tx3]
    
    assert len(_filter_by_ticker_substring(transactions, "nvda")) == 1
    assert len(_filter_by_ticker_substring(transactions, "NV")) == 1
    assert len(_filter_by_ticker_substring(transactions, "P")) == 1 # AAPL
    assert len(_filter_by_ticker_substring(transactions, "")) == 3
