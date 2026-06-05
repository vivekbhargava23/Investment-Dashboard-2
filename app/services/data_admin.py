"""Destructive book-of-record admin operations (erase all / erase scoped).

Pure functions over the transaction repository port: ports in, count out. The UI
layer (Manage Portfolio "Danger zone") owns confirmation, backups, and clearing
the ISIN map; this module only mutates the transaction store.
"""
from __future__ import annotations

from datetime import date
from typing import Final

from app.domain.models import Transaction
from app.ports.repository import TransactionRepository


class _Unset:
    """Sentinel marking 'do not filter on this field'.

    Distinct from ``None`` so a caller can filter for transactions whose source
    is explicitly ``None`` without it being confused with 'no source filter'.
    """


UNSET: Final = _Unset()

# A source filter is a concrete source value, an explicit None, or UNSET
# ("don't filter by source").
SourceFilter = str | None | _Unset


def erase_all_transactions(tx_repo: TransactionRepository) -> int:
    """Delete every transaction. Returns the number removed.

    Leaves the repository untouched (no write) when the book is already empty.
    """
    count = len(tx_repo.load_all())
    if count:
        tx_repo.save_all([])
    return count


def _matches(
    tx: Transaction,
    *,
    source: SourceFilter,
    date_from: date | None,
    date_to: date | None,
) -> bool:
    if not isinstance(source, _Unset) and tx.source != source:
        return False
    if date_from is not None and tx.trade_date < date_from:
        return False
    if date_to is not None and tx.trade_date > date_to:
        return False
    return True


def count_transactions(
    tx_repo: TransactionRepository,
    *,
    source: SourceFilter = UNSET,
    date_from: date | None = None,
    date_to: date | None = None,
) -> int:
    """Count transactions a scoped erase with the same filter would remove.

    Read-only mirror of :func:`erase_transactions` for the UI's live "would
    delete N" preview, so preview and action can never disagree. An empty
    selection counts 0.
    """
    if isinstance(source, _Unset) and date_from is None and date_to is None:
        return 0
    return sum(
        1
        for tx in tx_repo.load_all()
        if _matches(tx, source=source, date_from=date_from, date_to=date_to)
    )


def erase_transactions(
    tx_repo: TransactionRepository,
    *,
    source: SourceFilter = UNSET,
    date_from: date | None = None,
    date_to: date | None = None,
) -> int:
    """Delete transactions matching the given filter; return the count removed.

    A transaction matches when every supplied criterion matches: its ``source``
    equals ``source`` (unless ``source`` is :data:`UNSET`), its ``trade_date`` is
    on or after ``date_from`` (when given), and on or before ``date_to`` (when
    given).

    An empty selection — no source filter and no date bounds — deletes nothing
    and returns 0. Full-book wipes go through :func:`erase_all_transactions`, so
    the scoped path can never become an accidental full erase. The repository is
    likewise left untouched when nothing matches.
    """
    if isinstance(source, _Unset) and date_from is None and date_to is None:
        return 0

    txs = tx_repo.load_all()
    remaining = [
        tx
        for tx in txs
        if not _matches(tx, source=source, date_from=date_from, date_to=date_to)
    ]
    removed = len(txs) - len(remaining)
    if removed:
        tx_repo.save_all(remaining)
    return removed
