"""Shared portfolio.json backup helper for the UI layer.

The import workbench, the mappings page, and the Manage Portfolio danger zone all
write a timestamped backup of ``portfolio.json`` before a destructive write. This
is the single implementation of that rolling-window backup.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

_RETAIN = 10


def write_portfolio_backup(portfolio_path: Path, backups_dir: Path) -> Path:
    """Copy ``portfolio.json`` to a timestamped ``.bak``, keeping the 10 most recent."""
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    bak = backups_dir / f"portfolio.{stamp}.json.bak"
    shutil.copy2(portfolio_path, bak)
    existing = sorted(backups_dir.glob("portfolio.*.json.bak"))
    for old in existing[:-_RETAIN]:
        old.unlink(missing_ok=True)
    return bak
