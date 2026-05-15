from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app.adapters.repo_json import JsonTransactionRepository
from app.domain.models import Currency, Transaction, TransactionType
from app.domain.money import Money
from app.services.valuation import compute_live_positions, compute_portfolio_summary
from tests.fakes.fx_feed import FakeFxProvider
from tests.fakes.price_feed import FakePriceProvider


def _make_txs() -> list[Transaction]:
    return [
        Transaction(
            id="tx-vusa",
            type=TransactionType.BUY,
            ticker="VUSA.DE",
            trade_date=date(2024, 8, 1),
            shares=Decimal("32.0000"),
            price_native=Money(amount=Decimal("97.5000"), currency=Currency.EUR),
            fx_rate_eur=Decimal("1"),
            notes="Core S&P 500 ETF entry",
        ),
        Transaction(
            id="tx-etn",
            type=TransactionType.BUY,
            ticker="ETN",
            trade_date=date(2025, 1, 15),
            shares=Decimal("5.0000"),
            price_native=Money(amount=Decimal("320.0000"), currency=Currency.USD),
            fx_rate_eur=Decimal("0.9300"),
            notes="Eaton — power infra entry",
        ),
    ]


def test_overview_e2e(tmp_path: Path):
    output_json = tmp_path / "portfolio.json"

    repo = JsonTransactionRepository(output_json)
    repo.save_all(_make_txs())

    transactions = repo.load_all()

    fake_price = FakePriceProvider({
        "VUSA.DE": Decimal("100.00"),
        "ETN": Decimal("350.00"),
    })

    fake_fx = FakeFxProvider({
        (Currency.EUR, Currency.USD): Decimal("1.08"),
        (Currency.USD, Currency.EUR): Decimal("0.9259"),
    })

    live_positions = compute_live_positions(transactions, fake_price, fake_fx)

    assert len(live_positions) == 2
    assert "VUSA.DE" in live_positions
    assert "ETN" in live_positions

    assert live_positions["VUSA.DE"].live_value_eur is not None
    assert live_positions["ETN"].live_value_eur is not None

    summary = compute_portfolio_summary(live_positions, datetime.now())
    assert summary.staleness == "live"
    assert summary.total_value_eur > 0
