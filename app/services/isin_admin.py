"""Edits to the ISIN map that are not a feed change.

`isin_remap.change_feed` owns the one write that also rewrites transactions
(ADR-014 rule 2). Everything else an instrument card can do to the map — stop
asking for a feed, set the tax kind — is a plain document transform and lives
here, so both the Sync page and the sync service can perform it without either
importing the other.

Every function returns a new document; saving is the caller's job, because a
write made while a file is open has to be logged into the sync session first.
"""
from __future__ import annotations

from decimal import Decimal

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import TransactionType
from app.domain.tax.classification import InstrumentKind
from app.ports.repository import TransactionRepository


def apply_ignore(doc: IsinMapDocument, isin: str, name: str) -> IsinMapDocument:
    """Mark ``isin`` as wanting no price feed — "value it at its last trade price".

    Stored as ``ignored``; the ticker, if any, is dropped, because a holding that
    keeps a feed is not being valued at its last trade. The tax kind is kept: it
    is a fact about the instrument, not about its feed.
    """
    existing = doc.entries.get(isin)
    entry = IsinMapping(
        ticker=None,
        name=existing.name if existing else (name or isin),
        status="ignored",
        last_seen_in_csv=existing.last_seen_in_csv if existing else None,
        instrument_kind=existing.instrument_kind if existing else None,
    )
    return IsinMapDocument(version=doc.version, entries={**doc.entries, isin: entry})


def apply_kind(
    doc: IsinMapDocument,
    isin: str,
    kind: InstrumentKind,
    *,
    name: str = "",
) -> IsinMapDocument:
    """Set only the tax kind. Ticker and status are untouched.

    A holding with no feed still has a tax kind — that is the whole point of
    separating the two decisions — so an ISIN the map has never seen gets an
    ``unmapped`` entry rather than a KeyError.
    """
    existing = doc.entries.get(isin)
    if existing is None:
        entry = IsinMapping(
            ticker=None,
            name=name or isin,
            status="unmapped",
            last_seen_in_csv=None,
            instrument_kind=kind,
        )
    else:
        entry = existing.model_copy(update={"instrument_kind": kind})
    return IsinMapDocument(version=doc.version, entries={**doc.entries, isin: entry})


def open_shares_for_isin(tx_repo: TransactionRepository, isin: str) -> Decimal:
    """Shares of ``isin`` still held: buys minus sells over the book.

    Net shares, not FIFO lots — the card only needs to say "26 shares open" or
    "closed", and a write-off needs to know how much there is left to write off.
    """
    total = Decimal("0")
    for tx in tx_repo.load_all():
        if tx.isin != isin:
            continue
        if tx.type == TransactionType.BUY:
            total += tx.shares
        else:
            total -= tx.shares
    return total
