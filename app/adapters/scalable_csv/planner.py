"""Classify parsed CSV rows into planned import actions (no write I/O)."""
from __future__ import annotations

import hashlib
from decimal import Decimal

from app.adapters.scalable_csv.parser import ParsedCsvRow
from app.domain.csv_import import (
    ImportPlan,
    PlannedAction,
    PlannedRow,
    RowStatus,
)
from app.domain.isin_map import IsinMapDocument
from app.domain.models import Transaction

_EXECUTED_STATUS = "Executed"
_IN_SCOPE_TYPES = frozenset({"Buy", "Sell", "Savings plan"})

# Expected amount sign per row type: "negative"=cash out, "positive"=cash in.
_EXPECTED_AMOUNT_SIGN: dict[str, str] = {
    "Buy": "negative",
    "Savings plan": "negative",
    "Sell": "positive",
}


def _check_currency(row: ParsedCsvRow) -> str | None:
    """Reject non-EUR rows. All Scalable Capital rows are expected to be EUR-native;
    a non-EUR row must never be silently tagged as EUR (TICKET-009 silent corruption).
    """
    if row.currency != "EUR":
        return (
            f"Unexpected currency {row.currency!r} — only EUR is expected. "
            "This may indicate a CSV format change."
        )
    return None


def _check_amount(row: ParsedCsvRow) -> str | None:
    """Verify abs(amount) ≈ abs(shares × price) within 0.01 EUR tolerance.

    Sign-agnostic: works for both positive-amount (Sell) and negative-amount
    (Buy/Savings plan) rows. The fee column is NOT included in the amount column.
    """
    if row.shares is None or row.price is None or row.amount is None:
        return None
    expected = abs(row.shares * row.price)
    actual = abs(row.amount)
    diff = abs(expected - actual)
    if diff >= Decimal("0.01"):
        return (
            f"Amount sanity check failed — abs(amount)={actual:.6f}, "
            f"abs(shares×price)={expected:.6f}, diff={diff:.6f} ≥ 0.01. "
            "This may indicate a CSV format change."
        )
    return None


def _check_sign(row: ParsedCsvRow) -> str | None:
    """Verify the amount has the expected directional sign for this row type."""
    if row.amount is None:
        return None
    expected = _EXPECTED_AMOUNT_SIGN.get(row.type, "either")
    if expected == "negative" and row.amount > 0:
        return (
            f"Directional sign error — {row.type!r} expects negative amount "
            f"(cash out) but got {row.amount}. This may indicate a CSV format change."
        )
    if expected == "positive" and row.amount < 0:
        return (
            f"Directional sign error — {row.type!r} expects positive amount "
            f"(cash in) but got {row.amount}. This may indicate a CSV format change."
        )
    return None


def _validate_row(row: ParsedCsvRow) -> str | None:
    """Return the first validation error message for a row, or None if it passes."""
    for check in (_check_currency, _check_amount, _check_sign):
        message = check(row)
        if message is not None:
            return message
    return None


def _content_hash(tx: Transaction) -> str:
    key = (
        f"{tx.type}|{tx.ticker}|{tx.trade_date}|"
        f"{tx.shares:.6f}|{tx.price_native.amount:.4f}|{tx.price_native.currency}"
    )
    return hashlib.sha1(key.encode()).hexdigest()


def _row_content_hash(row: ParsedCsvRow, ticker: str, tx_type_str: str) -> str:
    if row.shares is None or row.price is None:
        return ""
    key = (
        f"{tx_type_str}|{ticker}|{row.date}|"
        f"{row.shares:.6f}|{row.price:.4f}|EUR"
    )
    return hashlib.sha1(key.encode()).hexdigest()


def plan_import(
    rows: list[ParsedCsvRow],
    existing_txs: list[Transaction],
    isin_doc: IsinMapDocument,
) -> ImportPlan:
    """Classify every CSV row into a planned action without writing anything.

    All Scalable Capital CSV rows carry EUR prices; no FX lookup is performed.
    Security-transfer pairs (both incoming and outgoing legs) are skipped as
    internal reshuffles with no economic effect.
    """
    existing_by_ref: dict[str, Transaction] = {
        tx.csv_reference: tx
        for tx in existing_txs
        if tx.csv_reference is not None
    }
    existing_by_content: dict[str, Transaction] = {
        _content_hash(tx): tx for tx in existing_txs
    }
    # Legacy: old importer stored reference directly as tx.id for scalable_csv rows
    existing_scalable_ids: set[str] = {
        tx.id for tx in existing_txs if tx.source == "scalable_csv"
    }

    planned: list[PlannedRow] = []

    for row in rows:
        if row.status != _EXECUTED_STATUS:
            planned.append(_make(row, RowStatus.CANCELLED_OR_EXPIRED, PlannedAction.SKIP))
            continue

        # Security transfers are internal reshuffles — skip both legs.
        if row.type == "Security transfer":
            planned.append(_make(row, RowStatus.INTERNAL_TRANSFER, PlannedAction.SKIP))
            continue

        if row.type not in _IN_SCOPE_TYPES:
            planned.append(_make(row, RowStatus.OUT_OF_SCOPE_V1, PlannedAction.SKIP))
            continue

        if row.reference in existing_by_ref or row.reference in existing_scalable_ids:
            planned.append(_make(row, RowStatus.ALREADY_IMPORTED, PlannedAction.NOOP))
            continue

        mapping = isin_doc.entries.get(row.isin)
        if mapping is not None and mapping.status == "ignored":
            planned.append(_make(row, RowStatus.IGNORED_ISIN, PlannedAction.SKIP))
            continue
        if mapping is None or mapping.status == "unmapped":
            planned.append(_make(row, RowStatus.UNMAPPED_ISIN, PlannedAction.SKIP))
            continue

        assert mapping.ticker is not None

        tx_type_str = "buy" if row.type in ("Buy", "Savings plan") else "sell"
        row_hash = _row_content_hash(row, mapping.ticker, tx_type_str)

        if row_hash and row_hash in existing_by_content:
            existing_tx = existing_by_content[row_hash]
            if existing_tx.source == "scalable_csv":
                planned.append(_make(
                    row, RowStatus.ALREADY_IMPORTED, PlannedAction.NOOP, ticker=mapping.ticker
                ))
            else:
                planned.append(_make(
                    row,
                    RowStatus.CONFLICT_WITH_MANUAL,
                    PlannedAction.REPLACE,
                    ticker=mapping.ticker,
                    conflict_tx_id=existing_tx.id,
                ))
            continue

        # Per-row guards run last, on rows that would otherwise be NEW/INSERT.
        # A failure becomes a blocked VALIDATION_ERROR (never a silent import).
        validation_error = _validate_row(row)
        if validation_error is not None:
            planned.append(_make(
                row,
                RowStatus.VALIDATION_ERROR,
                PlannedAction.SKIP,
                ticker=mapping.ticker,
                error_message=validation_error,
            ))
            continue

        planned.append(_make(row, RowStatus.NEW, PlannedAction.INSERT, ticker=mapping.ticker))

    return ImportPlan(rows=tuple(planned))


def _make(
    row: ParsedCsvRow,
    status: RowStatus,
    action: PlannedAction,
    *,
    ticker: str | None = None,
    conflict_tx_id: str | None = None,
    error_message: str | None = None,
    fx_rate_eur: Decimal | None = None,
) -> PlannedRow:
    return PlannedRow(
        row_number=row.row_number,
        trade_date=row.date,
        csv_type=row.type,
        isin=row.isin,
        reference=row.reference,
        description=row.description,
        shares=row.shares,
        price=row.price,
        amount=row.amount,
        fee=row.fee,
        tax=row.tax,
        status=status,
        action=action,
        proposed_ticker=ticker,
        conflict_tx_id=conflict_tx_id,
        error_message=error_message,
        fx_rate_eur=fx_rate_eur,
    )
