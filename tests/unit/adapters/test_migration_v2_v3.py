"""Unit tests for portfolio schema v2 → v3 migration."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.repo_json.migration import migrate_v2_to_v3

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_v2(path: Path, transactions: list[dict]) -> None:
    data = {"version": 2, "transactions": transactions}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read_portfolio(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_isin_map(path: Path, entries: dict) -> None:
    data = {"version": 1, "entries": entries}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _scalable_tx(ref: str, ticker: str) -> dict:
    return {
        "id": ref,
        "type": "buy",
        "ticker": ticker,
        "trade_date": "2026-01-01",
        "shares": "10",
        "price_native": {"amount": "100", "currency": "EUR"},
        "fx_rate_eur": "1",
        "notes": None,
        "csv_reference": ref,
        "source": "scalable_csv",
    }


def _manual_tx(ref: str, ticker: str) -> dict:
    return {
        "id": ref,
        "type": "buy",
        "ticker": ticker,
        "trade_date": "2026-01-01",
        "shares": "5",
        "price_native": {"amount": "200", "currency": "EUR"},
        "fx_rate_eur": "1",
        "notes": None,
        "csv_reference": None,
        "source": "manual",
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_migrates_scalable_and_leaves_manual(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    isin_map = tmp_path / "isin_map.json"

    _write_v2(portfolio, [
        _scalable_tx("R1", "NVDA"),
        _scalable_tx("R2", "AAPL"),
        _scalable_tx("R3", "RHM.DE"),
        _manual_tx("M1", "SAP.DE"),
    ])
    _write_isin_map(isin_map, {
        "US67066G1040": {"ticker": "NVDA", "name": "NVIDIA", "status": "mapped"},
        "US0378331005": {"ticker": "AAPL", "name": "Apple", "status": "mapped"},
        "DE0007030009": {"ticker": "RHM.DE", "name": "Rheinmetall", "status": "mapped"},
    })

    summary = migrate_v2_to_v3(portfolio)

    assert summary == {
        "migrated_count": 3,
        "manual_skipped_count": 1,
        "scalable_unbackfilled_count": 0,
    }

    data = _read_portfolio(portfolio)
    assert data["version"] == 3
    txs = {t["id"]: t for t in data["transactions"]}

    assert txs["R1"]["isin"] == "US67066G1040"
    assert txs["R2"]["isin"] == "US0378331005"
    assert txs["R3"]["isin"] == "DE0007030009"
    assert txs["M1"]["isin"] is None


def test_happy_path_backup_written(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    _write_v2(portfolio, [])
    _write_isin_map(tmp_path / "isin_map.json", {})

    migrate_v2_to_v3(portfolio)

    backup = tmp_path / "portfolio.json.v2.bak"
    assert backup.exists()
    bak_data = json.loads(backup.read_text())
    assert bak_data["version"] == 2


def test_backup_content_is_pre_migration_state(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    _write_v2(portfolio, [_scalable_tx("R1", "NVDA")])
    _write_isin_map(tmp_path / "isin_map.json", {
        "US67066G1040": {"ticker": "NVDA", "name": "NVIDIA", "status": "mapped"},
    })

    migrate_v2_to_v3(portfolio)

    bak = json.loads((tmp_path / "portfolio.json.v2.bak").read_text())
    assert bak["version"] == 2
    assert "isin" not in bak["transactions"][0]


# ---------------------------------------------------------------------------
# Collision
# ---------------------------------------------------------------------------


def test_collision_raises_and_leaves_portfolio_unchanged(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    _write_v2(portfolio, [_scalable_tx("R1", "FOO")])
    _write_isin_map(tmp_path / "isin_map.json", {
        "AA000000001": {"ticker": "FOO", "name": "Foo A", "status": "mapped"},
        "BB000000002": {"ticker": "FOO", "name": "Foo B", "status": "mapped"},
    })

    original_text = portfolio.read_text()

    with pytest.raises(RuntimeError, match="collision"):
        migrate_v2_to_v3(portfolio)

    # Portfolio file must be unchanged
    assert portfolio.read_text() == original_text
    data = _read_portfolio(portfolio)
    assert data["version"] == 2


def test_collision_error_names_colliding_ticker_and_isins(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    _write_v2(portfolio, [])
    _write_isin_map(tmp_path / "isin_map.json", {
        "AA000000001": {"ticker": "FOO", "name": "Foo A", "status": "mapped"},
        "BB000000002": {"ticker": "FOO", "name": "Foo B", "status": "mapped"},
    })

    with pytest.raises(RuntimeError) as exc_info:
        migrate_v2_to_v3(portfolio)

    msg = str(exc_info.value)
    assert "FOO" in msg
    assert "AA000000001" in msg
    assert "BB000000002" in msg


# ---------------------------------------------------------------------------
# Unbackfillable (scalable_csv tx whose ticker is not in isin_map)
# ---------------------------------------------------------------------------


def test_unbackfillable_scalable_tx_gets_none_isin(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    _write_v2(portfolio, [_scalable_tx("R1", "UNKNOWN")])
    _write_isin_map(tmp_path / "isin_map.json", {
        "US67066G1040": {"ticker": "NVDA", "name": "NVIDIA", "status": "mapped"},
    })

    summary = migrate_v2_to_v3(portfolio)

    assert summary["scalable_unbackfilled_count"] == 1
    data = _read_portfolio(portfolio)
    assert data["transactions"][0]["isin"] is None


def test_missing_isin_map_all_isin_none(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    _write_v2(portfolio, [
        _scalable_tx("R1", "NVDA"),
        _manual_tx("M1", "SAP.DE"),
    ])
    # No isin_map.json in tmp_path

    summary = migrate_v2_to_v3(portfolio)

    assert summary["migrated_count"] == 0
    assert summary["scalable_unbackfilled_count"] == 1
    assert summary["manual_skipped_count"] == 1

    data = _read_portfolio(portfolio)
    assert data["version"] == 3
    for tx in data["transactions"]:
        assert tx["isin"] is None


# ---------------------------------------------------------------------------
# Version guard
# ---------------------------------------------------------------------------


def test_wrong_version_raises(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text(json.dumps({"version": 3, "transactions": []}))

    with pytest.raises(ValueError, match="v2"):
        migrate_v2_to_v3(portfolio)


def test_v1_version_raises(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text(json.dumps({"version": 1, "transactions": []}))

    with pytest.raises(ValueError, match="v2"):
        migrate_v2_to_v3(portfolio)


# ---------------------------------------------------------------------------
# Unmapped entries in isin_map are ignored
# ---------------------------------------------------------------------------


def test_unmapped_entries_in_isin_map_are_ignored(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    _write_v2(portfolio, [_scalable_tx("R1", "NVDA")])
    _write_isin_map(tmp_path / "isin_map.json", {
        "US67066G1040": {"ticker": "NVDA", "name": "NVIDIA", "status": "mapped"},
        "XX999999999": {"ticker": None, "name": "Unknown", "status": "unmapped"},
    })

    summary = migrate_v2_to_v3(portfolio)

    assert summary["migrated_count"] == 1
    data = _read_portfolio(portfolio)
    assert data["transactions"][0]["isin"] == "US67066G1040"
