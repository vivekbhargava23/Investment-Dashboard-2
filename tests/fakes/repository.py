from __future__ import annotations

from collections.abc import Sequence

from app.domain.models import Transaction
from app.ports.repository import TransactionNotFoundError


class FakeTransactionRepository:
    """In-memory TransactionRepository for tests."""

    def __init__(self, transactions: Sequence[Transaction] | None = None) -> None:
        self._transactions: list[Transaction] = list(transactions or [])

    def load_all(self) -> list[Transaction]:
        return list(self._transactions)

    def save_all(self, transactions: Sequence[Transaction]) -> None:
        self._transactions = list(transactions)

    def add(self, transaction: Transaction) -> None:
        self._transactions.append(transaction)

    def update(self, transaction: Transaction) -> None:
        for i, tx in enumerate(self._transactions):
            if tx.id == transaction.id:
                self._transactions[i] = transaction
                return
        raise TransactionNotFoundError(transaction.id)

    def delete(self, transaction_id: str) -> None:
        for i, tx in enumerate(self._transactions):
            if tx.id == transaction_id:
                del self._transactions[i]
                return
        raise TransactionNotFoundError(transaction_id)

    def get(self, transaction_id: str) -> Transaction:
        for tx in self._transactions:
            if tx.id == transaction_id:
                return tx
        raise TransactionNotFoundError(transaction_id)
