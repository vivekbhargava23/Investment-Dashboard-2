"""Classify parsed CSV rows into planned import actions (no write I/O)."""
from __future__ import annotations

import hashlib
from decimal import Decimal

from app.adapters.scalable_csv.parser import (
    EXECUTED_STATUS,
    IN_SCOPE_TYPES,
    ParsedCsvRow,
)
from app.domain.csv_import import (
    CORPORATE_ACTION_TYPE,
    SECURITY_ASSET_TYPE,
    FeedState,
    ImportPlan,
    PlannedAction,
    PlannedRow,
    ProposedType,
    RowStatus,
)
from app.domain.isin_map import IsinMapDocument
from app.domain.models import Transaction

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
    # abs(): a corporate action's share count is signed in the file, but the
    # transaction it would become always holds a positive quantity.
    key = (
        f"{tx_type_str}|{ticker}|{row.date}|"
        f"{abs(row.shares):.6f}|{row.price:.4f}|EUR"
    )
    return hashlib.sha1(key.encode()).hexdigest()


def _resolve_ticker(isin: str, isin_doc: IsinMapDocument) -> tuple[str, FeedState]:
    """Ticker to trade under, plus the feed state behind it (display only).

    Without a ``mapped`` entry the ISIN itself is the placeholder ticker; picking a
    feed later rewrites it (ADR-014 rule 2).
    """
    mapping = isin_doc.entries.get(isin)
    if mapping is not None and mapping.status == "mapped" and mapping.ticker:
        return mapping.ticker, "mapped"
    if mapping is not None and mapping.status == "ignored":
        return isin.upper(), "ignored"
    return isin.upper(), "unmapped"


def _is_importable_corporate_action(row: ParsedCsvRow) -> bool:
    """True for the Security leg of a corporate action that moves shares.

    Scalable books a knock-out as two legs sharing one reference: a Security leg
    carrying the share movement and a Cash leg carrying the payout. Only the
    Security leg is a transaction; without it the position never closes and the
    book keeps valuing shares the broker has already taken away.
    """
    return (
        row.type == CORPORATE_ACTION_TYPE
        and row.asset_type == SECURITY_ASSET_TYPE
        and row.shares is not None
        and row.shares != Decimal("0")
        and row.price is not None
    )


def _proposed_type(row: ParsedCsvRow) -> ProposedType:
    """The direction to import a row under.

    Buy and Savings plan add shares, Sell removes them, and a corporate action
    says which it is in the sign of its share count.
    """
    if row.type == CORPORATE_ACTION_TYPE:
        shares = row.shares or Decimal("0")
        return "sell" if shares < 0 else "buy"
    return "sell" if row.type == "Sell" else "buy"


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
        if row.status != EXECUTED_STATUS:
            planned.append(_make(row, RowStatus.CANCELLED_OR_EXPIRED, PlannedAction.SKIP))
            continue

        # Security transfers are internal reshuffles — skip both legs.
        if row.type == "Security transfer":
            planned.append(_make(row, RowStatus.INTERNAL_TRANSFER, PlannedAction.SKIP))
            continue

        if row.type not in IN_SCOPE_TYPES and not _is_importable_corporate_action(row):
            planned.append(_make(row, RowStatus.OUT_OF_SCOPE_V1, PlannedAction.SKIP))
            continue

        if row.reference in existing_by_ref or row.reference in existing_scalable_ids:
            planned.append(_make(
                row,
                RowStatus.ALREADY_IMPORTED,
                PlannedAction.NOOP,
                proposed_type=_proposed_type(row),
            ))
            continue

        # The ISIN is the identity of the holding (ADR-014 rule 7): an executed trade
        # is always imported, so a missing or ignored feed only changes the ticker.
        if not row.isin:
            planned.append(_make(
                row,
                RowStatus.VALIDATION_ERROR,
                PlannedAction.SKIP,
                error_message="row has no ISIN",
            ))
            continue

        ticker, feed_state = _resolve_ticker(row.isin, isin_doc)

        tx_type_str = _proposed_type(row)
        row_hash = _row_content_hash(row, ticker, tx_type_str)

        if row_hash and row_hash in existing_by_content:
            existing_tx = existing_by_content[row_hash]
            if existing_tx.source == "scalable_csv":
                planned.append(_make(
                    row,
                    RowStatus.ALREADY_IMPORTED,
                    PlannedAction.NOOP,
                    ticker=ticker,
                    proposed_type=tx_type_str,
                    feed_state=feed_state,
                ))
            else:
                planned.append(_make(
                    row,
                    RowStatus.CONFLICT_WITH_MANUAL,
                    PlannedAction.REPLACE,
                    ticker=ticker,
                    proposed_type=tx_type_str,
                    feed_state=feed_state,
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
                ticker=ticker,
                proposed_type=tx_type_str,
                feed_state=feed_state,
                error_message=validation_error,
            ))
            continue

        planned.append(_make(
            row,
            RowStatus.NEW,
            PlannedAction.INSERT,
            ticker=ticker,
            proposed_type=tx_type_str,
            feed_state=feed_state,
        ))

    return ImportPlan(rows=tuple(planned))


def _make(
    row: ParsedCsvRow,
    status: RowStatus,
    action: PlannedAction,
    *,
    ticker: str | None = None,
    proposed_type: ProposedType | None = None,
    feed_state: FeedState | None = None,
    conflict_tx_id: str | None = None,
    error_message: str | None = None,
    fx_rate_eur: Decimal | None = None,
) -> PlannedRow:
    return PlannedRow(
        row_number=row.row_number,
        trade_date=row.date,
        csv_type=row.type,
        asset_type=row.asset_type,
        isin=row.isin,
        reference=row.reference,
        description=row.description,
        # The file's sign is preserved: an outbound security-transfer leg and a
        # corporate-action knock-out are both negative, and reconciliation reads
        # that sign. ``build_transaction`` takes the absolute value.
        shares=row.shares,
        price=row.price,
        amount=row.amount,
        fee=row.fee,
        tax=row.tax,
        status=status,
        action=action,
        proposed_ticker=ticker,
        proposed_type=proposed_type,
        feed_state=feed_state,
        conflict_tx_id=conflict_tx_id,
        error_message=error_message,
        fx_rate_eur=fx_rate_eur,
    )
