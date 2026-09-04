"""Unit tests for app.services.isin_remap."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pytest

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.tax.classification import InstrumentKind
from app.ports.repository import TransactionNotFoundError
from app.services.isin_remap import (
    TickerAlreadyMappedError,
    change_feed,
    check_consistency,
    count_transactions_for_isin,
    repair,
    rewrite_ticker_for_isin,
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


# ---------------------------------------------------------------------------
# change_feed (ADR-014 rules 2 and 4)
# ---------------------------------------------------------------------------


def _doc(**entries: IsinMapping) -> IsinMapDocument:
    return IsinMapDocument(version=2, entries=dict(entries))


def _mapped(ticker: str, name: str = "Some Instrument") -> IsinMapping:
    return IsinMapping(
        ticker=ticker,
        name=name,
        status="mapped",
        instrument_kind=InstrumentKind.AKTIE,
    )


def test_change_feed_rewrites_every_row_and_returns_count() -> None:
    repo = FakeRepo([
        _tx("tx1", "US67066G1040", "US67066G1040"),
        _tx("tx2", "US67066G1040", "US67066G1040"),
        _tx("tx3", "AAPL", "US0378331005"),
    ])
    doc = _doc(US67066G1040=IsinMapping(ticker=None, name="Nvidia", status="unmapped"))

    new_doc, count = change_feed(
        "US67066G1040", "NVDA", InstrumentKind.AKTIE, doc, repo
    )

    assert count == 2
    assert {tx.id: tx.ticker for tx in repo.load_all()} == {
        "tx1": "NVDA",
        "tx2": "NVDA",
        "tx3": "AAPL",
    }
    entry = new_doc.entries["US67066G1040"]
    assert entry.ticker == "NVDA"
    assert entry.status == "mapped"
    assert entry.name == "Nvidia"
    assert entry.instrument_kind is InstrumentKind.AKTIE
    # The caller saves the map; change_feed never mutates the input document.
    assert doc.entries["US67066G1040"].ticker is None


def test_change_feed_names_a_brand_new_entry_after_its_isin() -> None:
    new_doc, _ = change_feed(
        "US0378331005", "AAPL", InstrumentKind.AKTIE, _doc(), FakeRepo()
    )
    assert new_doc.entries["US0378331005"].name == "US0378331005"


def test_change_feed_with_no_transactions_returns_zero() -> None:
    repo = FakeRepo([_tx("tx1", "AAPL", "US0378331005")])
    _, count = change_feed(
        "US67066G1040", "NVDA", InstrumentKind.AKTIE, _doc(), repo
    )
    assert count == 0
    assert repo.save_calls == 0


def test_change_feed_refuses_a_ticker_another_mapped_isin_already_uses() -> None:
    repo = FakeRepo([_tx("tx1", "US67066G1040", "US67066G1040")])
    doc = _doc(US0378331005=_mapped("NVDA", "Nvidia (old ISIN)"))

    with pytest.raises(TickerAlreadyMappedError) as excinfo:
        change_feed("US67066G1040", "NVDA", InstrumentKind.AKTIE, doc, repo)

    assert excinfo.value.ticker == "NVDA"
    assert excinfo.value.other_isin == "US0378331005"
    # Nothing was written: the guard runs before the rewrite.
    assert repo.save_calls == 0
    assert repo.load_all()[0].ticker == "US67066G1040"


def test_change_feed_allows_a_shared_ticker_when_explicitly_confirmed() -> None:
    repo = FakeRepo([_tx("tx1", "US67066G1040", "US67066G1040")])
    doc = _doc(US0378331005=_mapped("NVDA", "Nvidia (old ISIN)"))

    new_doc, count = change_feed(
        "US67066G1040",
        "NVDA",
        InstrumentKind.AKTIE,
        doc,
        repo,
        allow_shared_ticker=True,
    )

    assert count == 1
    assert new_doc.entries["US67066G1040"].ticker == "NVDA"
    assert new_doc.entries["US0378331005"].ticker == "NVDA"


def test_change_feed_ignores_a_ticker_held_by_an_ignored_entry() -> None:
    doc = _doc(US0378331005=IsinMapping(ticker="NVDA", name="junk", status="ignored"))
    new_doc, _ = change_feed(
        "US67066G1040", "NVDA", InstrumentKind.AKTIE, doc, FakeRepo()
    )
    assert new_doc.entries["US67066G1040"].ticker == "NVDA"


def test_change_feed_remapping_the_same_isin_is_not_a_collision() -> None:
    doc = _doc(US67066G1040=_mapped("NVDA"))
    new_doc, _ = change_feed(
        "US67066G1040", "NVDA", InstrumentKind.AKTIENFONDS, doc, FakeRepo()
    )
    assert new_doc.entries["US67066G1040"].instrument_kind is InstrumentKind.AKTIENFONDS


# ---------------------------------------------------------------------------
# check_consistency / repair
# ---------------------------------------------------------------------------


def test_check_consistency_is_empty_when_the_book_agrees_with_the_map() -> None:
    txs = [_tx("tx1", "NVDA", "US67066G1040")]
    assert check_consistency(_doc(US67066G1040=_mapped("NVDA")), txs) == []


def test_check_consistency_finds_a_stale_stored_ticker() -> None:
    txs = [_tx("tx1", "NVDA", "US67066G1040"), _tx("tx2", "NVDA.DE", "US67066G1040")]
    assert check_consistency(_doc(US67066G1040=_mapped("NVDA")), txs) == [
        ("US67066G1040", "NVDA", "NVDA.DE")
    ]


def test_check_consistency_ignores_unmapped_and_ignored_entries() -> None:
    doc = _doc(
        US67066G1040=IsinMapping(ticker=None, name="n", status="unmapped"),
        US0378331005=IsinMapping(ticker="AAPL", name="a", status="ignored"),
    )
    txs = [
        _tx("tx1", "US67066G1040", "US67066G1040"),
        _tx("tx2", "AAPL.DE", "US0378331005"),
    ]
    assert check_consistency(doc, txs) == []


def test_repair_fixes_a_mismatch_and_is_idempotent() -> None:
    repo = FakeRepo([
        _tx("tx1", "NVDA.DE", "US67066G1040"),
        _tx("tx2", "NVDA", "US67066G1040"),
        _tx("tx3", "AAPL", "US0378331005"),
        _tx("tx4", "SAP.DE", isin=None, source="manual"),
    ])
    doc = _doc(US67066G1040=_mapped("NVDA"), US0378331005=_mapped("AAPL"))

    assert check_consistency(doc, repo.load_all())
    assert repair(doc, repo) == 1
    assert check_consistency(doc, repo.load_all()) == []
    assert {tx.id: tx.ticker for tx in repo.load_all()} == {
        "tx1": "NVDA",
        "tx2": "NVDA",
        "tx3": "AAPL",
        "tx4": "SAP.DE",
    }

    # Second run has nothing to do and leaves the repository untouched.
    calls_before = repo.save_calls
    assert repair(doc, repo) == 0
    assert repo.save_calls == calls_before
