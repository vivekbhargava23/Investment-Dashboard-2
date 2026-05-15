"""Unit tests for app.adapters.scalable_csv.importer."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.scalable_csv.importer import run_import
from app.adapters.scalable_csv.parser import parse_csv
from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.ports.repository import TransactionNotFoundError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "scalable_csv"

# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------


class FakeTransactionRepository:
    def __init__(self, transactions: list[Transaction] | None = None) -> None:
        self._txs: list[Transaction] = list(transactions or [])

    def load_all(self) -> list[Transaction]:
        return list(self._txs)

    def save_all(self, transactions: Sequence[Transaction]) -> None:
        self._txs = list(transactions)

    def add(self, transaction: Transaction) -> None:
        self._txs.append(transaction)

    def update(self, transaction: Transaction) -> None:
        for i, tx in enumerate(self._txs):
            if tx.id == transaction.id:
                self._txs[i] = transaction
                return
        raise TransactionNotFoundError(transaction.id)

    def delete(self, transaction_id: str) -> None:
        self._txs = [tx for tx in self._txs if tx.id != transaction_id]

    def get(self, transaction_id: str) -> Transaction:
        for tx in self._txs:
            if tx.id == transaction_id:
                return tx
        raise TransactionNotFoundError(transaction_id)


class FakeIsinMapRepository:
    def __init__(self, doc: IsinMapDocument | None = None) -> None:
        self._doc = doc or IsinMapDocument()

    def load(self) -> IsinMapDocument:
        return self._doc

    def save(self, doc: IsinMapDocument) -> None:
        self._doc = doc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_eur_tx(ref: str, ticker: str, trade_date: date) -> Transaction:
    return Transaction(
        id=ref,
        type=TransactionType.BUY,
        ticker=ticker,
        trade_date=trade_date,
        shares=Decimal("1"),
        price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )


def _isin_map_with(*entries: tuple[str, str, str]) -> IsinMapDocument:
    """Build IsinMapDocument from (isin, ticker, name) tuples (all mapped)."""
    return IsinMapDocument(
        entries={
            isin: IsinMapping(ticker=ticker, name=name, status="mapped")
            for isin, ticker, name in entries
        }
    )


# ISIN → EUR-denominated ticker mappings used in fixtures
_SAP_ISIN = "DE0007164600"
_RHM_ISIN = "DE0007030009"
_VWCE_ISIN = "IE00B3RBWM25"
_PARROT_ISIN = "FR0004038263"

_FULL_MAP = _isin_map_with(
    (_SAP_ISIN, "SAP.DE", "SAP SE"),
    (_RHM_ISIN, "RHM.DE", "Rheinmetall AG"),
    (_VWCE_ISIN, "VWCE.DE", "Vanguard FTSE All-World"),
    (_PARROT_ISIN, "PAR.PA", "Parrot SA"),
)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_empty_portfolio_happy_path():
    """4-row CSV, all mapped → 4 transactions with correct fields."""
    rows = parse_csv(FIXTURES / "happy_path.csv")
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository(_FULL_MAP)

    summary = run_import(rows, "happy_path.csv", tx_repo, map_repo)

    assert summary.new_transactions == 4
    assert summary.already_existing == 0
    assert summary.unmapped == 0
    txs = tx_repo.load_all()
    assert len(txs) == 4

    buy = next(t for t in txs if t.id == "REF001")
    assert buy.ticker == "SAP.DE"
    assert buy.type == TransactionType.BUY
    assert buy.trade_date == date(2026, 3, 1)
    assert buy.shares == Decimal("10")
    assert buy.price_native == Money(amount=Decimal("100.00"), currency=Currency.EUR)
    assert buy.fx_rate_eur == Decimal("1")
    assert buy.fees_native == Money(amount=Decimal("0.99"), currency=Currency.EUR)

    # Savings plan maps to BUY
    savings = next(t for t in txs if t.id == "REF003")
    assert savings.type == TransactionType.BUY
    assert savings.shares == Decimal("7.054176")

    # Security transfer maps to BUY, blank fee → None
    transfer = next(t for t in txs if t.id == "REF004")
    assert transfer.type == TransactionType.BUY
    assert transfer.fees_native is None

    # price_native.currency is EUR for all
    for tx in txs:
        assert tx.price_native.currency == Currency.EUR
        assert tx.fx_rate_eur == Decimal("1")


def test_idempotent_reimport():
    """Running the same CSV twice adds 0 new transactions the second time."""
    rows = parse_csv(FIXTURES / "happy_path.csv")
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository(_FULL_MAP)

    s1 = run_import(rows, "happy_path.csv", tx_repo, map_repo)
    assert s1.new_transactions == 4

    s2 = run_import(rows, "happy_path.csv", tx_repo, map_repo)
    assert s2.new_transactions == 0
    assert s2.already_existing == 4
    assert len(tx_repo.load_all()) == 4


def test_partial_csv_update(tmp_path: Path):
    """Existing transactions not in new CSV are preserved; new ones are added."""
    existing = [
        _make_eur_tx("A", "SAP.DE", date(2026, 1, 1)),
        _make_eur_tx("REF001", "SAP.DE", date(2026, 3, 1)),
        _make_eur_tx("REF002", "RHM.DE", date(2026, 3, 2)),
    ]
    tx_repo = FakeTransactionRepository(existing)
    map_repo = FakeIsinMapRepository(_FULL_MAP)

    rows = parse_csv(FIXTURES / "happy_path.csv")  # contains REF001-REF004
    summary = run_import(rows, "happy_path.csv", tx_repo, map_repo)

    # REF001, REF002 already exist → already_existing=2; REF003, REF004 are new
    assert summary.already_existing == 2
    assert summary.new_transactions == 2

    all_ids = {tx.id for tx in tx_repo.load_all()}
    assert "A" in all_ids  # preserved even though not in CSV
    assert "REF001" in all_ids
    assert "REF002" in all_ids
    assert "REF003" in all_ids
    assert "REF004" in all_ids
    assert len(all_ids) == 5


def test_unmapped_isin_is_quarantined(tmp_path: Path):
    """Rows with unmapped ISINs are counted and listed; mapped rows still import."""
    # Only SAP is mapped; RHM, VWCE, Parrot are absent → unmapped on first run
    partial_map = _isin_map_with((_SAP_ISIN, "SAP.DE", "SAP SE"))
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository(partial_map)

    rows = parse_csv(FIXTURES / "happy_path.csv")
    summary = run_import(rows, "happy_path.csv", tx_repo, map_repo)

    assert summary.new_transactions == 1  # only SAP buy goes through
    assert summary.unmapped == 3  # RHM sell, VWCE savings plan, Parrot transfer
    unmapped_isins = {isin for isin, _ in summary.unmapped_isins}
    assert _RHM_ISIN in unmapped_isins
    assert _VWCE_ISIN in unmapped_isins
    assert _PARROT_ISIN in unmapped_isins


def test_new_isin_first_time_seen_becomes_unmapped():
    """ISINs absent from isin_map.json are added as unmapped entries."""
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository()  # empty map

    rows = parse_csv(FIXTURES / "happy_path.csv")
    summary = run_import(rows, "happy_path.csv", tx_repo, map_repo)

    assert summary.new_transactions == 0
    assert summary.unmapped == 4  # all 4 ISINs are new and unmapped

    doc = map_repo.load()
    assert _SAP_ISIN in doc.entries
    assert doc.entries[_SAP_ISIN].status == "unmapped"
    assert doc.entries[_SAP_ISIN].ticker is None


def test_status_filter_counts():
    """Cancelled/Expired/Rejected rows are counted in status_filtered."""
    rows = parse_csv(FIXTURES / "mixed_statuses.csv")
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository(_FULL_MAP)

    summary = run_import(rows, "mixed_statuses.csv", tx_repo, map_repo)

    assert summary.status_filtered == 3
    assert summary.status_filtered_detail.get("Cancelled") == 1
    assert summary.status_filtered_detail.get("Expired") == 1
    assert summary.status_filtered_detail.get("Rejected") == 1
    assert summary.in_scope == 2
    assert summary.new_transactions == 2


def test_out_of_scope_type_filter():
    """Deposit/Distribution/Interest/Taxes/Corporate-action rows go to out_of_scope."""
    rows = parse_csv(FIXTURES / "out_of_scope_types.csv")
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository(_FULL_MAP)

    summary = run_import(rows, "out_of_scope_types.csv", tx_repo, map_repo)

    assert summary.out_of_scope == 5  # Deposit, Distribution, Interest, Taxes, Corporate action
    assert summary.in_scope == 1  # only the Buy row
    assert summary.new_transactions == 1


def test_amount_mismatch_aborts_import():
    """A row where abs(amount) ≠ shares×price raises ValueError."""
    rows = parse_csv(FIXTURES / "amount_mismatch.csv")
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository(_FULL_MAP)

    with pytest.raises(ValueError, match="amount sanity check failed"):
        run_import(rows, "amount_mismatch.csv", tx_repo, map_repo)


def test_non_eur_currency_aborts_import():
    """A row with currency != EUR raises ValueError."""
    rows = parse_csv(FIXTURES / "non_eur_currency.csv")
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository(
        _isin_map_with(("US67066G1040", "NVD.DE", "NVIDIA Frankfurt"))
    )

    with pytest.raises(ValueError, match="unexpected currency"):
        run_import(rows, "non_eur_currency.csv", tx_repo, map_repo)


def test_last_seen_in_csv_updated(tmp_path: Path):
    """Importing a newer CSV row updates last_seen_in_csv for an existing entry."""
    old_map = IsinMapDocument(
        entries={
            _SAP_ISIN: IsinMapping(
                ticker="SAP.DE",
                name="SAP SE",
                status="mapped",
                last_seen_in_csv=date(2025, 12, 1),
            )
        }
    )
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository(old_map)

    rows = parse_csv(FIXTURES / "happy_path.csv")  # SAP row is 2026-03-01
    run_import(rows, "happy_path.csv", tx_repo, map_repo)

    doc = map_repo.load()
    assert doc.entries[_SAP_ISIN].last_seen_in_csv == date(2026, 3, 1)


def test_fees_none_on_security_transfer():
    """Security transfer rows with blank fee → fees_native=None."""
    rows = parse_csv(FIXTURES / "happy_path.csv")
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository(_FULL_MAP)

    run_import(rows, "happy_path.csv", tx_repo, map_repo)

    transfer = next(t for t in tx_repo.load_all() if t.id == "REF004")
    assert transfer.fees_native is None


def test_fees_zero_for_savings_plan():
    """Savings plan rows with fee=0,00 → fees_native=Money(0, EUR), not None."""
    rows = parse_csv(FIXTURES / "happy_path.csv")
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository(_FULL_MAP)

    run_import(rows, "happy_path.csv", tx_repo, map_repo)

    savings = next(t for t in tx_repo.load_all() if t.id == "REF003")
    assert savings.fees_native is not None
    assert savings.fees_native.amount == Decimal("0")
    assert savings.fees_native.currency == Currency.EUR


def test_savings_plan_fractional_shares():
    """Savings plan fractional shares are preserved with full precision."""
    rows = parse_csv(FIXTURES / "happy_path.csv")
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository(_FULL_MAP)

    run_import(rows, "happy_path.csv", tx_repo, map_repo)

    savings = next(t for t in tx_repo.load_all() if t.id == "REF003")
    assert savings.shares == Decimal("7.054176")


def test_sell_tax_captured_in_notes():
    """Sell rows with tax > 0 have tax_withheld_eur in notes."""
    rows = parse_csv(FIXTURES / "happy_path.csv")
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository(_FULL_MAP)

    run_import(rows, "happy_path.csv", tx_repo, map_repo)

    sell = next(t for t in tx_repo.load_all() if t.id == "REF002")
    assert sell.notes is not None
    assert "tax_withheld_eur" in sell.notes
    assert "15" in sell.notes


def test_transaction_id_equals_csv_reference():
    """Transaction.id is exactly the CSV reference column value."""
    rows = parse_csv(FIXTURES / "happy_path.csv")
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository(_FULL_MAP)

    run_import(rows, "happy_path.csv", tx_repo, map_repo)

    ids = {tx.id for tx in tx_repo.load_all()}
    assert ids == {"REF001", "REF002", "REF003", "REF004"}


def test_within_csv_duplicate_references_not_double_imported(tmp_path: Path):
    """If the same reference appears twice in one CSV, only one transaction is created."""
    csv_path = tmp_path / "dup_ref.csv"
    csv_path.write_text(
        "date;time;status;reference;description;assetType;type;isin;"
        "shares;price;amount;fee;tax;currency\n"
        "2026-03-01;10:00:00;Executed;REF001;SAP SE;Security;Buy;"
        "DE0007164600;10;100,00;-1.000,00;0,99;0,00;EUR\n"
        "2026-03-01;10:00:01;Executed;REF001;SAP SE;Security;Buy;"
        "DE0007164600;10;100,00;-1.000,00;0,99;0,00;EUR\n"
    )
    rows = parse_csv(csv_path)
    tx_repo = FakeTransactionRepository()
    map_repo = FakeIsinMapRepository(_isin_map_with((_SAP_ISIN, "SAP.DE", "SAP SE")))

    summary = run_import(rows, "dup_ref.csv", tx_repo, map_repo)

    assert summary.new_transactions == 1
    assert summary.already_existing == 1
    assert len(tx_repo.load_all()) == 1
