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


def delete_transactions_for_isin(
    tx_repo: TransactionRepository,
    isin: str,
) -> int:
    """Delete every transaction matching ``isin``.

    Returns the count of transactions removed. Zero if none match (and the
    repository is left untouched). FIFO replay happens on the next read per the
    save_all/replay invariant, so the caller need not trigger recompute.
    """
    txs = tx_repo.load_all()
    remaining = [tx for tx in txs if tx.isin != isin]
    removed = len(txs) - len(remaining)
    if removed:
        tx_repo.save_all(remaining)
    return removed
