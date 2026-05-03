from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.adapters.repo_json import JsonTransactionRepository
from app.domain.models import Currency
from app.scripts import seed_portfolio
from app.services.valuation import compute_live_positions, compute_portfolio_summary
from tests.fakes.fx_feed import FakeFxProvider
from tests.fakes.price_feed import FakePriceProvider


def test_overview_e2e(tmp_path: Path):
    input_csv = tmp_path / "seed.csv"
    output_json = tmp_path / "portfolio.json"
    
    input_csv.write_text(
        "ticker,type,trade_date,shares,price_native,currency,fx_rate_eur,notes\n"
        "VUSA.DE,buy,2024-08-01,32.0000,97.5000,EUR,1.0,Core S&P 500 ETF entry\n"
        "ETN,buy,2025-01-15,5.0000,320.0000,USD,0.9300,Eaton — power infra entry\n"
    )
    
    seed_portfolio.main(input_csv, output_json)
    
    repo = JsonTransactionRepository(output_json)
    transactions = repo.load_all()
    
    fake_price = FakePriceProvider({
        "VUSA.DE": Decimal("100.00"),
        "ETN": Decimal("350.00")
    })
    
    fake_fx = FakeFxProvider({
        (Currency.EUR, Currency.USD): Decimal("1.08"),
        (Currency.USD, Currency.EUR): Decimal("0.9259")
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
