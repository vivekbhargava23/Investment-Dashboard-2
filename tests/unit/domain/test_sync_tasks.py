from datetime import date
from decimal import Decimal

from app.domain.csv_import import PlannedAction, PlannedRow, RowStatus
from app.domain.feed_check import FeedCheck
from app.domain.reconcile import ReconcileRow
from app.domain.sync_completeness import CompletenessResult
from app.domain.sync_tasks import build_tasks

COMPLETE = CompletenessResult(
    partial=False, reason=None, file_start=date(2026, 1, 5), book_start=date(2026, 1, 5)
)


def rec(
    *,
    isin: str = "US1",
    name: str = "Apple Inc.",
    shares_csv: str = "10",
    shares_book: str = "10",
    cause: str | None = None,
    last_trade_price_eur: str | None = "100",
) -> ReconcileRow:
    csv_shares = Decimal(shares_csv)
    book_shares = Decimal(shares_book)
    diff = csv_shares - book_shares
    return ReconcileRow(
        isin=isin,
        name=name,
        shares_csv=csv_shares,
        shares_book=book_shares,
        diff=diff,
        matches=diff == Decimal("0"),
        cause=cause,
        last_trade_price_eur=(
            Decimal(last_trade_price_eur) if last_trade_price_eur else None
        ),
    )


def check(
    *,
    isin: str = "US1",
    ticker: str | None = "AAPL",
    status: str = "ok",
    avg_trade: str = "100",
    avg_close: str = "50",
) -> FeedCheck:
    return FeedCheck(
        isin=isin,
        ticker=ticker,
        status=status,  # type: ignore[arg-type]
        compared=3,
        median_deviation_pct=Decimal("50"),
        avg_trade_price_eur=Decimal(avg_trade),
        avg_close_eur=Decimal(avg_close),
        detail="Your trades averaged €100.00, AAPL closed at €50.00 (median 50.0% off).",
    )


def planned(
    *,
    isin: str = "US1",
    description: str = "Apple Inc.",
    trade_date: date = date(2026, 1, 5),
    shares: str = "10",
    price: str = "100",
) -> PlannedRow:
    return PlannedRow(
        row_number=2,
        trade_date=trade_date,
        csv_type="Buy",
        isin=isin,
        reference="ref-1",
        description=description,
        shares=Decimal(shares),
        price=Decimal(price),
        amount=Decimal("-1000"),
        fee=None,
        tax=None,
        status=RowStatus.CONFLICT_WITH_MANUAL,
        action=PlannedAction.REPLACE,
        proposed_ticker="AAPL",
        feed_state="mapped",
        conflict_tx_id="manual-1",
    )


def test_no_feed_task() -> None:
    [task] = build_tasks(
        [rec()], {}, {}, [], COMPLETE, {"US1": "unmapped"}
    )

    assert task.kind == "no_feed"
    assert task.headline == (
        "No price feed for Apple Inc. (10 shares, valued at last trade price)"
    )
    assert "last trade price" in task.detail
    assert task.impact_eur == Decimal("1000")


def test_no_feed_detail_never_implies_missing_trades() -> None:
    [task] = build_tasks([rec()], {}, {}, [], COMPLETE, {"US1": "unmapped"})
    assert "Every trade for this holding is in your book." in task.detail


def test_feed_suspicious_task() -> None:
    [task] = build_tasks(
        [rec()],
        {"US1": check(status="suspicious")},
        {},
        [],
        COMPLETE,
        {"US1": "mapped"},
    )

    assert task.kind == "feed_suspicious"
    assert task.headline == (
        "Price feed for Apple Inc. looks wrong — your trades avg €100.00, "
        "feed AAPL closed €50.00"
    )


def test_shares_differ_task() -> None:
    [task] = build_tasks(
        [rec(shares_csv="10", shares_book="8", cause="transfer imbalance: net +2 shares")],
        {"US1": check()},
        {},
        [],
        COMPLETE,
        {"US1": "mapped"},
    )

    assert task.kind == "shares_differ"
    assert task.headline == "Shares differ: Apple Inc. — Scalable 10, dashboard 8"
    assert task.detail == "transfer imbalance: net +2 shares"
    assert task.impact_eur == Decimal("200")


def test_sell_exceeds_task() -> None:
    [task] = build_tasks(
        [rec()],
        {"US1": check()},
        {"US1": "Sell of 12 exceeds 10 held on 2026-02-01"},
        [],
        COMPLETE,
        {"US1": "mapped"},
    )

    assert task.kind == "sell_exceeds"
    assert task.headline == "Sell exceeds shares held: Apple Inc."
    assert task.detail == "Sell of 12 exceeds 10 held on 2026-02-01"


def test_possible_duplicate_task() -> None:
    [task] = build_tasks([], {}, {}, [planned()], COMPLETE, {})

    assert task.kind == "possible_duplicate"
    assert task.headline == (
        "Possible duplicate: Apple Inc. on 2026-01-05 matches a manual entry"
    )


def test_partial_file_task_is_the_only_task() -> None:
    partial = CompletenessResult(
        partial=True,
        reason="This file starts 2026-06-01; your book starts 2026-01-05.",
        file_start=date(2026, 6, 1),
        book_start=date(2026, 1, 5),
    )

    tasks = build_tasks(
        [rec(shares_csv="10", shares_book="0")],
        {"US1": check(status="suspicious")},
        {"US1": "sell error"},
        [planned()],
        partial,
        {"US1": "unmapped"},
    )

    assert [t.kind for t in tasks] == ["partial_file"]
    assert tasks[0].headline == (
        "This file looks partial (starts 2026-06-01; your book starts 2026-01-05)"
    )
    assert "holdings comparison" in tasks[0].detail


def test_closed_position_without_a_feed_raises_no_task() -> None:
    tasks = build_tasks(
        [rec(shares_csv="0", shares_book="0")], {}, {}, [], COMPLETE, {"US1": "unmapped"}
    )

    assert tasks == []


def test_ignored_isin_raises_no_task() -> None:
    tasks = build_tasks(
        [rec()],
        {"US1": check(status="suspicious")},
        {},
        [],
        COMPLETE,
        {"US1": "ignored"},
    )

    assert tasks == []


def test_shares_differ_yields_to_a_more_specific_task_for_the_same_isin() -> None:
    tasks = build_tasks(
        [rec(shares_csv="10", shares_book="8")],
        {},
        {},
        [],
        COMPLETE,
        {"US1": "unmapped"},
    )

    assert [t.kind for t in tasks] == ["no_feed"]


def test_tasks_are_sorted_by_impact_descending() -> None:
    tasks = build_tasks(
        [
            rec(isin="US1", name="Small", shares_csv="1", last_trade_price_eur="10"),
            rec(isin="US2", name="Big", shares_csv="100", last_trade_price_eur="50"),
            rec(isin="US3", name="Mid", shares_csv="10", last_trade_price_eur="50"),
        ],
        {},
        {},
        [],
        COMPLETE,
        {"US1": "unmapped", "US2": "unmapped", "US3": "unmapped"},
    )

    assert [t.name for t in tasks] == ["Big", "Mid", "Small"]
    assert [t.impact_eur for t in tasks] == [
        Decimal("5000"),
        Decimal("500"),
        Decimal("10"),
    ]


def test_matching_isin_with_a_healthy_feed_raises_no_task() -> None:
    tasks = build_tasks([rec()], {"US1": check()}, {}, [], COMPLETE, {"US1": "mapped"})

    assert tasks == []
