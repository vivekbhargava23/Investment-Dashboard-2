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
    proposed_type: str | None = None,
    asset_type: str = "Security",
    conflict_tx_id: str | None = None,
) -> PlannedRow:
    return PlannedRow(
        row_number=row_number,
        trade_date=trade_date,
        csv_type=csv_type,
        asset_type=asset_type,
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
        proposed_type=proposed_type,
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


def test_name_comes_from_the_latest_trade_not_a_later_cash_row() -> None:
    trade = make_row(
        isin="US9", reference="ref-1", description="Vanguard FTSE All-World",
        trade_date=date(2026, 3, 1),
    )
    dividend = make_row(
        isin="US9",
        row_number=2,
        reference="ref-2",
        description="Dividend Vanguard FTSE All-World",
        csv_type="Distribution",
        trade_date=date(2026, 3, 2),
        shares=None,
        status=RowStatus.OUT_OF_SCOPE_V1,
        action=PlannedAction.SKIP,
    )

    [result] = reconcile([trade, dividend], [])

    assert result.name == "Vanguard FTSE All-World"


# ─── corporate actions (TICKET-SYNC-7) ────────────────────────────────────────

def test_corporate_action_security_leg_closes_the_position() -> None:
    """26 bought, 26 knocked out by a corporate action → the CSV side is 0."""
    rows = [
        make_row(reference="buy", shares=Decimal("26"), price=Decimal("3")),
        make_row(
            row_number=2,
            trade_date=date(2026, 2, 1),
            csv_type="Corporate action",
            reference="ca",
            shares=Decimal("26"),
            price=Decimal("0.001"),
            amount=Decimal("-0.026"),
            proposed_type="sell",
        ),
    ]
    txs = [
        make_tx(id="buy", shares=Decimal("26")),
        make_tx(id="ca", type=TransactionType.SELL, shares=Decimal("26")),
    ]
    result = reconcile(rows, txs)
    assert len(result) == 1
    assert result[0].shares_csv == Decimal("0")
    assert result[0].shares_book == Decimal("0")
    assert result[0].matches
    assert result[0].cause is None


def test_corporate_action_cash_leg_moves_no_shares() -> None:
    rows = [
        make_row(reference="buy", shares=Decimal("26"), price=Decimal("3")),
        make_row(
            row_number=2,
            csv_type="Corporate action",
            asset_type="Cash",
            reference="ca",
            shares=None,
            price=None,
            amount=Decimal("0.03"),
        ),
    ]
    result = reconcile(rows, [make_tx(id="buy", shares=Decimal("26"))])
    assert result[0].shares_csv == Decimal("26")
    assert result[0].matches


def test_a_knocked_out_holding_is_not_valued_at_the_knock_out_price() -> None:
    rows = [
        make_row(reference="buy", shares=Decimal("26"), price=Decimal("3")),
        make_row(
            row_number=2,
            trade_date=date(2026, 2, 1),
            csv_type="Corporate action",
            reference="ca",
            shares=Decimal("26"),
            price=Decimal("0.001"),
            proposed_type="sell",
        ),
    ]
    result = reconcile(rows, [])
    assert result[0].last_trade_price_eur == Decimal("3")
    assert result[0].name == "Apple Inc."


def test_a_corporate_action_no_longer_explains_a_share_difference() -> None:
    """Cause rule 6 is gone: the leg is imported, so it cannot be the excuse."""
    rows = [
        make_row(reference="buy", shares=Decimal("26"), price=Decimal("3")),
        make_row(
            row_number=2,
            trade_date=date(2026, 2, 1),
            csv_type="Corporate action",
            reference="ca",
            shares=Decimal("26"),
            price=Decimal("0.001"),
            proposed_type="sell",
        ),
    ]
    result = reconcile(rows, [make_tx(id="buy", shares=Decimal("26"))])
    assert not result[0].matches
    assert result[0].cause == "unknown — check Details"


# ─── write-off (TICKET-SYNC-7) ────────────────────────────────────────────────

def test_a_written_off_holding_reconciles_at_zero() -> None:
    """26 bought, 26 written off by hand → both sides read 0 and there is no cause."""
    rows = [make_row(reference="buy", shares=Decimal("26"), price=Decimal("3"))]
    txs = [
        make_tx(id="buy", shares=Decimal("26")),
        make_tx(
            id="writeoff-US1000000001-2026-03-01",
            type=TransactionType.SELL,
            shares=Decimal("26"),
            source="write_off",
        ),
    ]

    [result] = reconcile(rows, txs)

    assert result.shares_csv == Decimal("0")
    assert result.shares_book == Decimal("0")
    assert result.matches
    assert result.cause is None


def test_a_partial_write_off_leaves_the_rest_matching() -> None:
    rows = [make_row(reference="buy", shares=Decimal("26"), price=Decimal("3"))]
    txs = [
        make_tx(id="buy", shares=Decimal("26")),
        make_tx(
            id="writeoff-1",
            type=TransactionType.SELL,
            shares=Decimal("10"),
            source="write_off",
        ),
    ]

    [result] = reconcile(rows, txs)

    assert result.shares_csv == Decimal("16")
    assert result.shares_book == Decimal("16")
    assert result.matches


def test_a_write_off_is_never_the_cause_of_a_difference() -> None:
    rows = [make_row(reference="buy", shares=Decimal("26"), price=Decimal("3"))]
    txs = [
        make_tx(
            id="writeoff-1",
            type=TransactionType.SELL,
            shares=Decimal("10"),
            source="write_off",
        ),
    ]

    [result] = reconcile(rows, txs)

    assert not result.matches
    assert result.cause is not None
    assert "manual entry" not in result.cause
