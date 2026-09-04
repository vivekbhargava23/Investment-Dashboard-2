from datetime import date
from decimal import Decimal

from app.domain.csv_import import PlannedAction, PlannedRow, RowStatus
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.sync_completeness import check_completeness


def make_row(
    *,
    row_number: int = 1,
    trade_date: date = date(2026, 1, 5),
    reference: str = "ref-1",
    status: RowStatus = RowStatus.NEW,
    action: PlannedAction = PlannedAction.INSERT,
) -> PlannedRow:
    return PlannedRow(
        row_number=row_number,
        trade_date=trade_date,
        csv_type="Buy",
        isin="US1000000001",
        reference=reference,
        description="Apple Inc.",
        shares=Decimal("10"),
        price=Decimal("100"),
        amount=Decimal("-1000"),
        fee=None,
        tax=None,
        status=status,
        action=action,
        proposed_ticker="AAPL",
        feed_state="mapped",
    )


def make_tx(
    *,
    trade_date: date = date(2026, 1, 5),
    csv_reference: str | None = "ref-1",
    source: str = "scalable_csv",
) -> Transaction:
    eur = source != "manual"
    return Transaction(
        id=csv_reference or "manual-1",
        type=TransactionType.BUY,
        ticker="AAPL",
        trade_date=trade_date,
        shares=Decimal("10"),
        price_native=Money(
            amount=Decimal("100"), currency=Currency.EUR if eur else Currency.USD
        ),
        fx_rate_eur=Decimal("1") if eur else Decimal("0.9"),
        isin="US1000000001",
        csv_reference=csv_reference,
        source=source,
    )


def test_full_file_is_not_partial() -> None:
    rows = [make_row(reference="ref-1"), make_row(row_number=2, reference="ref-2")]
    book = [make_tx(csv_reference="ref-1")]

    result = check_completeness(rows, book)

    assert result.partial is False
    assert result.reason is None
    assert result.file_start == date(2026, 1, 5)
    assert result.book_start == date(2026, 1, 5)


def test_file_starting_after_the_book_is_partial() -> None:
    rows = [make_row(trade_date=date(2026, 6, 1), reference="ref-2")]
    book = [make_tx(trade_date=date(2026, 1, 5), csv_reference="ref-1")]

    result = check_completeness(rows, book)

    assert result.partial is True
    assert result.reason is not None
    assert "2026-06-01" in result.reason
    assert "2026-01-05" in result.reason


def test_file_starting_after_a_logged_file_start_is_partial() -> None:
    rows = [make_row(trade_date=date(2026, 6, 1))]

    result = check_completeness(rows, [], earliest_logged_file_start=date(2026, 1, 5))

    assert result.partial is True
    assert result.reason is not None
    assert "an earlier sync covered" in result.reason


def test_file_starting_on_the_logged_file_start_is_not_partial() -> None:
    rows = [make_row(trade_date=date(2026, 1, 5))]

    result = check_completeness(rows, [], earliest_logged_file_start=date(2026, 1, 5))

    assert result.partial is False


def test_book_reference_missing_from_the_file_is_partial() -> None:
    rows = [make_row(reference="ref-2")]
    book = [make_tx(csv_reference="ref-1")]

    result = check_completeness(rows, book)

    assert result.partial is True
    assert result.reason == "1 trade already in your book are not in this file."


def test_manual_transactions_never_make_a_file_partial() -> None:
    rows = [make_row(trade_date=date(2026, 6, 1), reference="ref-2")]
    book = [
        make_tx(trade_date=date(2026, 1, 5), csv_reference=None, source="manual"),
    ]

    result = check_completeness(rows, book)

    assert result.partial is False
    assert result.book_start is None


def test_empty_book_is_never_partial() -> None:
    rows = [make_row(trade_date=date(2026, 6, 1))]

    result = check_completeness(rows, [])

    assert result.partial is False
    assert result.file_start == date(2026, 6, 1)
    assert result.book_start is None


def test_cancelled_rows_do_not_set_the_file_start() -> None:
    rows = [
        make_row(
            trade_date=date(2020, 1, 1),
            reference="ref-0",
            status=RowStatus.CANCELLED_OR_EXPIRED,
            action=PlannedAction.SKIP,
        ),
        make_row(row_number=2, trade_date=date(2026, 1, 5), reference="ref-1"),
    ]

    result = check_completeness(rows, [])

    assert result.file_start == date(2026, 1, 5)


def test_empty_file_has_no_file_start_and_is_not_partial() -> None:
    result = check_completeness([], [make_tx()])

    assert result.partial is False
    assert result.file_start is None
