"""Unit tests for portfolio schema v1 → v2 migration."""
from __future__ import annotations

import json
from pathlib import Path

from app.adapters.repo_json.migration import MigrationResult, migrate_v1_to_v2

# ─── helpers ──────────────────────────────────────────────────────────────────

def _write_v1(path: Path, transactions: list[dict]) -> None:
    data = {"version": 1, "transactions": transactions}
    with open(path, "w") as f:
        json.dump(data, f)


def _read_portfolio(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


# ─── test 11: CSV-matched tx ──────────────────────────────────────────────────

def test_csv_reference_match_sets_source(tmp_path: Path) -> None:
    """TX whose id matches a CSV reference gets csv_reference set and source=scalable_csv."""
    portfolio = tmp_path / "portfolio.json"
    _write_v1(portfolio, [
        {
            "id": "SCALabc123",
            "type": "buy",
            "ticker": "SAP.DE",
            "trade_date": "2026-03-01",
            "shares": "10",
            "price_native": {"amount": "100.0000", "currency": "EUR"},
            "fx_rate_eur": "1",
        }
    ])

    # Write a minimal CSV with this reference
    csv_path = tmp_path / "scalable_raw.csv"
    csv_path.write_text(
        "date;time;status;reference;description;assetType;type;isin;"
        "shares;price;amount;fee;tax;currency\n"
        "2026-03-01;10:00:00;Executed;SCALabc123;SAP SE;Security;Buy;"
        "DE0007164600;10;100,00;-1000,00;0,99;0,00;EUR\n"
    )

    result = migrate_v1_to_v2(portfolio, csv_path)
    assert result.csv_matched == 1

    data = _read_portfolio(portfolio)
    assert data["version"] == 2
    tx = data["transactions"][0]
    assert tx["csv_reference"] == "SCALabc123"
    assert tx["source"] == "scalable_csv"


# ─── test 12: SWITCH-101 tx ───────────────────────────────────────────────────

def test_switch_tagged_extracts_wwum_ref(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    _write_v1(portfolio, [
        {
            "id": "SWITCH-101-WWUM00596687933",
            "type": "buy",
            "ticker": "POLY.DE",
            "trade_date": "2025-12-06",
            "shares": "17",
            "price_native": {"amount": "1.1440", "currency": "EUR"},
            "fx_rate_eur": "1",
        }
    ])

    result = migrate_v1_to_v2(portfolio)
    assert result.switch_tagged == 1

    data = _read_portfolio(portfolio)
    tx = data["transactions"][0]
    assert tx["source"] == "switch"
    assert tx["csv_reference"] == "WWUM00596687933"


# ─── test 13: UUID tx is manual ───────────────────────────────────────────────

def test_uuid_tx_tagged_as_manual(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    _write_v1(portfolio, [
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "type": "buy",
            "ticker": "SAP.DE",
            "trade_date": "2026-01-01",
            "shares": "5",
            "price_native": {"amount": "200.0000", "currency": "EUR"},
            "fx_rate_eur": "1",
        }
    ])

    result = migrate_v1_to_v2(portfolio)
    assert result.manual_tagged == 1

    data = _read_portfolio(portfolio)
    tx = data["transactions"][0]
    assert tx["source"] == "manual"
    assert tx["csv_reference"] is None


# ─── test 14: v2 portfolio is no-op ──────────────────────────────────────────

def test_v2_portfolio_is_noop(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text(json.dumps({"version": 2, "transactions": []}))

    result = migrate_v1_to_v2(portfolio)
    assert result.csv_matched == 0
    assert result.switch_tagged == 0
    assert result.manual_tagged == 0
    assert result.untagged_scalable == 0


# ─── test 15: backup written exactly once ────────────────────────────────────

def test_backup_written_once_on_first_run(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    _write_v1(portfolio, [])

    backup = tmp_path / "portfolio.v1.pre-migration.json.bak"
    assert not backup.exists()

    migrate_v1_to_v2(portfolio)
    assert backup.exists()

    # Second run: portfolio is v2 — migration is no-op, backup not overwritten
    backup.write_text("original_backup")
    migrate_v1_to_v2(portfolio)
    assert backup.read_text() == "original_backup"


# ─── test 16: SCAL-prefixed id without CSV match is untagged_scalable ─────────

def test_scal_without_csv_match_is_untagged_scalable(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    _write_v1(portfolio, [
        {
            "id": "SCALxyz999",
            "type": "buy",
            "ticker": "RHM.DE",
            "trade_date": "2026-02-01",
            "shares": "3",
            "price_native": {"amount": "500.0000", "currency": "EUR"},
            "fx_rate_eur": "1",
        }
    ])

    # No CSV — migration still classifies by ID prefix
    result = migrate_v1_to_v2(portfolio, csv_path=None)
    assert result.untagged_scalable == 1

    data = _read_portfolio(portfolio)
    tx = data["transactions"][0]
    assert tx["source"] == "scalable_csv"
    assert tx["csv_reference"] is None


# ─── test 17: MigrationResult __str__ ────────────────────────────────────────

def test_migration_result_str() -> None:
    r = MigrationResult(csv_matched=2, switch_tagged=1, untagged_scalable=3, manual_tagged=5)
    s = str(r)
    assert "11 transactions" in s
    assert "2 CSV-matched" in s
    assert "1 switch-tagged" in s
    assert "3 untagged-Scalable" in s
    assert "5 manual" in s
