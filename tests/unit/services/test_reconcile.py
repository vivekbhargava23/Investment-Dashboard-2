from datetime import date
from decimal import Decimal

from app.domain.csv_import import ImportPlan, PlannedAction, PlannedRow, RowStatus
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.services.reconcile import reconcile_book
from tests.fakes.repository import FakeTransactionRepository


def test_reconcile_book_loads_from_the_port_and_delegates_to_the_domain() -> None:
    row = PlannedRow(
        row_number=1,
        trade_date=date(2026, 1, 5),
        csv_type="Buy",
        isin="US1000000001",
        reference="ref-1",
        description="Apple Inc.",
        shares=Decimal("10"),
        price=Decimal("100"),
        amount=Decimal("-1000"),
        fee=None,
        tax=None,
        status=RowStatus.NEW,
        action=PlannedAction.INSERT,
        proposed_ticker="AAPL",
        feed_state="mapped",
    )
    plan = ImportPlan(rows=(row,))
    tx = Transaction(
        type=TransactionType.BUY,
        ticker="AAPL",
        trade_date=date(2026, 1, 5),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("100"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9"),
        isin="US1000000001",
        source="scalable_csv",
    )
    repo = FakeTransactionRepository([tx])

    [result] = reconcile_book(plan, repo)

    assert result.isin == "US1000000001"
    assert result.matches is True
    assert result.cause is None
