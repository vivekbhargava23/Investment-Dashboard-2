from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.domain.models import Transaction
from app.domain.tickers import UnsupportedTickerError, infer_currency_from_ticker
from app.ports.repository import (
    RepositoryCorruptedError,
    TransactionNotFoundError,
    TransactionRepository,
)

if TYPE_CHECKING:
    from app.ports.nav_repository import NavSnapshotRepository


class LegacyDataError(Exception):
    """
    Raised when portfolio.json contains manually-entered transactions whose ticker
    does not match their recorded currency (a pre-ADR-005 corruption).
    Broker-sourced rows (scalable_csv, switch) are exempt — they carry their own
    settlement currency and are never checked here.
    """

    def __init__(self, path: Path, count: int, first_offender: dict[str, object]) -> None:
        self.path = path
        self.count = count
        self.first_offender: dict[str, object] = first_offender
        self.offenders: list[dict[str, object]] = [first_offender]
        super().__init__(
            f"Found {count} manually-entered transaction(s) in {path} that fail the "
            f"ticker↔currency consistency check. First offender: {first_offender}."
        )


class JsonTransactionRepository(TransactionRepository):
    """
    JSON-based implementation of TransactionRepository.
    Stores transactions in a single JSON file.

    If nav_repo is provided, save_all calls nav_repo.clear() after every
    successful write so the NAV snapshot cache stays consistent with
    the transaction history (TICKET-013 decision #6).
    """

    SCHEMA_VERSION = 2

    def __init__(self, path: Path, nav_repo: NavSnapshotRepository | None = None) -> None:
        self.path = path
        self._nav_repo = nav_repo

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

        if data["version"] == 1:
            import logging

            from app.adapters.repo_json.migration import migrate_v1_to_v2

            result = migrate_v1_to_v2(self.path)
            logging.getLogger(__name__).info("Auto-migrated portfolio to v2: %s", result)
            # Reload the migrated file
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)

        if data["version"] != self.SCHEMA_VERSION:
            raise RepositoryCorruptedError(
                f"Unsupported schema version: {data['version']}"
            )

        if "transactions" not in data:
            raise RepositoryCorruptedError("Missing 'transactions' field")

        # Phase 1: detect legacy ticker↔currency mismatches before full construction.
        # Only manually-entered transactions are checked; broker rows (scalable_csv, switch)
        # carry their own settlement currency and must not be second-guessed via inference.
        offenders: list[dict[str, object]] = []
        for tx_data in data["transactions"]:
            if tx_data.get("source", "manual") != "manual":
                continue
            ticker = tx_data.get("ticker", "")
            currency_str = (tx_data.get("price_native") or {}).get("currency", "")
            if ticker and currency_str:
                try:
                    inferred = infer_currency_from_ticker(ticker)
                    if inferred.value != currency_str:
                        offenders.append(tx_data)
                except UnsupportedTickerError:
                    offenders.append(tx_data)

        if offenders:
            err = LegacyDataError(self.path, len(offenders), offenders[0])
            err.offenders = offenders
            raise err

        # Phase 2: full Pydantic construction.
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

        if self._nav_repo is not None:
            self._nav_repo.clear()

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
