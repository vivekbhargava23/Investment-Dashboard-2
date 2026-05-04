from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.adapters.repo_json import JsonTransactionRepository
from app.domain.fifo import SellExceedsOpenSharesError, compute_positions
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money


@pytest.fixture
def repo(tmp_path: Path) -> JsonTransactionRepository:
    json_path = tmp_path / "test_portfolio.json"
    return JsonTransactionRepository(json_path)

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

def test_add_buy_persists(repo: JsonTransactionRepository):
    tx = make_tx(TransactionType.BUY, "NVDA", "10", "2025-01-01")
    repo.add(tx)
    
    loaded = repo.load_all()
    assert len(loaded) == 1
    assert loaded[0].id == tx.id

def test_add_sell_exceeds_open_shares(repo: JsonTransactionRepository):
    tx_buy = make_tx(TransactionType.BUY, "NVDA", "5", "2025-01-01")
    repo.add(tx_buy)
    
    existing = repo.load_all()
    tx_sell = make_tx(TransactionType.SELL, "NVDA", "10", "2025-02-01")
    proposed = [*existing, tx_sell]
    
    with pytest.raises(SellExceedsOpenSharesError):
        compute_positions(proposed)

def test_add_valid_partial_sell(repo: JsonTransactionRepository):
    tx_buy = make_tx(TransactionType.BUY, "NVDA", "10", "2025-01-01")
    repo.add(tx_buy)
    
    existing = repo.load_all()
    tx_sell = make_tx(TransactionType.SELL, "NVDA", "4", "2025-02-01")
    proposed = [*existing, tx_sell]
    
    positions = compute_positions(proposed)
    assert positions["NVDA"].open_shares == Decimal("6")

def test_edit_buy_preserves_id(repo: JsonTransactionRepository):
    tx_buy = make_tx(TransactionType.BUY, "NVDA", "10", "2025-01-01")
    repo.add(tx_buy)
    
    loaded = repo.load_all()[0]
    edited = loaded.model_copy(update={"shares": Decimal("15")})
    repo.update(edited)
    
    reloaded = repo.load_all()[0]
    assert reloaded.id == tx_buy.id
    assert reloaded.shares == Decimal("15")

def test_edit_buy_breaks_fifo(repo: JsonTransactionRepository):
    tx_buy = make_tx(TransactionType.BUY, "NVDA", "10", "2025-01-01")
    tx_sell = make_tx(TransactionType.SELL, "NVDA", "8", "2025-02-01")
    repo.add(tx_buy)
    repo.add(tx_sell)
    
    existing = repo.load_all()
    # Edit the buy down to 5 shares
    edited_buy = existing[0].model_copy(update={"shares": Decimal("5")})
    
    proposed = [tx if tx.id != edited_buy.id else edited_buy for tx in existing]
    with pytest.raises(SellExceedsOpenSharesError):
        compute_positions(proposed)

def test_delete_transaction(repo: JsonTransactionRepository):
    tx1 = make_tx(TransactionType.BUY, "NVDA", "10", "2025-01-01")
    tx2 = make_tx(TransactionType.BUY, "AAPL", "5", "2025-01-02")
    tx3 = make_tx(TransactionType.BUY, "MSFT", "2", "2025-01-03")
    repo.add(tx1)
    repo.add(tx2)
    repo.add(tx3)
    
    repo.delete(tx2.id)
    loaded = repo.load_all()
    assert len(loaded) == 2
    assert loaded[0].id == tx1.id
    assert loaded[1].id == tx3.id

def test_delete_buy_breaks_fifo(repo: JsonTransactionRepository):
    tx_buy = make_tx(TransactionType.BUY, "NVDA", "10", "2025-01-01")
    tx_sell = make_tx(TransactionType.SELL, "NVDA", "4", "2025-02-01")
    repo.add(tx_buy)
    repo.add(tx_sell)
    
    existing = repo.load_all()
    transactions_without_buy = [tx for tx in existing if tx.id != tx_buy.id]
    
    with pytest.raises(SellExceedsOpenSharesError):
        compute_positions(transactions_without_buy)
