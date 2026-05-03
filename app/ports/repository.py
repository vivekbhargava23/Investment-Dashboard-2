from collections.abc import Sequence
from typing import Protocol

from app.domain.models import Transaction


class TransactionNotFoundError(Exception):
    """Raised when a transaction with a specific ID is not found in the repository."""

    def __init__(self, transaction_id: str):
        super().__init__(f"Transaction with id {transaction_id} not found")
        self.transaction_id = transaction_id


class RepositoryCorruptedError(Exception):
    """Raised when the repository storage is unreadable or malformed."""

    pass


class TransactionRepository(Protocol):
    """Abstract interface for persisting and retrieving transactions."""

    def load_all(self) -> list[Transaction]:
        """Returns all transactions, in stored order."""
        ...

    def save_all(self, transactions: Sequence[Transaction]) -> None:
        """Replaces the entire stored list atomically."""
        ...

    def add(self, transaction: Transaction) -> None:
        """Appends one transaction."""
        ...

    def update(self, transaction: Transaction) -> None:
        """
        Replaces an existing transaction by id.
        Raises TransactionNotFoundError if not present.
        """
        ...

    def delete(self, transaction_id: str) -> None:
        """Removes a transaction by id; raises TransactionNotFoundError if not present."""
        ...

    def get(self, transaction_id: str) -> Transaction:
        """Fetches one transaction by id; raises TransactionNotFoundError if not present."""
        ...
