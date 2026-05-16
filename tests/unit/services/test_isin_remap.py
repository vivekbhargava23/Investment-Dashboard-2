"""Unit tests for app.services.isin_remap."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.ports.repository import TransactionNotFoundError
from app.services.isin_remap import count_transactions_for_isin, rewrite_ticker_for_isin

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
    ticker: str,
    isin: str | None = None,
    *,
    source: str = "scalable_csv",
) -> Transaction:
    return Transaction(
        id=tx_id,
        type=TransactionType.BUY,
        ticker=ticker,
        trade_date=date(2026, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
        isin=isin,
        source=source,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# rewrite_ticker_for_isin
# ---------------------------------------------------------------------------


def test_rewrite_empty_repo_returns_zero() -> None:
    repo = FakeRepo()
    result = rewrite_ticker_for_isin(repo, "US67066G1040", "NVDA2")
    assert result == 0
    assert repo.save_calls == 0


def test_rewrite_no_match_returns_zero() -> None:
    repo = FakeRepo([_tx("tx1", "AAPL", "US0378331005")])
    result = rewrite_ticker_for_isin(repo, "US67066G1040", "NVDA2")
    assert result == 0
    assert repo.save_calls == 0


def test_rewrite_single_match_returns_one() -> None:
    tx = _tx("tx1", "NVDA", "US67066G1040")
    repo = FakeRepo([tx])
    result = rewrite_ticker_for_isin(repo, "US67066G1040", "NVDA2")
    assert result == 1
    assert repo.load_all()[0].ticker == "NVDA2"


def test_rewrite_multi_match_rewrites_all() -> None:
    txs = [
        _tx("tx1", "NVDA", "US67066G1040"),
        _tx("tx2", "NVDA", "US67066G1040"),
        _tx("tx3", "NVDA", "US67066G1040"),
        _tx("tx4", "AAPL", "US0378331005"),
        _tx("tx5", "AAPL", "US0378331005"),
    ]
    repo = FakeRepo(txs)
    result = rewrite_ticker_for_isin(repo, "US67066G1040", "NVDA2")
    assert result == 3
    loaded = {tx.id: tx for tx in repo.load_all()}
    assert loaded["tx1"].ticker == "NVDA2"
    assert loaded["tx2"].ticker == "NVDA2"
    assert loaded["tx3"].ticker == "NVDA2"
    assert loaded["tx4"].ticker == "AAPL"
    assert loaded["tx5"].ticker == "AAPL"


def test_rewrite_preserves_all_other_fields() -> None:
    tx = Transaction(
        id="ref-001",
        type=TransactionType.BUY,
        ticker="NVDA",
        trade_date=date(2025, 6, 15),
        shares=Decimal("4.5"),
        price_native=Money(amount=Decimal("82.65"), currency=Currency.EUR),
        fees_native=Money(amount=Decimal("0.99"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
        isin="US67066G1040",
        csv_reference="ref-001",
        source="scalable_csv",
        notes="buy note",
    )
    repo = FakeRepo([tx])
    rewrite_ticker_for_isin(repo, "US67066G1040", "NVDA.DE")
    rewritten = repo.load_all()[0]
    assert rewritten.ticker == "NVDA.DE"
    assert rewritten.id == tx.id
    assert rewritten.shares == tx.shares
    assert rewritten.price_native == tx.price_native
    assert rewritten.fees_native == tx.fees_native
    assert rewritten.fx_rate_eur == tx.fx_rate_eur
    assert rewritten.isin == tx.isin
    assert rewritten.csv_reference == tx.csv_reference
    assert rewritten.source == tx.source
    assert rewritten.notes == tx.notes


# ---------------------------------------------------------------------------
# count_transactions_for_isin
# ---------------------------------------------------------------------------


def test_count_empty_repo() -> None:
    assert count_transactions_for_isin(FakeRepo(), "US67066G1040") == 0


def test_count_no_match() -> None:
    repo = FakeRepo([_tx("tx1", "AAPL", "US0378331005")])
    assert count_transactions_for_isin(repo, "US67066G1040") == 0


def test_count_single_match() -> None:
    repo = FakeRepo([_tx("tx1", "NVDA", "US67066G1040")])
    assert count_transactions_for_isin(repo, "US67066G1040") == 1


def test_count_multiple_matches() -> None:
    txs = [
        _tx("tx1", "NVDA", "US67066G1040"),
        _tx("tx2", "NVDA", "US67066G1040"),
        _tx("tx3", "AAPL", "US0378331005"),
    ]
    assert count_transactions_for_isin(FakeRepo(txs), "US67066G1040") == 2


def test_count_none_isin_not_matched() -> None:
    repo = FakeRepo([_tx("tx1", "NVDA", isin=None)])
    assert count_transactions_for_isin(repo, "US67066G1040") == 0
