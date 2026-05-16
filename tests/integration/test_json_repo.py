import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from app.adapters.repo_json.json_repo import JsonTransactionRepository, LegacyDataError
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.ports.repository import RepositoryCorruptedError, TransactionNotFoundError

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_transaction():
    return Transaction(
        type=TransactionType.BUY,
        ticker="AAPL",
        trade_date=date(2024, 3, 15),
        shares=Decimal("10.0000"),
        price_native=Money(amount=Decimal("180.0000"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9200"),
    )


def test_load_all_empty_nonexistent(tmp_path):
    path = tmp_path / "portfolio.json"
    repo = JsonTransactionRepository(path)
    assert repo.load_all() == []


def test_save_load_round_trip(tmp_path, sample_transaction):
    path = tmp_path / "portfolio.json"
    repo = JsonTransactionRepository(path)

    tx2 = sample_transaction.model_copy(update={"id": "another-id", "ticker": "MSFT"})
    txs = [sample_transaction, tx2]

    repo.save_all(txs)

    # Fresh repo instance to ensure it reads from disk
    new_repo = JsonTransactionRepository(path)
    loaded_txs = new_repo.load_all()

    assert len(loaded_txs) == 2
    assert loaded_txs[0] == sample_transaction
    assert loaded_txs[1] == tx2


def test_add_appends(tmp_path, sample_transaction):
    path = tmp_path / "portfolio.json"
    repo = JsonTransactionRepository(path)

    repo.add(sample_transaction)
    tx2 = sample_transaction.model_copy(update={"id": "id2", "ticker": "MSFT"})
    repo.add(tx2)

    loaded = repo.load_all()
    assert loaded == [sample_transaction, tx2]


def test_add_raises_on_duplicate_id(tmp_path, sample_transaction):
    path = tmp_path / "portfolio.json"
    repo = JsonTransactionRepository(path)

    repo.add(sample_transaction)
    with pytest.raises(ValueError, match="already exists"):
        repo.add(sample_transaction)


def test_get_finds_existing(tmp_path, sample_transaction):
    path = tmp_path / "portfolio.json"
    repo = JsonTransactionRepository(path)
    repo.add(sample_transaction)

    found = repo.get(sample_transaction.id)
    assert found == sample_transaction


def test_get_raises_on_missing(tmp_path):
    path = tmp_path / "portfolio.json"
    repo = JsonTransactionRepository(path)
    with pytest.raises(TransactionNotFoundError, match="unknown"):
        repo.get("unknown")


def test_update_replaces_by_id(tmp_path, sample_transaction):
    path = tmp_path / "portfolio.json"
    repo = JsonTransactionRepository(path)
    repo.add(sample_transaction)

    updated_tx = sample_transaction.model_copy(update={"shares": Decimal("20")})
    repo.update(updated_tx)

    assert repo.get(sample_transaction.id).shares == Decimal("20")


def test_update_raises_on_missing(tmp_path, sample_transaction):
    path = tmp_path / "portfolio.json"
    repo = JsonTransactionRepository(path)
    with pytest.raises(TransactionNotFoundError):
        repo.update(sample_transaction)


def test_delete_removes(tmp_path, sample_transaction):
    path = tmp_path / "portfolio.json"
    repo = JsonTransactionRepository(path)

    tx2 = sample_transaction.model_copy(update={"id": "id2"})
    tx3 = sample_transaction.model_copy(update={"id": "id3"})

    repo.save_all([sample_transaction, tx2, tx3])
    repo.delete(tx2.id)

    loaded = repo.load_all()
    assert len(loaded) == 2
    assert loaded == [sample_transaction, tx3]


def test_delete_raises_on_missing(tmp_path):
    path = tmp_path / "portfolio.json"
    repo = JsonTransactionRepository(path)
    with pytest.raises(TransactionNotFoundError):
        repo.delete("unknown")


def test_atomic_write_cleanup_on_failure(tmp_path, sample_transaction):
    path = tmp_path / "portfolio.json"
    repo = JsonTransactionRepository(path)

    # Initial save
    repo.save_all([sample_transaction])
    tmp_file = path.with_suffix(".json.tmp")

    with patch("os.replace", side_effect=OSError("Disk full")):
        with pytest.raises(OSError, match="Disk full"):
            repo.save_all([sample_transaction.model_copy(update={"id": "new"})])

    # Ensure original file is intact
    assert len(repo.load_all()) == 1
    assert repo.load_all()[0].id == sample_transaction.id

    # Ensure temp file is cleaned up
    assert not tmp_file.exists()


def test_load_all_corrupted_empty_file(tmp_path):
    path = tmp_path / "portfolio.json"
    path.write_text("")
    repo = JsonTransactionRepository(path)
    with pytest.raises(RepositoryCorruptedError, match="empty"):
        repo.load_all()


def test_load_all_corrupted_malformed_json(tmp_path):
    path = tmp_path / "portfolio.json"
    path.write_text("not json")
    repo = JsonTransactionRepository(path)
    with pytest.raises(RepositoryCorruptedError, match="JSON"):
        repo.load_all()


def test_load_all_corrupted_missing_version(tmp_path):
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps({"transactions": []}))
    repo = JsonTransactionRepository(path)
    with pytest.raises(RepositoryCorruptedError, match="version"):
        repo.load_all()


def test_load_all_corrupted_wrong_version(tmp_path):
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps({"version": 3, "transactions": []}))
    repo = JsonTransactionRepository(path)
    with pytest.raises(RepositoryCorruptedError, match="version"):
        repo.load_all()


def test_load_all_corrupted_invalid_transaction(tmp_path):
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps({"version": 2, "transactions": [{"id": "bad"}]}))
    repo = JsonTransactionRepository(path)
    with pytest.raises(RepositoryCorruptedError, match="Invalid transaction"):
        repo.load_all()


def test_decimal_precision_round_trip(tmp_path):
    path = tmp_path / "portfolio.json"
    repo = JsonTransactionRepository(path)

    tx = Transaction(
        type=TransactionType.BUY,
        ticker="AAPL",
        trade_date=date(2024, 3, 15),
        shares=Decimal("0.0001"),
        price_native=Money(amount=Decimal("12345.6789"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9234"),
    )

    repo.save_all([tx])
    loaded = repo.load_all()[0]

    assert loaded.shares == Decimal("0.0001")
    assert loaded.price_native.amount == Decimal("12345.6789")
    assert loaded.fx_rate_eur == Decimal("0.9234")


def test_legacy_data_error_raised_for_jpy_as_usd():
    """Loading the legacy 5631.T-as-USD fixture must raise LegacyDataError."""
    path = FIXTURES_DIR / "portfolio_legacy_jpy_as_usd.json"
    repo = JsonTransactionRepository(path)
    with pytest.raises(LegacyDataError) as exc_info:
        repo.load_all()
    assert "5631.T" in str(exc_info.value)
    assert exc_info.value.count == 1
    assert len(exc_info.value.offenders) == 1


def test_legacy_data_error_message_includes_migration_hint():
    """LegacyDataError message must tell the user which script to run."""
    path = FIXTURES_DIR / "portfolio_legacy_jpy_as_usd.json"
    repo = JsonTransactionRepository(path)
    with pytest.raises(LegacyDataError) as exc_info:
        repo.load_all()
    assert "migrate_currency" in str(exc_info.value)


def test_clean_portfolio_loads_without_error(tmp_path):
    """A portfolio with correct ticker↔currency mapping loads fine."""
    path = tmp_path / "portfolio.json"
    repo = JsonTransactionRepository(path)
    tx = Transaction(
        type=TransactionType.BUY,
        ticker="5631.T",
        trade_date=date(2025, 11, 10),
        shares=Decimal("1"),
        price_native=Money(amount=Decimal("9049"), currency=Currency.JPY),
        fx_rate_eur=Decimal("0.0061"),
    )
    repo.save_all([tx])
    loaded = repo.load_all()
    assert len(loaded) == 1
    assert loaded[0].ticker == "5631.T"
    assert loaded[0].price_native.currency == Currency.JPY


def test_creates_parent_directory(tmp_path):
    path = tmp_path / "deep" / "nested" / "portfolio.json"
    repo = JsonTransactionRepository(path)
    tx = Transaction(
        type=TransactionType.BUY,
        ticker="AAPL",
        trade_date=date(2024, 3, 15),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("180"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.92"),
    )

    repo.save_all([tx])
    assert path.exists()
