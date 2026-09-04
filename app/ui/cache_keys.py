"""Cache-key helpers shared across Streamlit pages."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.domain.models import Transaction


def transactions_signature(transactions: list[Transaction]) -> str:
    """Stable key over a transaction list: ids *and* tickers.

    A mapping change rewrites tickers in place without changing the row count,
    so an id-only key would keep every cached page on the old ticker
    (ADR-014 consequence 1).
    """
    if not transactions:
        return "empty"
    payload = "|".join(sorted(f"{tx.id}:{tx.ticker}" for tx in transactions))
    digest = hashlib.sha1(payload.encode()).hexdigest()[:12]
    return f"{len(transactions)}:{digest}"


def file_mtime_key(path: Path) -> str:
    """Key based on file mtime; changes when the file is written."""
    try:
        return str(os.path.getmtime(path))
    except OSError:
        return "missing"
