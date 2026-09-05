from __future__ import annotations

from collections.abc import Sequence

from app.domain.csv_import import PlannedRow, RowStatus
from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction
from app.domain.tax.classification import InstrumentKind
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


class TickerAlreadyMappedError(Exception):
    """Raised when a ticker is already the feed of a different mapped ISIN.

    ADR-014 rule 4: two instruments must not merge into one FIFO position by
    accident. The caller may override deliberately with ``allow_shared_ticker``.
    """

    def __init__(self, ticker: str, other_isin: str) -> None:
        super().__init__(
            f"{ticker} is already the feed for {other_isin}"
        )
        self.ticker = ticker
        self.other_isin = other_isin


def mapped_owner_of_ticker(
    isin_doc: IsinMapDocument,
    ticker: str,
    exclude_isin: str,
) -> str | None:
    """Return the ISIN (other than ``exclude_isin``) that already feeds off ``ticker``."""
    for other_isin, mapping in isin_doc.entries.items():
        if other_isin == exclude_isin:
            continue
        if mapping.status == "mapped" and mapping.ticker == ticker:
            return other_isin
    return None


def change_feed(
    isin: str,
    ticker: str,
    kind: InstrumentKind,
    isin_doc: IsinMapDocument,
    tx_repo: TransactionRepository,
    *,
    allow_shared_ticker: bool = False,
    name: str | None = None,
) -> tuple[IsinMapDocument, int]:
    """Point ``isin`` at ``ticker`` and rewrite every transaction carrying that ISIN.

    Returns ``(new_doc, rewritten_count)``. The caller saves ``new_doc``.

    Write order is fixed (ADR-014 rule 9): transactions first, then the map. If the
    caller's map save fails, stored tickers are ahead of the map, which
    :func:`check_consistency` detects and :func:`repair` fixes idempotently.

    Raises :class:`TickerAlreadyMappedError` when another ``mapped`` ISIN already
    uses ``ticker`` and ``allow_shared_ticker`` is False.
    """
    if not allow_shared_ticker:
        other_isin = mapped_owner_of_ticker(isin_doc, ticker, isin)
        if other_isin is not None:
            raise TickerAlreadyMappedError(ticker, other_isin)

    existing = isin_doc.entries.get(isin)
    entry = IsinMapping(
        ticker=ticker,
        name=name or (existing.name if existing else isin),
        status="mapped",
        last_seen_in_csv=existing.last_seen_in_csv if existing else None,
        instrument_kind=kind,
    )
    new_entries = dict(isin_doc.entries)
    new_entries[isin] = entry
    new_doc = IsinMapDocument(version=isin_doc.version, entries=new_entries)

    rewritten = rewrite_ticker_for_isin(tx_repo, isin, ticker)
    return new_doc, rewritten


def check_consistency(
    isin_doc: IsinMapDocument,
    txs: Sequence[Transaction],
) -> list[tuple[str, str, str]]:
    """Return ``(isin, map_ticker, stored_ticker)`` for every mismatch.

    A mismatch means the mapping write path was bypassed (or a map save failed
    after the transactions were rewritten). One entry per distinct stored ticker
    per ISIN, in map order.
    """
    mismatches: list[tuple[str, str, str]] = []
    for isin, mapping in isin_doc.entries.items():
        if mapping.status != "mapped" or mapping.ticker is None:
            continue
        stored = {tx.ticker for tx in txs if tx.isin == isin}
        for stored_ticker in sorted(stored - {mapping.ticker}):
            mismatches.append((isin, mapping.ticker, stored_ticker))
    return mismatches


def repair(
    isin_doc: IsinMapDocument,
    tx_repo: TransactionRepository,
) -> int:
    """Re-run the rewrite for every mapped ISIN. Returns the number of rows changed.

    Idempotent: a second call on a consistent book returns 0.
    """
    txs = tx_repo.load_all()
    updated: list[Transaction] = []
    changed = 0
    targets = {
        isin: mapping.ticker
        for isin, mapping in isin_doc.entries.items()
        if mapping.status == "mapped" and mapping.ticker is not None
    }
    for tx in txs:
        target = targets.get(tx.isin) if tx.isin else None
        if target is not None and tx.ticker != target:
            updated.append(tx.model_copy(update={"ticker": target}))
            changed += 1
        else:
            updated.append(tx)
    if changed:
        tx_repo.save_all(updated)
    return changed


def record_seen_isins(
    plan_rows: Sequence[PlannedRow],
    isin_doc: IsinMapDocument,
) -> IsinMapDocument | None:
    """Give every ISIN in the file a map entry, and stamp when it was last seen.

    Returns a new document, or None when nothing changed (so the caller can skip
    the write). An ISIN the map has never heard of becomes an ``unmapped`` entry
    carrying the broker's name for it: without that entry the holding has no name
    anywhere in the app — it trades under its ISIN as a placeholder ticker — and
    the Sync tab cannot offer it for mapping at all.
    """
    latest_row: dict[str, PlannedRow] = {}
    for row in plan_rows:
        if not row.isin or row.status == RowStatus.CANCELLED_OR_EXPIRED:
            continue
        seen = latest_row.get(row.isin)
        if seen is None or (row.trade_date, row.row_number) > (seen.trade_date, seen.row_number):
            latest_row[row.isin] = row

    entries = dict(isin_doc.entries)
    changed = False

    for isin, row in latest_row.items():
        existing = entries.get(isin)
        if existing is None:
            entries[isin] = IsinMapping(
                ticker=None,
                name=row.description or isin,
                status="unmapped",
                last_seen_in_csv=row.trade_date,
                instrument_kind=None,
            )
            changed = True
        elif existing.last_seen_in_csv != row.trade_date:
            entries[isin] = existing.model_copy(
                update={"last_seen_in_csv": row.trade_date}
            )
            changed = True

    if not changed:
        return None
    return IsinMapDocument(version=isin_doc.version, entries=entries)
