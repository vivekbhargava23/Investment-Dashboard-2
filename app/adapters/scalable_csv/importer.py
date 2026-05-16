"""Orchestrate CSV parsing, ISIN mapping, and transaction repository updates.

Takes parsed CSV rows (from parser.py), an IsinMapRepository, and a
TransactionRepository. Applies business rules (status filter, type filter,
deduplication, amount sanity check) and writes the results.

All Scalable Capital CSV rows carry EUR prices (currency column is always EUR).
No FX lookup is performed; every imported Transaction is stored as EUR-native
with fx_rate_eur=1.  Security-transfer pairs are skipped as internal reshuffles.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import ValidationError

from app.adapters.scalable_csv.parser import ParsedCsvRow
from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.ports.isin_map import IsinMapRepository
from app.ports.repository import TransactionRepository

_IN_SCOPE_TYPES = frozenset({"Buy", "Sell", "Savings plan"})
_EXECUTED_STATUS = "Executed"

# Expected amount sign per row type: "negative"=cash out, "positive"=cash in, "either"=no check.
_EXPECTED_AMOUNT_SIGN: dict[str, str] = {
    "Buy": "negative",
    "Savings plan": "negative",
    "Sell": "positive",
}


@dataclass
class ImportSummary:
    csv_path: str
    total_rows: int = 0
    status_filtered: int = 0
    status_filtered_detail: dict[str, int] = field(default_factory=dict)
    out_of_scope: int = 0
    internal_transfers_skipped: int = 0
    in_scope: int = 0
    already_existing: int = 0
    new_transactions: int = 0
    unmapped: int = 0
    unmapped_isins: list[tuple[str, str]] = field(default_factory=list)
    invalid_mapping: int = 0
    invalid_mapping_errors: list[tuple[str, str]] = field(default_factory=list)
    portfolio_total: int = 0
    unique_tickers: int = 0


def _csv_type_to_transaction_type(csv_type: str) -> TransactionType:
    if csv_type in ("Buy", "Savings plan"):
        return TransactionType.BUY
    if csv_type == "Sell":
        return TransactionType.SELL
    raise ValueError(f"Unsupported CSV type: {csv_type!r}")


def _check_amount(row: ParsedCsvRow) -> None:
    """Verify abs(amount) ≈ abs(shares × price) within 0.01 EUR tolerance.

    Sign-agnostic: works for both positive-amount (Sell) and
    negative-amount (Buy/Savings plan) rows. The fee column is NOT included in
    the amount column — it is recorded separately.
    """
    if row.shares is None or row.price is None or row.amount is None:
        return
    expected = abs(row.shares * row.price)
    actual = abs(row.amount)
    diff = abs(expected - actual)
    if diff >= Decimal("0.01"):
        raise ValueError(
            f"Row {row.row_number}: amount sanity check failed — "
            f"abs(amount)={actual:.6f}, abs(shares×price)={expected:.6f}, "
            f"diff={diff:.6f} ≥ 0.01. This may indicate a CSV format change."
        )


def _check_sign(row: ParsedCsvRow) -> None:
    """Verify shares and amount have the expected directional sign for this row type."""
    if row.amount is None:
        return
    expected = _EXPECTED_AMOUNT_SIGN.get(row.type, "either")
    if expected == "either":
        return
    if expected == "negative" and row.amount > 0:
        raise ValueError(
            f"Row {row.row_number}: directional sign error — "
            f"{row.type!r} expects negative amount (cash out) but got {row.amount}. "
            "This may indicate a CSV format change."
        )
    if expected == "positive" and row.amount < 0:
        raise ValueError(
            f"Row {row.row_number}: directional sign error — "
            f"{row.type!r} expects positive amount (cash in) but got {row.amount}. "
            "This may indicate a CSV format change."
        )


def _build_notes(row: ParsedCsvRow) -> str | None:
    parts: list[str] = [row.description]
    if row.type == "Sell" and row.tax is not None and row.tax != Decimal("0"):
        parts.append(f"tax_withheld_eur={row.tax}")
    return "; ".join(parts)


def _update_last_seen(
    entries: dict[str, IsinMapping], row: ParsedCsvRow
) -> None:
    """Update last_seen_in_csv (and name) for an existing entry if row.date is newer."""
    existing = entries.get(row.isin)
    if existing is None:
        return
    if existing.last_seen_in_csv is None or row.date > existing.last_seen_in_csv:
        entries[row.isin] = IsinMapping(
            ticker=existing.ticker,
            name=row.description,
            status=existing.status,
            last_seen_in_csv=row.date,
        )


def run_import(
    rows: list[ParsedCsvRow],
    csv_filename: str,
    tx_repo: TransactionRepository,
    isin_map_repo: IsinMapRepository,
) -> ImportSummary:
    summary = ImportSummary(csv_path=csv_filename, total_rows=len(rows))

    existing_transactions = tx_repo.load_all()
    existing_ids: set[str] = {tx.id for tx in existing_transactions}

    isin_doc = isin_map_repo.load()
    entries: dict[str, IsinMapping] = dict(isin_doc.entries)

    new_transactions: list[Transaction] = []
    # Track which ISINs we've already reported in summary (avoid duplicates in lists)
    reported_unmapped: set[str] = set()
    reported_invalid: set[str] = set()

    for row in rows:
        # Status filter
        if row.status != _EXECUTED_STATUS:
            summary.status_filtered += 1
            summary.status_filtered_detail[row.status] = (
                summary.status_filtered_detail.get(row.status, 0) + 1
            )
            continue

        # Security transfers are internal reshuffles — skip both legs entirely.
        if row.type == "Security transfer":
            summary.internal_transfers_skipped += 1
            continue

        # Type filter
        if row.type not in _IN_SCOPE_TYPES:
            summary.out_of_scope += 1
            continue

        summary.in_scope += 1

        # Non-EUR currency defense (all Scalable rows should be EUR)
        if row.currency != "EUR":
            raise ValueError(
                f"Row {row.row_number} (ISIN {row.isin}): unexpected currency "
                f"{row.currency!r} — only EUR is expected. "
                "This may indicate a CSV format change."
            )

        # Shares/price must be present for in-scope rows
        if row.shares is None or row.price is None:
            raise ValueError(
                f"Row {row.row_number}: in-scope row has blank shares or price"
            )

        # Amount sanity check (sign-agnostic)
        _check_amount(row)

        # Directional sign check (separate from amount magnitude check)
        _check_sign(row)

        # Deduplication — still update last_seen even for duplicates
        if row.reference in existing_ids:
            summary.already_existing += 1
            _update_last_seen(entries, row)
            continue

        # ISIN lookup
        mapping = entries.get(row.isin)

        if mapping is None:
            # First time seeing this ISIN: add as unmapped
            entries[row.isin] = IsinMapping(
                ticker=None,
                name=row.description,
                status="unmapped",
                last_seen_in_csv=row.date,
            )
            if row.isin not in reported_unmapped:
                reported_unmapped.add(row.isin)
                summary.unmapped_isins.append((row.isin, row.description))
            summary.unmapped += 1
            continue

        # Update last_seen for existing entry
        _update_last_seen(entries, row)
        # Re-fetch in case _update_last_seen replaced the entry
        mapping = entries[row.isin]

        if mapping.status == "unmapped":
            if row.isin not in reported_unmapped:
                reported_unmapped.add(row.isin)
                summary.unmapped_isins.append((row.isin, row.description))
            summary.unmapped += 1
            continue

        # Build Transaction — all Scalable CSV rows are EUR-native
        assert mapping.ticker is not None
        tx_type = _csv_type_to_transaction_type(row.type)

        price_native = Money(amount=row.price, currency=Currency.EUR)
        fees_native: Money | None = (
            Money(amount=row.fee, currency=Currency.EUR) if row.fee is not None else None
        )
        fx_rate_eur = Decimal("1")

        try:
            tx = Transaction(
                id=row.reference,
                type=tx_type,
                ticker=mapping.ticker,
                trade_date=row.date,
                shares=row.shares,
                price_native=price_native,
                fees_native=fees_native,
                fx_rate_eur=fx_rate_eur,
                notes=_build_notes(row),
                isin=row.isin,
                csv_reference=row.reference,
                source="scalable_csv",
            )
        except ValidationError as exc:
            if row.isin not in reported_invalid:
                reported_invalid.add(row.isin)
                summary.invalid_mapping_errors.append((row.isin, str(exc)))
            summary.invalid_mapping += 1
            continue

        new_transactions.append(tx)
        existing_ids.add(row.reference)  # prevent within-CSV duplicates
        summary.new_transactions += 1

    # Persist updated ISIN map
    updated_doc = IsinMapDocument(version=isin_doc.version, entries=entries)
    isin_map_repo.save(updated_doc)

    # Persist updated portfolio (only write if there are new transactions)
    all_transactions = existing_transactions + new_transactions
    if new_transactions:
        tx_repo.save_all(all_transactions)

    summary.portfolio_total = len(all_transactions)
    summary.unique_tickers = len({tx.ticker for tx in all_transactions})
    return summary
