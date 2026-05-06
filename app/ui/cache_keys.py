"""Cache-key helpers shared across Streamlit pages."""

from __future__ import annotations

import os
from pathlib import Path

from app.domain.models import Transaction


def transactions_signature(transactions: list[Transaction]) -> str:
    """Stable key over a transaction list: changes when any tx is added/removed."""
    if not transactions:
        return "empty"
    sorted_ids = sorted(str(tx.id) for tx in transactions)
    return f"{len(transactions)}:{sorted_ids[-1]}"


def file_mtime_key(path: Path) -> str:
    """Key based on file mtime; changes when the file is written."""
    try:
        return str(os.path.getmtime(path))
    except OSError:
        return "missing"
