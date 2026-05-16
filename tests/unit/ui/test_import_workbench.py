"""Smoke + unit tests for app.ui.pages.import_workbench."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from app.domain.csv_import import ImportPlan, PlannedAction, PlannedRow, RowStatus
from app.domain.models import TransactionType
from app.domain.money import Currency, Money
from app.ui.pages.import_workbench import (
    _append_import_log,
    _build_transaction,
    _count_ready,
    _load_import_log,
    _md5,
    _write_backup,
)

# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_planned_row(
    *,
    reference: str = "REF001",
    status: RowStatus = RowStatus.NEW,
    action: PlannedAction = PlannedAction.INSERT,
    ticker: str | None = "SAP.DE",
    shares: Decimal | None = Decimal("10"),
    price: Decimal | None = Decimal("100"),
    csv_type: str = "Buy",
    conflict_tx_id: str | None = None,
) -> PlannedRow:
    return PlannedRow(
        row_number=2,
        trade_date=date(2026, 3, 1),
        csv_type=csv_type,
        isin="DE0007164600",
        reference=reference,
        description="SAP SE",
        shares=shares,
        price=price,
        amount=Decimal("-1000"),
        fee=Decimal("0.99"),
        tax=Decimal("0"),
        status=status,
        action=action,
        proposed_ticker=ticker,
        conflict_tx_id=conflict_tx_id,
    )


# ─── _build_transaction ───────────────────────────────────────────────────────

def test_build_transaction_buy() -> None:
    row = _make_planned_row()
    tx = _build_transaction(row)
    assert tx is not None
    assert tx.type == TransactionType.BUY
    assert tx.ticker == "SAP.DE"
    assert tx.shares == Decimal("10")
    assert tx.price_native == Money(amount=Decimal("100"), currency=Currency.EUR)
    assert tx.csv_reference == "REF001"
    assert tx.source == "scalable_csv"


def test_build_transaction_sell_with_tax() -> None:
    row = PlannedRow(
        row_number=3,
        trade_date=date(2026, 4, 1),
        csv_type="Sell",
        isin="DE0007164600",
        reference="REF002",
        description="SAP SE",
        shares=Decimal("5"),
        price=Decimal("120"),
        amount=Decimal("600"),
        fee=None,
        tax=Decimal("15"),
        status=RowStatus.NEW,
        action=PlannedAction.INSERT,
        proposed_ticker="SAP.DE",
    )
    tx = _build_transaction(row)
    assert tx is not None
    assert tx.type == TransactionType.SELL
    assert tx.notes is not None
    assert "tax_withheld_eur" in tx.notes
    assert "15" in tx.notes


def test_build_transaction_no_ticker_returns_none() -> None:
    row = _make_planned_row(ticker=None)
    assert _build_transaction(row) is None


def test_build_transaction_no_shares_returns_none() -> None:
    row = _make_planned_row(shares=None)
    assert _build_transaction(row) is None


def test_build_transaction_savings_plan_is_buy() -> None:
    row = _make_planned_row(csv_type="Savings plan")
    tx = _build_transaction(row)
    assert tx is not None
    assert tx.type == TransactionType.BUY


# ─── _count_ready ─────────────────────────────────────────────────────────────

def test_count_ready_all_new() -> None:
    plan = ImportPlan(rows=(
        _make_planned_row(reference="A"),
        _make_planned_row(reference="B"),
    ))
    assert _count_ready(plan, {}, set()) == 2


def test_count_ready_excluded_new_row() -> None:
    plan = ImportPlan(rows=(
        _make_planned_row(reference="A"),
        _make_planned_row(reference="B"),
    ))
    assert _count_ready(plan, {}, {"A"}) == 1


def test_count_ready_conflict_replace() -> None:
    plan = ImportPlan(rows=(
        _make_planned_row(
            reference="C",
            status=RowStatus.CONFLICT_WITH_MANUAL,
            action=PlannedAction.REPLACE,
            conflict_tx_id="manual-1",
        ),
    ))
    assert _count_ready(plan, {"C": "replace"}, set()) == 1


def test_count_ready_conflict_keep() -> None:
    plan = ImportPlan(rows=(
        _make_planned_row(
            reference="C",
            status=RowStatus.CONFLICT_WITH_MANUAL,
            action=PlannedAction.REPLACE,
            conflict_tx_id="manual-1",
        ),
    ))
    assert _count_ready(plan, {"C": "keep"}, set()) == 0


def test_count_ready_already_imported_not_counted() -> None:
    plan = ImportPlan(rows=(
        _make_planned_row(
            reference="D",
            status=RowStatus.ALREADY_IMPORTED,
            action=PlannedAction.NOOP,
        ),
    ))
    assert _count_ready(plan, {}, set()) == 0


# ─── import log ───────────────────────────────────────────────────────────────

def test_load_import_log_nonexistent(tmp_path: Path) -> None:
    assert _load_import_log(tmp_path / "log.json") == []


def test_append_import_log(tmp_path: Path) -> None:
    log_path = tmp_path / "import_log.json"
    _append_import_log(log_path, {"filename": "test.csv", "applied_count": 3})
    _append_import_log(log_path, {"filename": "test2.csv", "applied_count": 1})
    entries = _load_import_log(log_path)
    assert len(entries) == 2
    assert entries[0]["filename"] == "test.csv"
    assert entries[1]["applied_count"] == 1


# ─── backup rolling window ────────────────────────────────────────────────────

def test_backup_rolling_window_keeps_ten(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text('{"version":2,"transactions":[]}')
    backups_dir = tmp_path / "backups"
    backups_dir.mkdir()

    # Create 11 backup files with distinct names directly to test rolling-window logic
    for i in range(11):
        bak = backups_dir / f"portfolio.2026-01-{i+1:02d}_00-00-00-000000.json.bak"
        bak.write_text("{}")

    # Simulate one more write_backup call: should delete the oldest, leaving 10
    _write_backup(portfolio, backups_dir)

    remaining = list(backups_dir.glob("portfolio.*.json.bak"))
    assert len(remaining) == 10


# ─── md5 ──────────────────────────────────────────────────────────────────────

def test_md5_deterministic() -> None:
    data = b"hello world"
    assert _md5(data) == _md5(data)
    assert _md5(data) != _md5(b"other")


# ─── page import smoke ────────────────────────────────────────────────────────

def test_import_workbench_module_importable() -> None:
    import app.ui.pages.import_workbench as page
    assert callable(page.render)


def test_import_workbench_has_render_function() -> None:
    from app.ui.pages.import_workbench import render
    assert callable(render)
