"""Parse Scalable Capital CSV exports into typed rows.

Does not filter by status or type — all rows are returned.
Filtering is the importer's responsibility (separation of concerns).
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_EXPECTED_COLUMNS = 14


class ParseError(Exception):
    def __init__(self, row_number: int, message: str) -> None:
        super().__init__(f"Row {row_number}: {message}")
        self.row_number = row_number


class ParsedCsvRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    row_number: int
    date: date
    time: str
    status: str
    reference: str
    description: str
    asset_type: str
    type: str
    isin: str
    shares: Decimal | None
    price: Decimal | None
    amount: Decimal | None
    fee: Decimal | None
    tax: Decimal | None
    currency: str


def _parse_european_decimal(value: str, row_number: int, field_name: str) -> Decimal:
    """Parse European-format decimal: '1.760,325' → Decimal('1760.325')."""
    stripped = value.strip()
    # Remove thousands separator (.) then replace decimal comma (,) with dot
    normalized = stripped.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ParseError(row_number, f"Invalid {field_name} '{value}'") from exc


def _parse_optional_decimal(
    value: str, row_number: int, field_name: str
) -> Decimal | None:
    if not value.strip():
        return None
    return _parse_european_decimal(value, row_number, field_name)


def parse_csv(path: Path) -> list[ParsedCsvRow]:
    """Read and parse all rows from a Scalable Capital CSV export.

    Raises ParseError on malformed rows (wrong column count, unparseable values).
    Raises FileNotFoundError if the file does not exist.
    """
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"CSV file not found: {path}")

    lines = content.splitlines()
    if not lines:
        return []

    reader = csv.reader(lines, delimiter=";")
    rows: list[ParsedCsvRow] = []
    header_seen = False

    for raw_row in reader:
        row_number = reader.line_num

        if not header_seen:
            header_seen = True
            if len(raw_row) < _EXPECTED_COLUMNS:
                raise ParseError(
                    row_number,
                    f"Header has {len(raw_row)} columns, expected {_EXPECTED_COLUMNS}",
                )
            continue

        if len(raw_row) != _EXPECTED_COLUMNS:
            raise ParseError(
                row_number,
                f"Expected {_EXPECTED_COLUMNS} columns, got {len(raw_row)}",
            )

        (
            date_str,
            time_str,
            status,
            reference,
            description,
            asset_type,
            type_,
            isin,
            shares_str,
            price_str,
            amount_str,
            fee_str,
            tax_str,
            currency,
        ) = raw_row

        try:
            trade_date = date.fromisoformat(date_str.strip())
        except ValueError as exc:
            raise ParseError(row_number, f"Invalid date '{date_str.strip()}'") from exc

        rows.append(
            ParsedCsvRow(
                row_number=row_number,
                date=trade_date,
                time=time_str.strip(),
                status=status.strip(),
                reference=reference.strip(),
                description=description.strip(),
                asset_type=asset_type.strip(),
                type=type_.strip(),
                isin=isin.strip(),
                shares=_parse_optional_decimal(shares_str, row_number, "shares"),
                price=_parse_optional_decimal(price_str, row_number, "price"),
                amount=_parse_optional_decimal(amount_str, row_number, "amount"),
                fee=_parse_optional_decimal(fee_str, row_number, "fee"),
                tax=_parse_optional_decimal(tax_str, row_number, "tax"),
                currency=currency.strip(),
            )
        )

    return rows
