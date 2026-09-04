from datetime import date
from decimal import Decimal

from app.domain.csv_import import PlannedAction, PlannedRow, RowStatus
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.reconcile import reconcile


def make_row(
    *,
    row_number: int = 1,
    trade_date: date = date(2026, 1, 5),
    csv_type: str = "Buy",
    isin: str = "US1000000001",
    reference: str = "ref-1",
    description: str = "Apple Inc.",
    shares: Decimal | None = Decimal("10"),
    price: Decimal | None = Decimal("100"),
    amount: Decimal | None = Decimal("-1000"),
    status: RowStatus = RowStatus.NEW,
    action: PlannedAction = PlannedAction.INSERT,
    proposed_ticker: str | None = "AAPL",
    conflict_tx_id: str | None = None,
) -> PlannedRow:
    return PlannedRow(
        row_number=row_number,
        trade_date=trade_date,
        csv_type=csv_type,
        isin=isin,
        reference=reference,
        description=description,
        shares=shares,
        price=price,
        amount=amount,
        fee=None,
        tax=None,
        status=status,
        action=action,
        proposed_ticker=proposed_ticker,
        feed_state="mapped",
        conflict_tx_id=conflict_tx_id,
        error_message=None,
        fx_rate_eur=None,
    )


def make_tx(
    *,
    id: str | None = None,
    type: TransactionType = TransactionType.BUY,
    ticker: str = "AAPL",
    trade_date: date = date(2026, 1, 5),
    shares: Decimal = Decimal("10"),
    isin: str | None = "US1000000001",
    source: str = "scalable_csv",
) -> Transaction:
    kwargs: dict = {
        "type": type,
        "ticker": ticker,
        "trade_date": trade_date,
        "shares": shares,
        "price_native": Money(amount=Decimal("100"), currency=Currency.USD),
        "fx_rate_eur": Decimal("0.9"),
        "isin": isin,
        "source": source,
    }
    if id is not None:
        kwargs["id"] = id
    return Transaction(**kwargs)


def test_matching_isin_has_no_cause() -> None:
    row = make_row(isin="US1", reference="ref-1")
    tx = make_tx(isin="US1", shares=Decimal("10"))

    [result] = reconcile([row], [tx])

    assert result.matches is True
    assert result.cause is None
    assert result.diff == Decimal("0")
    assert result.shares_csv == Decimal("10")
    assert result.shares_book == Decimal("10")


def test_cancelled_row_does_not_affect_expected_shares() -> None:
    row = make_row(
        isin="US2",
        csv_type="Buy",
        shares=Decimal("10"),
        status=RowStatus.CANCELLED_OR_EXPIRED,
        action=PlannedAction.SKIP,
    )

    [result] = reconcile([row], [])

    assert result.shares_csv == Decimal("0")
    assert result.matches is True
    assert result.cause is None


def test_unmapped_feed_state_is_never_a_cause() -> None:
    row = make_row(isin="US2B", reference="ref-2b", proposed_ticker=None)
    row = row.model_copy(update={"feed_state": "unmapped"})
    tx = make_tx(isin="US2B", ticker="US2B", shares=Decimal("10"))

    [result] = reconcile([row], [tx])

    assert result.matches is True
    assert result.cause is None


def test_validation_error_row_is_the_cause() -> None:
    row = make_row(
        isin="US3",
        reference="ref-3",
        status=RowStatus.VALIDATION_ERROR,
        action=PlannedAction.SKIP,
    )

    [result] = reconcile([row], [])

    assert result.matches is False
    assert result.cause == "1 row failed validation — see Details"


def test_transfer_imbalance_is_the_cause() -> None:
    row = make_row(
        isin="US4",
        csv_type="Security transfer",
        reference="ref-4",
        shares=Decimal("10"),
        price=None,
        amount=None,
    )

    [result] = reconcile([row], [])

    assert result.matches is False
    assert result.cause == "transfer imbalance: net +10 shares"


def test_manual_edit_of_a_csv_row_is_the_cause() -> None:
    row = make_row(isin="US5", reference="ref-5", shares=Decimal("10"))
    tx = make_tx(id="ref-5", isin="US5", shares=Decimal("4"), source="manual")

    [result] = reconcile([row], [tx])

    assert result.matches is False
    assert result.cause == "edited manually on the Manage page"


def test_corporate_action_is_the_cause() -> None:
    buy_row = make_row(isin="US6", reference="ref-6-buy", shares=Decimal("10"))
    ca_row = make_row(
        row_number=2,
        isin="US6",
        csv_type="Corporate action",
        reference="ref-6-ca",
        trade_date=date(2026, 2, 1),
        shares=None,
        price=None,
        amount=None,
        status=RowStatus.OUT_OF_SCOPE_V1,
        action=PlannedAction.SKIP,
    )

    [result] = reconcile([buy_row, ca_row], [])

    assert result.matches is False
    assert result.cause == "corporate action on 2026-02-01 — not imported"


def test_manual_entry_for_same_instrument_is_the_cause() -> None:
    row = make_row(isin="US7", reference="ref-7", proposed_ticker="TSLA")
    manual_tx = make_tx(isin=None, ticker="TSLA", shares=Decimal("3"), source="manual")

    [result] = reconcile([row], [manual_tx])

    assert result.matches is False
    assert result.cause == "includes a manual entry for the same instrument (3 shares)"


def test_conflict_with_manual_is_the_cause() -> None:
    row = make_row(
        isin="US8",
        reference="ref-8",
        status=RowStatus.CONFLICT_WITH_MANUAL,
        action=PlannedAction.REPLACE,
        conflict_tx_id="tx-8",
        proposed_ticker=None,
    )

    [result] = reconcile([row], [])

    assert result.matches is False
    assert result.cause == "possible duplicate of a manual entry — decide on the Sync tab"


def test_unexplained_diff_falls_back_to_unknown() -> None:
    row = make_row(isin="US9", reference="ref-9", proposed_ticker=None)

    [result] = reconcile([row], [])

    assert result.matches is False
    assert result.cause == "unknown — check Details"


def test_partial_file_returns_empty_list() -> None:
    row = make_row(isin="US10", reference="ref-10")

    assert reconcile([row], [], partial=True) == []


def test_sorted_by_impact_descending_then_isin() -> None:
    small = make_row(
        isin="US11",
        reference="ref-11",
        shares=Decimal("1"),
        price=Decimal("10"),
        proposed_ticker=None,
    )
    large = make_row(
        isin="US12",
        reference="ref-12",
        shares=Decimal("5"),
        price=Decimal("100"),
        proposed_ticker=None,
    )

    results = reconcile([small, large], [])

    assert [r.isin for r in results] == ["US12", "US11"]
