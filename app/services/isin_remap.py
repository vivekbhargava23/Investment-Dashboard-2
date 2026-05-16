from __future__ import annotations

from app.ports.repository import TransactionRepository


def rewrite_ticker_for_isin(
    tx_repo: TransactionRepository,
    isin: str,
    new_ticker: str,
) -> int:
    """Rewrite the ticker field on every transaction matching ``isin``.

    Returns the count of transactions rewritten. Zero if none match.
    """
    txs = tx_repo.load_all()
    affected = [tx for tx in txs if tx.isin == isin]
    if not affected:
        return 0
    updated = [
        tx.model_copy(update={"ticker": new_ticker}) if tx.isin == isin else tx
        for tx in txs
    ]
    tx_repo.save_all(updated)
    return len(affected)


def count_transactions_for_isin(
    tx_repo: TransactionRepository,
    isin: str,
) -> int:
    """Count transactions referencing ``isin``. Used to block deletes."""
    return sum(1 for tx in tx_repo.load_all() if tx.isin == isin)
