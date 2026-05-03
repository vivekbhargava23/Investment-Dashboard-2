import json
import os
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from app.domain.models import Transaction
from app.ports.repository import (
    RepositoryCorruptedError,
    TransactionNotFoundError,
    TransactionRepository,
)


class JsonTransactionRepository(TransactionRepository):
    """
    JSON-based implementation of TransactionRepository.
    Stores transactions in a single JSON file.
    """

    SCHEMA_VERSION = 1

    def __init__(self, path: Path):
        self.path = path

    def load_all(self) -> list[Transaction]:
        if not self.path.exists():
            return []

        if self.path.stat().st_size == 0:
            raise RepositoryCorruptedError("File is empty")

        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise RepositoryCorruptedError(f"Failed to read JSON: {e}") from e

        if "version" not in data:
            raise RepositoryCorruptedError("Missing 'version' field")

        if data["version"] != self.SCHEMA_VERSION:
            raise RepositoryCorruptedError(
                f"Unsupported schema version: {data['version']}"
            )

        if "transactions" not in data:
            raise RepositoryCorruptedError("Missing 'transactions' field")

        transactions = []
        for tx_data in data["transactions"]:
            try:
                transactions.append(Transaction.model_validate(tx_data))
            except ValidationError as e:
                raise RepositoryCorruptedError(
                    f"Invalid transaction data: {e}"
                ) from e

        return transactions

    def save_all(self, transactions: Sequence[Transaction]) -> None:
        data = {
            "version": self.SCHEMA_VERSION,
            "transactions": [tx.model_dump(mode="json") for tx in transactions],
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")

        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

    def add(self, transaction: Transaction) -> None:
        txs = self.load_all()
        if any(tx.id == transaction.id for tx in txs):
            raise ValueError(f"Transaction with id {transaction.id} already exists")
        txs.append(transaction)
        self.save_all(txs)

    def update(self, transaction: Transaction) -> None:
        txs = self.load_all()
        for i, tx in enumerate(txs):
            if tx.id == transaction.id:
                txs[i] = transaction
                self.save_all(txs)
                return
        raise TransactionNotFoundError(transaction.id)

    def delete(self, transaction_id: str) -> None:
        txs = self.load_all()
        new_txs = [tx for tx in txs if tx.id != transaction_id]
        if len(new_txs) == len(txs):
            raise TransactionNotFoundError(transaction_id)
        self.save_all(new_txs)

    def get(self, transaction_id: str) -> Transaction:
        txs = self.load_all()
        for tx in txs:
            if tx.id == transaction_id:
                return tx
        raise TransactionNotFoundError(transaction_id)
