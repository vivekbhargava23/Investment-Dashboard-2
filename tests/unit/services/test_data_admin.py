"""Unit tests for app.services.data_admin."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.ports.repository import TransactionNotFoundError
from app.services.data_admin import (
    count_transactions,
    erase_all_transactions,
    erase_transactions,
)

# ---------------------------------------------------------------------------
# Fake repo
# ---------------------------------------------------------------------------


class FakeRepo:
    def __init__(self, txs: list[Transaction] | None = None) -> None:
        self._txs: list[Transaction] = list(txs or [])
        self.save_calls: int = 0

    def load_all(self) -> list[Transaction]:
        return list(self._txs)

    def save_all(self, transactions: Sequence[Transaction]) -> None:
        self._txs = list(transactions)
        self.save_calls += 1

    def add(self, tx: Transaction) -> None:
        self._txs.append(tx)

    def update(self, tx: Transaction) -> None:
        for i, t in enumerate(self._txs):
            if t.id == tx.id:
                self._txs[i] = tx
                return
        raise TransactionNotFoundError(tx.id)

    def delete(self, tx_id: str) -> None:
        self._txs = [t for t in self._txs if t.id != tx_id]

    def get(self, tx_id: str) -> Transaction:
        for t in self._txs:
            if t.id == tx_id:
                return t
        raise TransactionNotFoundError(tx_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tx(
    tx_id: str,
    *,
    source: str = "scalable_csv",
    trade_date: date = date(2026, 1, 1),
) -> Transaction:
    # AAPL trades in USD; manual rows are validated against ticker inference, so
    # record them USD-native. Broker-sourced rows skip that check (ADR-005).
    return Transaction(
        id=tx_id,
        type=TransactionType.BUY,
        ticker="AAPL",
        trade_date=trade_date,
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("100"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9"),
        source=source,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# erase_all_transactions
# ---------------------------------------------------------------------------


def test_erase_all_empties_book_and_returns_count() -> None:
    repo = FakeRepo([_tx("a"), _tx("b"), _tx("c")])
    removed = erase_all_transactions(repo)
    assert removed == 3
    assert repo.load_all() == []
    assert repo.save_calls == 1


def test_erase_all_empty_book_is_a_noop() -> None:
    repo = FakeRepo()
    removed = erase_all_transactions(repo)
    assert removed == 0
    assert repo.save_calls == 0


# ---------------------------------------------------------------------------
# erase_transactions — by source
# ---------------------------------------------------------------------------


def test_scoped_erase_by_source_deletes_only_matching() -> None:
    repo = FakeRepo([
        _tx("csv1", source="scalable_csv"),
        _tx("man1", source="manual"),
        _tx("csv2", source="scalable_csv"),
    ])
    removed = erase_transactions(repo, source="scalable_csv")
    assert removed == 2
    remaining = repo.load_all()
    assert [t.id for t in remaining] == ["man1"]
    assert repo.save_calls == 1


def test_scoped_erase_by_manual_source_leaves_csv() -> None:
    repo = FakeRepo([
        _tx("csv1", source="scalable_csv"),
        _tx("man1", source="manual"),
    ])
    removed = erase_transactions(repo, source="manual")
    assert removed == 1
    assert [t.id for t in repo.load_all()] == ["csv1"]


# ---------------------------------------------------------------------------
# erase_transactions — by date range
# ---------------------------------------------------------------------------


def test_scoped_erase_by_date_range_inclusive() -> None:
    repo = FakeRepo([
        _tx("old", trade_date=date(2024, 1, 1)),
        _tx("from", trade_date=date(2025, 1, 1)),
        _tx("mid", trade_date=date(2025, 6, 1)),
        _tx("to", trade_date=date(2025, 12, 31)),
        _tx("new", trade_date=date(2026, 1, 1)),
    ])
    removed = erase_transactions(
        repo, date_from=date(2025, 1, 1), date_to=date(2025, 12, 31)
    )
    assert removed == 3
    assert [t.id for t in repo.load_all()] == ["old", "new"]


def test_scoped_erase_open_ended_to_date() -> None:
    repo = FakeRepo([
        _tx("old", trade_date=date(2024, 1, 1)),
        _tx("new", trade_date=date(2026, 1, 1)),
    ])
    removed = erase_transactions(repo, date_to=date(2024, 12, 31))
    assert removed == 1
    assert [t.id for t in repo.load_all()] == ["new"]


def test_scoped_erase_source_and_date_combined() -> None:
    repo = FakeRepo([
        _tx("csv_old", source="scalable_csv", trade_date=date(2024, 1, 1)),
        _tx("csv_new", source="scalable_csv", trade_date=date(2026, 1, 1)),
        _tx("man_new", source="manual", trade_date=date(2026, 1, 1)),
    ])
    removed = erase_transactions(
        repo, source="scalable_csv", date_from=date(2025, 1, 1)
    )
    assert removed == 1
    assert sorted(t.id for t in repo.load_all()) == ["csv_old", "man_new"]


# ---------------------------------------------------------------------------
# erase_transactions — empty / no-match selections
# ---------------------------------------------------------------------------


def test_empty_selection_deletes_nothing() -> None:
    repo = FakeRepo([_tx("a"), _tx("b")])
    removed = erase_transactions(repo)
    assert removed == 0
    assert len(repo.load_all()) == 2
    assert repo.save_calls == 0


def test_no_match_leaves_repo_untouched() -> None:
    repo = FakeRepo([_tx("man1", source="manual")])
    removed = erase_transactions(repo, source="scalable_csv")
    assert removed == 0
    assert repo.save_calls == 0


# ---------------------------------------------------------------------------
# count_transactions (preview mirror)
# ---------------------------------------------------------------------------


def test_count_matches_erase_without_mutating() -> None:
    repo = FakeRepo([
        _tx("csv1", source="scalable_csv"),
        _tx("man1", source="manual"),
        _tx("csv2", source="scalable_csv"),
    ])
    assert count_transactions(repo, source="scalable_csv") == 2
    # preview is read-only
    assert repo.save_calls == 0
    assert len(repo.load_all()) == 3


def test_count_empty_selection_is_zero() -> None:
    repo = FakeRepo([_tx("a"), _tx("b")])
    assert count_transactions(repo) == 0
