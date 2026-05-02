"""
tests/test_repository.py

Integration tests for app/data/repository.py.
Tests use the committed seed file (app/data/seeds/portfolio.json) so they
work without a runtime data/portfolio.json present.
"""

import json
import tempfile
from pathlib import Path

import pytest

import app.data.repository as repo
from app.core.portfolio import Portfolio
from app.core.position import Position
from app.core.transaction import Transaction


# ── helpers ───────────────────────────────────────────────────────────────────

def _minimal_portfolio_json(name: str = "Test") -> dict:
    return {
        "name": name,
        "positions": [
            {
                "ticker": "NVDA",
                "name": "Nvidia",
                "tags": [],
                "horizon": None,
                "thesis_status": "intact",
                "thesis_notes": "",
                "transactions": [
                    {
                        "id": "txn-1",
                        "ticker": "NVDA",
                        "trade_date": "2025-01-01",
                        "trade_type": "buy",
                        "shares": 10.0,
                        "price": 100.0,
                        "fees": 0.0,
                        "note": "",
                    },
                    {
                        "id": "txn-2",
                        "ticker": "NVDA",
                        "trade_date": "2025-06-01",
                        "trade_type": "sell",
                        "shares": 4.0,
                        "price": 130.0,
                        "fees": 0.0,
                        "note": "",
                    },
                ],
            }
        ],
        "catalysts": [],
        "risk_flags": [],
        "behavioural_ledger": [],
        "session_log": [],
    }


# ── tests ─────────────────────────────────────────────────────────────────────

class TestLoadPortfolio:
    def test_load_portfolio_returns_positions_with_transactions(
        self, tmp_path, monkeypatch
    ):
        data = _minimal_portfolio_json()
        runtime = tmp_path / "portfolio.json"
        runtime.write_text(json.dumps(data), encoding="utf-8")

        monkeypatch.setattr(repo, "_RUNTIME_PATH", runtime)

        portfolio = repo.load_portfolio()

        assert len(portfolio.positions) == 1
        pos = portfolio.positions[0]
        assert pos.ticker == "NVDA"
        assert len(pos.transactions) == 2
        assert all(isinstance(t, Transaction) for t in pos.transactions)

    def test_load_portfolio_computes_correct_open_lots(
        self, tmp_path, monkeypatch
    ):
        data = _minimal_portfolio_json()
        runtime = tmp_path / "portfolio.json"
        runtime.write_text(json.dumps(data), encoding="utf-8")

        monkeypatch.setattr(repo, "_RUNTIME_PATH", runtime)

        portfolio = repo.load_portfolio()
        pos = portfolio.positions[0]

        # buy 10, sell 4 → 6 remaining; gain = 4*(130-100) = 120
        assert pos.total_shares == pytest.approx(6.0)
        assert len(pos.realised_disposals) == 1
        assert pos.realised_disposals[0].total_gain == pytest.approx(120.0)

    def test_load_portfolio_works_with_seed_when_runtime_missing(
        self, tmp_path, monkeypatch
    ):
        missing = tmp_path / "does_not_exist.json"
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps(_minimal_portfolio_json("Seed")), encoding="utf-8")

        monkeypatch.setattr(repo, "_RUNTIME_PATH", missing)
        monkeypatch.setattr(repo, "_SEED_PATH", seed)

        portfolio = repo.load_portfolio()
        assert portfolio.name == "Seed"
        assert len(portfolio.positions) == 1


class TestSavePortfolio:
    def test_save_load_roundtrip_preserves_all_transactions(
        self, tmp_path, monkeypatch
    ):
        data = _minimal_portfolio_json()
        runtime = tmp_path / "portfolio.json"
        runtime.write_text(json.dumps(data), encoding="utf-8")

        monkeypatch.setattr(repo, "_RUNTIME_PATH", runtime)

        # Load, save, reload
        portfolio = repo.load_portfolio()
        repo.save_portfolio(portfolio)
        reloaded = repo.load_portfolio()

        pos = reloaded.positions[0]
        assert len(pos.transactions) == 2
        assert pos.transactions[0].trade_type == "buy"
        assert pos.transactions[1].trade_type == "sell"
        assert pos.total_shares == pytest.approx(6.0)

    def test_save_writes_transactions_not_lots(
        self, tmp_path, monkeypatch
    ):
        data = _minimal_portfolio_json()
        runtime = tmp_path / "portfolio.json"
        runtime.write_text(json.dumps(data), encoding="utf-8")

        monkeypatch.setattr(repo, "_RUNTIME_PATH", runtime)

        portfolio = repo.load_portfolio()
        repo.save_portfolio(portfolio)

        saved = json.loads(runtime.read_text(encoding="utf-8"))
        p = saved["positions"][0]
        assert "transactions" in p
        assert "lots" not in p
        assert all("trade_date" in t for t in p["transactions"])
        assert all("lot_type" not in t for t in p["transactions"])
