"""
End-to-end tests for the Manage Portfolio pipeline using fakes.
No Streamlit context required — tests exercise build_transaction + repository.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.adapters.repo_json.json_repo import JsonTransactionRepository
from app.domain.models import TransactionType
from app.domain.money import Currency, Money
from app.ports.ticker_resolver import TickerMatch
from app.services.trading import build_transaction
from tests.fakes.fx_feed import FakeFxProvider
from tests.fakes.price_feed import FakePriceProvider
from tests.fakes.ticker_resolver import FakeTickerResolver

_DATE_EUR = date(2026, 5, 4)
_DATE_USD = date(2025, 7, 22)
_DATE_JPY = date(2025, 11, 10)

_PRICE_PROVIDER = FakePriceProvider(
    historical_prices={
        ("APD", _DATE_USD): Money(amount=Decimal("250.00"), currency=Currency.USD),
        ("5631.T", _DATE_JPY): Money(amount=Decimal("8829"), currency=Currency.JPY),
    }
)
_FX_PROVIDER = FakeFxProvider(
    historical_rates={
        (Currency.USD, Currency.EUR, _DATE_USD): Decimal("0.9050"),
        (Currency.JPY, Currency.EUR, _DATE_JPY): Decimal("0.005776"),
    }
)

_RESOLVER = FakeTickerResolver([
    TickerMatch(symbol="RHM.DE", name="Rheinmetall AG", exchange="XETRA", currency=Currency.EUR),
    TickerMatch(symbol="APD", name="Air Products", exchange="NYSE", currency=Currency.USD),
    TickerMatch(symbol="5631.T", name="Japan Steel Works", exchange="TYO", currency=Currency.JPY),
])


def _repo(tmp_path: Path) -> JsonTransactionRepository:
    return JsonTransactionRepository(tmp_path / "portfolio.json")


# ---------------------------------------------------------------------------
# Add pipeline
# ---------------------------------------------------------------------------

def test_add_eur_transaction(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    tx, dev = build_transaction(
        ticker="RHM.DE",
        tx_type=TransactionType.BUY,
        trade_date=_DATE_EUR,
        shares=Decimal("1"),
        eur_total=Decimal("1452.75"),
        fees_eur=Decimal("0"),
        currency=Currency.EUR,
        price_provider=_PRICE_PROVIDER,
        fx_provider=_FX_PROVIDER,
    )
    repo.add(tx)
    loaded = repo.load_all()
    assert len(loaded) == 1
    assert loaded[0].ticker == "RHM.DE"
    assert loaded[0].price_native.currency == Currency.EUR
    assert dev is None


def test_add_usd_transaction(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    tx, dev = build_transaction(
        ticker="APD",
        tx_type=TransactionType.BUY,
        trade_date=_DATE_USD,
        shares=Decimal("4"),
        eur_total=Decimal("904.50"),
        fees_eur=Decimal("0.99"),
        currency=Currency.USD,
        price_provider=_PRICE_PROVIDER,
        fx_provider=_FX_PROVIDER,
    )
    repo.add(tx)
    loaded = repo.load_all()
    assert len(loaded) == 1
    assert loaded[0].ticker == "APD"
    assert loaded[0].price_native.currency == Currency.USD
    assert dev is not None


def test_add_jpy_transaction(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    tx, dev = build_transaction(
        ticker="5631.T",
        tx_type=TransactionType.BUY,
        trade_date=_DATE_JPY,
        shares=Decimal("1"),
        eur_total=Decimal("51.00"),
        fees_eur=Decimal("0.99"),
        currency=Currency.JPY,
        price_provider=_PRICE_PROVIDER,
        fx_provider=_FX_PROVIDER,
    )
    repo.add(tx)
    loaded = repo.load_all()
    assert len(loaded) == 1
    assert loaded[0].ticker == "5631.T"
    assert loaded[0].price_native.currency == Currency.JPY
    assert dev is not None


def test_add_three_transactions_all_load(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    for ticker, date_, currency, eur_total, shares in [
        ("RHM.DE", _DATE_EUR, Currency.EUR, Decimal("1452.75"), Decimal("1")),
        ("APD", _DATE_USD, Currency.USD, Decimal("904.50"), Decimal("4")),
        ("5631.T", _DATE_JPY, Currency.JPY, Decimal("51.00"), Decimal("1")),
    ]:
        tx, _ = build_transaction(
            ticker=ticker,
            tx_type=TransactionType.BUY,
            trade_date=date_,
            shares=shares,
            eur_total=eur_total,
            fees_eur=Decimal("0.99"),
            currency=currency,
            price_provider=_PRICE_PROVIDER,
            fx_provider=_FX_PROVIDER,
        )
        repo.add(tx)
    loaded = repo.load_all()
    assert len(loaded) == 3
    assert {t.ticker for t in loaded} == {"RHM.DE", "APD", "5631.T"}


# ---------------------------------------------------------------------------
# Edit pipeline
# ---------------------------------------------------------------------------

def test_edit_transaction_updates_shares(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    tx, _ = build_transaction(
        ticker="APD",
        tx_type=TransactionType.BUY,
        trade_date=_DATE_USD,
        shares=Decimal("4"),
        eur_total=Decimal("904.50"),
        fees_eur=Decimal("0.99"),
        currency=Currency.USD,
        price_provider=_PRICE_PROVIDER,
        fx_provider=_FX_PROVIDER,
    )
    repo.add(tx)

    tx2, _ = build_transaction(
        ticker="APD",
        tx_type=TransactionType.BUY,
        trade_date=_DATE_USD,
        shares=Decimal("6"),
        eur_total=Decimal("1356.75"),
        fees_eur=Decimal("0.99"),
        currency=Currency.USD,
        price_provider=_PRICE_PROVIDER,
        fx_provider=_FX_PROVIDER,
    )
    updated = tx2.model_copy(update={"id": tx.id})
    repo.update(updated)

    loaded = repo.load_all()
    assert len(loaded) == 1
    assert loaded[0].shares == Decimal("6.0000")


# ---------------------------------------------------------------------------
# Delete pipeline
# ---------------------------------------------------------------------------

def test_delete_reduces_count(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    tx1, _ = build_transaction(
        ticker="RHM.DE",
        tx_type=TransactionType.BUY,
        trade_date=_DATE_EUR,
        shares=Decimal("1"),
        eur_total=Decimal("1452.75"),
        fees_eur=Decimal("0"),
        currency=Currency.EUR,
        price_provider=_PRICE_PROVIDER,
        fx_provider=_FX_PROVIDER,
    )
    tx2, _ = build_transaction(
        ticker="APD",
        tx_type=TransactionType.BUY,
        trade_date=_DATE_USD,
        shares=Decimal("1"),
        eur_total=Decimal("226.13"),
        fees_eur=Decimal("0.99"),
        currency=Currency.USD,
        price_provider=_PRICE_PROVIDER,
        fx_provider=_FX_PROVIDER,
    )
    repo.add(tx1)
    repo.add(tx2)
    repo.delete(tx1.id)
    loaded = repo.load_all()
    assert len(loaded) == 1
    assert loaded[0].ticker == "APD"


# ---------------------------------------------------------------------------
# Resolver-failure fallback path
# ---------------------------------------------------------------------------

def test_fake_resolver_resolve_and_lookup() -> None:
    """FakeTickerResolver returns expected results for the test fixtures."""
    hit = _RESOLVER.lookup("RHM.DE")
    assert hit is not None
    assert hit.currency == Currency.EUR

    results = _RESOLVER.resolve("APD")
    assert any(m.symbol == "APD" for m in results)


def test_resolver_failure_triggers_fallback(tmp_path: Path) -> None:
    """When the resolver raises, the caller must fall back to manual entry.
    Here we simulate the fallback by constructing the Transaction directly."""
    from app.domain.models import Transaction
    from app.domain.money import Money

    fallback_tx = Transaction(
        type=TransactionType.BUY,
        ticker="APD",
        trade_date=_DATE_USD,
        shares=Decimal("4"),
        price_native=Money(amount=Decimal("250"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9050"),
        notes="manual fallback",
    )
    repo = _repo(tmp_path)
    repo.add(fallback_tx)
    loaded = repo.load_all()
    assert len(loaded) == 1
    assert loaded[0].notes == "manual fallback"
