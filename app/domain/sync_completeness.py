"""Decide whether an uploaded Scalable export covers the whole book.

A partial file still imports its new rows, but reconciliation and the feed check
are meaningless against it — the missing history would read as "shares differ".
The three rules are fixed by `docs/DESIGN/SYNC-TAB.md` and are not re-litigated
here.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from pydantic import BaseModel, ConfigDict

from app.domain.csv_import import PlannedRow, RowStatus
from app.domain.models import Transaction

_SCALABLE_SOURCE = "scalable_csv"


class CompletenessResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    partial: bool
    reason: str | None
    file_start: date | None
    book_start: date | None


def _file_start(rows: Sequence[PlannedRow]) -> date | None:
    dates = [
        row.trade_date
        for row in rows
        if row.status != RowStatus.CANCELLED_OR_EXPIRED
    ]
    return min(dates) if dates else None


def _book_start(book: Sequence[Transaction]) -> date | None:
    dates = [tx.trade_date for tx in book if tx.source == _SCALABLE_SOURCE]
    return min(dates) if dates else None


def check_completeness(
    rows: Sequence[PlannedRow],
    book: Sequence[Transaction],
    earliest_logged_file_start: date | None = None,
) -> CompletenessResult:
    """Return whether ``rows`` looks like a partial export of the book.

    A file is partial if it starts after the earliest Scalable trade in the book,
    after the earliest ``file_start`` any previous sync recorded, or if a CSV
    reference already in the book is absent from the file. On the first-ever sync
    (no Scalable rows in the book, nothing logged) nothing can be checked, so the
    file is never partial — its ``file_start`` is recorded for next time.
    """
    file_start = _file_start(rows)
    book_start = _book_start(book)

    if file_start is None:
        return CompletenessResult(
            partial=False, reason=None, file_start=None, book_start=book_start
        )

    if book_start is not None and file_start > book_start:
        return CompletenessResult(
            partial=True,
            reason=(
                f"This file starts {file_start.isoformat()}; your book starts "
                f"{book_start.isoformat()}."
            ),
            file_start=file_start,
            book_start=book_start,
        )

    if earliest_logged_file_start is not None and file_start > earliest_logged_file_start:
        return CompletenessResult(
            partial=True,
            reason=(
                f"This file starts {file_start.isoformat()}; an earlier sync covered "
                f"from {earliest_logged_file_start.isoformat()}."
            ),
            file_start=file_start,
            book_start=book_start,
        )

    file_references = {row.reference for row in rows if row.reference}
    missing = [
        tx.csv_reference
        for tx in book
        if tx.source == _SCALABLE_SOURCE
        and tx.csv_reference
        and tx.csv_reference not in file_references
    ]
    if missing:
        n = len(missing)
        plural = "trade" if n == 1 else "trades"
        return CompletenessResult(
            partial=True,
            reason=f"{n} {plural} already in your book are not in this file.",
            file_start=file_start,
            book_start=book_start,
        )

    return CompletenessResult(
        partial=False, reason=None, file_start=file_start, book_start=book_start
    )
