"""
app/data/repository.py

Loads and saves portfolio state from JSON storage.

Looks for data/portfolio.json first (runtime, gitignored).
Falls back to app/data/seeds/portfolio.json (committed template).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.portfolio import Portfolio
from app.core.position import Position
from app.core.tax import TaxYear
from app.core.transaction import Transaction
from app.utils.logger import get_logger

logger = get_logger(__name__)

_RUNTIME_PATH = Path("data/portfolio.json")
_SEED_PATH = Path("app/data/seeds/portfolio.json")


def _resolve_path() -> Path:
    if _RUNTIME_PATH.exists():
        return _RUNTIME_PATH
    logger.info("runtime_data_missing_using_seed", seed=str(_SEED_PATH))
    return _SEED_PATH


def load_portfolio() -> Portfolio:
    """
    Load the portfolio from JSON storage.

    Returns:
        Portfolio with all positions and transactions. No live prices — call
        price_service.inject_prices() to add them.
    """
    path = _resolve_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    logger.info("portfolio_loaded", path=str(path), positions=len(raw["positions"]))

    positions: list[Position] = []
    for p in raw["positions"]:
        p = dict(p)
        raw_txns = p.pop("transactions", [])
        transactions = [Transaction(**t) for t in raw_txns]
        pos = Position(**p, transactions=transactions)
        positions.append(pos)

    return Portfolio(name=raw["name"], positions=positions)


def load_tax_year() -> TaxYear | None:
    """
    Load the current tax year state from JSON storage if present.

    Returns:
        TaxYear with YTD figures, or None if the JSON has no tax_year block.
    """
    path = _resolve_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    block = raw.get("tax_year")
    if not block:
        return None
    return TaxYear(**block)


def load_catalysts() -> list[dict]:
    """Load raw catalyst event dicts from storage."""
    path = _resolve_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw.get("catalysts", [])


def load_manual_risk_flags() -> list[dict]:
    """Load manually authored risk flag dicts from storage."""
    path = _resolve_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw.get("risk_flags", [])


def load_behavioural_ledger() -> list[dict]:
    """Load behavioural pattern dicts from storage."""
    path = _resolve_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw.get("behavioural_ledger", [])


def load_session_log() -> list[dict]:
    """Load session log entry dicts from storage."""
    path = _resolve_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw.get("session_log", [])


def save_tax_year(tax_year: TaxYear) -> None:
    """
    Persist tax_year block to data/portfolio.json without touching positions.
    """
    _RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    source = _RUNTIME_PATH if _RUNTIME_PATH.exists() else _SEED_PATH
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["tax_year"] = tax_year.model_dump(mode="json")
    _RUNTIME_PATH.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("tax_year_saved", year=tax_year.year)


def save_portfolio(portfolio: Portfolio) -> None:
    """
    Persist portfolio positions to data/portfolio.json.

    Reads the current full JSON (runtime if present, otherwise seed) to
    preserve non-position sections (catalysts, risk_flags, behavioural_ledger,
    session_log, tax_year), replaces the positions array, and writes to the
    runtime path. Auto-creates the data/ directory if it does not exist.
    """
    _RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)

    source = _RUNTIME_PATH if _RUNTIME_PATH.exists() else _SEED_PATH
    raw = json.loads(source.read_text(encoding="utf-8"))

    raw["name"] = portfolio.name
    raw["positions"] = [
        {
            "ticker": p.ticker,
            "name": p.name,
            "tags": p.tags,
            "horizon": p.horizon.value if p.horizon else None,
            "thesis_status": p.thesis_status.value,
            "thesis_notes": p.thesis_notes,
            "transactions": [
                {
                    "id": t.id,
                    "ticker": t.ticker,
                    "trade_date": t.trade_date.isoformat(),
                    "trade_type": t.trade_type,
                    "shares": t.shares,
                    "price": t.price,
                    "fees": t.fees,
                    "note": t.note,
                }
                for t in p.transactions
            ],
        }
        for p in portfolio.positions
    ]

    _RUNTIME_PATH.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("portfolio_saved", path=str(_RUNTIME_PATH), positions=len(portfolio.positions))
