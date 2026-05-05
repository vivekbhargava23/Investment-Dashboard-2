"""Integration tests for app.scripts.migrate_currency."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.adapters.repo_json.json_repo import JsonTransactionRepository
from app.domain.money import Currency, Money
from app.scripts.migrate_currency import main
from tests.fakes.price_feed import FakePriceProvider

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
LEGACY_FIXTURE = FIXTURES_DIR / "portfolio_legacy_jpy_as_usd.json"

# Known JPY close we inject so tests are deterministic (no network)
FAKE_JPY_CLOSE = Decimal("8829.5596")
_FAKE_PRICES = FakePriceProvider(
    historical_prices={
        ("5631.T", date(2025, 11, 10)): Money(amount=FAKE_JPY_CLOSE, currency=Currency.JPY),
    }
)


def test_dry_run_leaves_files_untouched(tmp_path: Path) -> None:
    import shutil

    src = tmp_path / "portfolio.json"
    shutil.copy(LEGACY_FIXTURE, src)
    original_content = src.read_text()

    ret = main(src, dry_run=True, force=True, price_provider=_FAKE_PRICES, interactive=False)

    assert ret == 0
    assert src.read_text() == original_content


def test_migrates_5631t_to_jpy(tmp_path: Path) -> None:
    """After migration, 5631.T row has JPY currency and the same EUR cost basis."""
    import shutil

    src = tmp_path / "portfolio.json"
    out = tmp_path / "migrated.json"
    shutil.copy(LEGACY_FIXTURE, src)

    ret = main(src, output_path=out, force=True, price_provider=_FAKE_PRICES, interactive=False)
    assert ret == 0

    repo = JsonTransactionRepository(out)
    txs = repo.load_all()

    jpy_tx = next(tx for tx in txs if tx.ticker == "5631.T")
    assert jpy_tx.price_native.currency == Currency.JPY
    assert jpy_tx.price_native.amount == FAKE_JPY_CLOSE.quantize(Decimal("0.0001"))

    # EUR cost basis is preserved (within rounding): original was 4200 * 0.93 = 3906
    original_eur = Decimal("4200") * Decimal("0.9300")
    migrated_eur = jpy_tx.cost_eur.amount
    assert abs(migrated_eur - original_eur) < Decimal("0.01"), (
        f"Expected EUR cost ~{original_eur}, got {migrated_eur}"
    )


def test_clean_rows_left_alone(tmp_path: Path) -> None:
    """NVDA (USD) row in the legacy fixture must be written back unchanged."""
    import shutil

    src = tmp_path / "portfolio.json"
    out = tmp_path / "migrated.json"
    shutil.copy(LEGACY_FIXTURE, src)

    ret = main(src, output_path=out, force=True, price_provider=_FAKE_PRICES, interactive=False)
    assert ret == 0

    repo = JsonTransactionRepository(out)
    txs = repo.load_all()

    nvda_tx = next(tx for tx in txs if tx.ticker == "NVDA")
    assert nvda_tx.price_native.currency == Currency.USD
    assert nvda_tx.price_native.amount == Decimal("115.0000")


def test_output_round_trips_through_repo(tmp_path: Path) -> None:
    """After migration, JsonTransactionRepository.load_all() succeeds."""
    import shutil

    src = tmp_path / "portfolio.json"
    out = tmp_path / "migrated.json"
    shutil.copy(LEGACY_FIXTURE, src)

    main(src, output_path=out, force=True, price_provider=_FAKE_PRICES, interactive=False)

    repo = JsonTransactionRepository(out)
    txs = repo.load_all()
    # Fixture has 2 rows
    assert len(txs) == 2


def test_no_op_on_already_clean_file(tmp_path: Path) -> None:
    """Running migration on a file with no offenders exits cleanly."""
    repo = JsonTransactionRepository(tmp_path / "clean.json")
    from app.domain.models import Transaction, TransactionType

    tx = Transaction(
        type=TransactionType.BUY,
        ticker="NVDA",
        trade_date=date(2025, 5, 12),
        shares=Decimal("9"),
        price_native=Money(amount=Decimal("115"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.91"),
    )
    repo.save_all([tx])

    ret = main(
        tmp_path / "clean.json",
        force=True,
        price_provider=_FAKE_PRICES,
        interactive=False,
    )
    assert ret == 0
