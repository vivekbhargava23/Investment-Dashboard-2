"""Reconcile CSV-expected shares per ISIN against the book, with a cause for any diff."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.domain.csv_import import (
    CORPORATE_ACTION_TYPE,
    SECURITY_ASSET_TYPE,
    PlannedRow,
    RowStatus,
)
from app.domain.models import Transaction, TransactionType

MATCH_TOLERANCE = Decimal("0.000001")

# Row types that move shares for an ISIN, and their sign.
_ADD_TYPES = frozenset({"Buy", "Savings plan"})
_SUB_TYPES = frozenset({"Sell"})
_TRANSFER_TYPE = "Security transfer"

# A holding written down to zero by hand. The broker file will never mention it,
# so it is subtracted from the CSV side to keep the two sides comparable.
_WRITE_OFF_SOURCE = "write_off"


class ReconcileRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    isin: str
    name: str
    shares_csv: Decimal
    shares_book: Decimal
    diff: Decimal
    matches: bool
    cause: str | None
    last_trade_price_eur: Decimal | None


def _isin_universe(
    plan_rows: Sequence[PlannedRow], transactions: Sequence[Transaction]
) -> set[str]:
    isins = {row.isin for row in plan_rows if row.isin}
    isins |= {tx.isin for tx in transactions if tx.isin}
    return isins


def _is_corporate_action_security_leg(row: PlannedRow) -> bool:
    """The leg of a corporate action that moves shares (the Cash leg does not)."""
    return (
        row.csv_type == CORPORATE_ACTION_TYPE
        and row.asset_type == SECURITY_ASSET_TYPE
        and row.shares is not None
    )


def _shares_csv(rows: Sequence[PlannedRow]) -> Decimal:
    total = Decimal("0")
    for row in rows:
        if row.status == RowStatus.CANCELLED_OR_EXPIRED or row.shares is None:
            continue
        if _is_corporate_action_security_leg(row):
            # Signed in the file, like a security transfer: a knock-out books a
            # negative share count and takes the position to zero.
            total += row.shares
        elif row.csv_type in _ADD_TYPES or row.csv_type == _TRANSFER_TYPE:
            total += row.shares
        elif row.csv_type in _SUB_TYPES:
            total -= row.shares
    return total


def _write_off_shares(transactions: Sequence[Transaction]) -> Decimal:
    """Shares written off by hand for this ISIN (always sells, always positive)."""
    return sum(
        (tx.shares for tx in transactions if tx.source == _WRITE_OFF_SOURCE),
        Decimal("0"),
    )


def _shares_book(transactions: Sequence[Transaction]) -> Decimal:
    total = Decimal("0")
    for tx in transactions:
        if tx.type == TransactionType.BUY:
            total += tx.shares
        else:
            total -= tx.shares
    return total


def _transfer_net(rows: Sequence[PlannedRow]) -> Decimal:
    total = Decimal("0")
    for row in rows:
        if row.status == RowStatus.CANCELLED_OR_EXPIRED or row.shares is None:
            continue
        if row.csv_type == _TRANSFER_TYPE:
            total += row.shares
    return total


def _name(rows: Sequence[PlannedRow]) -> str:
    """The instrument's name, taken from its most recent trade.

    Cash rows carry the payout's description ("Dividend SAP SE"), so naming a
    holding after the latest row of any kind renames it every time it pays.
    Corporate actions are excluded for the same reason.
    """
    trades = [r for r in rows if r.csv_type in _ADD_TYPES | _SUB_TYPES | {_TRANSFER_TYPE}]
    candidates = trades or list(rows)
    latest = max(candidates, key=lambda r: (r.trade_date, r.row_number))
    return latest.description


def _last_trade_price_eur(rows: Sequence[PlannedRow]) -> Decimal | None:
    """The price of the latest real trade — never a corporate action.

    A knock-out settles at €0,001; valuing the rest of a holding at that price
    would wipe it off the screen rather than value it.
    """
    candidates = [
        row
        for row in rows
        if row.csv_type in _ADD_TYPES | _SUB_TYPES
        and row.status != RowStatus.CANCELLED_OR_EXPIRED
        and row.price is not None
    ]
    if not candidates:
        return None
    latest = max(candidates, key=lambda r: (r.trade_date, r.row_number))
    return latest.price


def _format_shares(value: Decimal) -> str:
    text = f"{value.normalize():f}"
    return text


def _cause(
    isin: str,
    rows: Sequence[PlannedRow],
    transactions: Sequence[Transaction],
) -> str:
    # 1. validation failures — the row was executed at the broker but never imported.
    failed = [r for r in rows if r.status == RowStatus.VALIDATION_ERROR]
    if failed:
        n = len(failed)
        plural = "row" if n == 1 else "rows"
        return f"{n} {plural} failed validation — see Details"

    # 4. security-transfer legs that don't net to zero for this ISIN.
    transfer_net = _transfer_net(rows)
    if transfer_net != Decimal("0"):
        sign = "+" if transfer_net > 0 else "-"
        return f"transfer imbalance: net {sign}{_format_shares(abs(transfer_net))} shares"

    # 5. a transaction whose id is a CSV reference for this ISIN but is no longer
    #    sourced from the CSV — it was edited manually on the Manage page.
    references = {r.reference for r in rows if r.status != RowStatus.CANCELLED_OR_EXPIRED}
    for tx in transactions:
        if tx.id in references and tx.source != "scalable_csv":
            return "edited manually on the Manage page"

    # 7. a manual transaction for the same instrument, under the ticker the CSV uses.
    mapped_ticker = next(
        (tx.ticker for tx in transactions if tx.source == "scalable_csv" and tx.isin == isin),
        None,
    )
    if mapped_ticker is None:
        proposed = [r.proposed_ticker for r in rows if r.proposed_ticker]
        mapped_ticker = proposed[-1] if proposed else None
    if mapped_ticker is not None:
        manual_matches = [
            tx for tx in transactions if tx.source == "manual" and tx.ticker == mapped_ticker
        ]
        # A write-off is a manual entry the CSV side already accounts for, so it
        # is never the explanation for a difference.
        if manual_matches:
            manual_shares = manual_matches[0].shares
            return (
                "includes a manual entry for the same instrument "
                f"({_format_shares(manual_shares)} shares)"
            )

    # 8. the planner flagged a possible duplicate of a manual entry.
    if any(r.status == RowStatus.CONFLICT_WITH_MANUAL for r in rows):
        return "possible duplicate of a manual entry — decide on the Sync tab"

    # 9. nothing explains the diff — should be rare; surfaced for investigation.
    return "unknown — check Details"


def reconcile(
    plan_rows: Sequence[PlannedRow],
    transactions: Sequence[Transaction],
    *,
    partial: bool = False,
) -> list[ReconcileRow]:
    """Compare CSV-expected shares per ISIN against the book, with a cause for any diff.

    ``partial`` files skip reconciliation entirely (the caller shows the partial-file
    task instead) — everything else in this function assumes a complete file.
    """
    if partial:
        return []

    rows_by_isin: dict[str, list[PlannedRow]] = defaultdict(list)
    for row in plan_rows:
        if row.isin:
            rows_by_isin[row.isin].append(row)

    tx_by_isin: dict[str, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        if tx.isin:
            tx_by_isin[tx.isin].append(tx)

    result: list[ReconcileRow] = []
    for isin in _isin_universe(plan_rows, transactions):
        isin_rows = rows_by_isin.get(isin, [])
        isin_txs = tx_by_isin.get(isin, [])

        shares_csv = _shares_csv(isin_rows) - _write_off_shares(isin_txs)
        shares_book = _shares_book(isin_txs)
        diff = shares_csv - shares_book
        matches = abs(diff) < MATCH_TOLERANCE

        name = _name(isin_rows) if isin_rows else isin
        last_trade_price_eur = _last_trade_price_eur(isin_rows) if isin_rows else None
        cause = None if matches else _cause(isin, isin_rows, transactions)

        result.append(
            ReconcileRow(
                isin=isin,
                name=name,
                shares_csv=shares_csv,
                shares_book=shares_book,
                diff=diff,
                matches=matches,
                cause=cause,
                last_trade_price_eur=last_trade_price_eur,
            )
        )

    result.sort(
        key=lambda r: (
            -(abs(r.diff) * (r.last_trade_price_eur or Decimal("1"))),
            r.isin,
        )
    )
    return result
