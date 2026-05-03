from pathlib import Path

from app.adapters.repo_json import JsonTransactionRepository
from app.scripts import seed_portfolio


def test_seed_portfolio_end_to_end(tmp_path: Path):
    input_csv = tmp_path / "seed.csv"
    output_json = tmp_path / "portfolio.json"
    
    input_csv.write_text(
        "ticker,type,trade_date,shares,price_native,currency,fx_rate_eur,notes\n"
        "VUSA.DE,buy,2024-08-01,32.0000,97.5000,EUR,1.0,Core S&P 500 ETF entry\n"
        "ETN,buy,2025-01-15,5.0000,320.0000,USD,0.9300,Eaton — power infra entry"
    )
    
    ret = seed_portfolio.main(input_csv, output_json)
    assert ret == 0
    assert output_json.exists()
    
    repo = JsonTransactionRepository(output_json)
    txs = repo.load_all()
    assert len(txs) == 2
    assert txs[0].ticker == "VUSA.DE"
    assert txs[1].ticker == "ETN"

def test_seed_portfolio_refuses_to_overwrite(tmp_path: Path):
    input_csv = tmp_path / "seed.csv"
    output_json = tmp_path / "portfolio.json"
    
    input_csv.write_text("ticker,type,trade_date,shares,price_native,currency,fx_rate_eur,notes\n")
    output_json.write_text("existing data")
    
    ret = seed_portfolio.main(input_csv, output_json)
    assert ret == 1
    assert output_json.read_text() == "existing data"

def test_seed_portfolio_force_overwrites(tmp_path: Path):
    input_csv = tmp_path / "seed.csv"
    output_json = tmp_path / "portfolio.json"
    
    input_csv.write_text(
        "ticker,type,trade_date,shares,price_native,currency,fx_rate_eur,notes\n"
        "VUSA.DE,buy,2024-08-01,32.0000,97.5000,EUR,1.0,Core S&P 500 ETF entry\n"
    )
    output_json.write_text("existing data")
    
    ret = seed_portfolio.main(input_csv, output_json, force=True)
    assert ret == 0
    
    repo = JsonTransactionRepository(output_json)
    txs = repo.load_all()
    assert len(txs) == 1

def test_seed_portfolio_skips_malformed_rows(tmp_path: Path):
    input_csv = tmp_path / "seed.csv"
    output_json = tmp_path / "portfolio.json"
    
    input_csv.write_text(
        "ticker,type,trade_date,shares,price_native,currency,fx_rate_eur,notes\n"
        "VUSA.DE,buy,2024-08-01,32.0000,97.5000,EUR,1.0,Core S&P 500 ETF entry\n"
        "BAD,buy,2024-08-01,NOT_A_NUMBER,97.5000,EUR,1.0,Bad row\n"
        "ETN,buy,2025-01-15,5.0000,320.0000,USD,0.9300,Good row\n"
    )
    
    ret = seed_portfolio.main(input_csv, output_json)
    assert ret == 0
    
    repo = JsonTransactionRepository(output_json)
    txs = repo.load_all()
    assert len(txs) == 2
