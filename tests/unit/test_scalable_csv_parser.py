"""Unit tests for app.adapters.scalable_csv.parser."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.scalable_csv.parser import ParseError, parse_csv

FIXTURES = Path(__file__).parent.parent / "fixtures" / "scalable_csv"


def test_happy_path_four_rows():
    rows = parse_csv(FIXTURES / "happy_path.csv")
    assert len(rows) == 4

    buy = rows[0]
    assert buy.date == date(2026, 3, 1)
    assert buy.status == "Executed"
    assert buy.reference == "REF001"
    assert buy.description == "SAP SE"
    assert buy.type == "Buy"
    assert buy.isin == "DE0007164600"
    assert buy.shares == Decimal("10")
    assert buy.price == Decimal("100.00")
    assert buy.amount == Decimal("-1000.00")
    assert buy.fee == Decimal("0.99")
    assert buy.tax == Decimal("0.00")
    assert buy.currency == "EUR"

    sell = rows[1]
    assert sell.type == "Sell"
    assert sell.shares == Decimal("5")
    assert sell.price == Decimal("200.00")
    assert sell.amount == Decimal("1000.00")
    assert sell.tax == Decimal("15.00")

    savings = rows[2]
    assert savings.type == "Savings plan"
    assert savings.shares == Decimal("7.054176")
    assert savings.price == Decimal("70.88")
    assert savings.amount == Decimal("-499.99999488")
    assert savings.fee == Decimal("0.00")

    transfer = rows[3]
    assert transfer.type == "Security transfer"
    assert transfer.shares == Decimal("50")
    assert transfer.price == Decimal("8.68")
    assert transfer.amount == Decimal("434.00")
    assert transfer.fee is None
    assert transfer.tax is None


def test_european_number_parsing():
    """Thousands separator (.) and decimal comma (,) are both handled."""
    rows = parse_csv(FIXTURES / "happy_path.csv")
    # amount on sell row: "1.000,00" → 1000.00
    assert rows[1].amount == Decimal("1000.00")
    # amount on savings plan: "-499,99999488" → -499.99999488
    assert rows[2].amount == Decimal("-499.99999488")
    # shares on savings plan: "7,054176" → 7.054176
    assert rows[2].shares == Decimal("7.054176")


def test_blank_fields_in_non_trade_row():
    """Deposit/Distribution rows have blank shares, price, fee, tax — should be None."""
    rows = parse_csv(FIXTURES / "out_of_scope_types.csv")
    deposit = next(r for r in rows if r.type == "Deposit")
    assert deposit.shares is None
    assert deposit.price is None


def test_status_filter_not_applied_by_parser():
    """Parser returns ALL rows including Cancelled, Expired, Rejected."""
    rows = parse_csv(FIXTURES / "mixed_statuses.csv")
    statuses = [r.status for r in rows]
    assert "Cancelled" in statuses
    assert "Expired" in statuses
    assert "Rejected" in statuses
    assert statuses.count("Executed") == 2


def test_special_characters_in_description():
    """Descriptions with &, (, ) survive CSV parsing intact."""
    rows = parse_csv(FIXTURES / "special_descriptions.csv")
    assert rows[0].description == "Vanguard S&P 500 (Acc)"
    assert rows[1].description == "21shares Polygon ETP"


def test_malformed_row_raises_parse_error():
    """A row with wrong column count raises ParseError referencing the row number."""
    with pytest.raises(ParseError) as exc_info:
        parse_csv(FIXTURES / "malformed_columns.csv")
    assert exc_info.value.row_number == 2
    assert "columns" in str(exc_info.value)


def test_file_not_found_raises():
    with pytest.raises(FileNotFoundError):
        parse_csv(FIXTURES / "nonexistent.csv")


def test_empty_file_returns_no_rows(tmp_path: Path):
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("")
    rows = parse_csv(empty_csv)
    assert rows == []


def test_header_only_returns_no_rows(tmp_path: Path):
    header_only = tmp_path / "header_only.csv"
    header_only.write_text(
        "date;time;status;reference;description;assetType;type;isin;"
        "shares;price;amount;fee;tax;currency\n"
    )
    rows = parse_csv(header_only)
    assert rows == []


def test_row_numbers_are_correct(tmp_path: Path):
    """row_number reflects 1-indexed line number including header."""
    csv_path = tmp_path / "two_rows.csv"
    csv_path.write_text(
        "date;time;status;reference;description;assetType;type;isin;"
        "shares;price;amount;fee;tax;currency\n"
        "2026-03-01;10:00:00;Executed;REF001;SAP SE;Security;Buy;"
        "DE0007164600;10;100,00;-1.000,00;0,99;0,00;EUR\n"
        "2026-03-02;11:00:00;Executed;REF002;SAP SE;Security;Buy;"
        "DE0007164600;5;100,00;-500,00;0,99;0,00;EUR\n"
    )
    rows = parse_csv(csv_path)
    assert rows[0].row_number == 2  # line 1 is header, line 2 is first data row
    assert rows[1].row_number == 3
