"""Shared portfolio.json backup helper for the UI layer.

Every destructive write in the UI — the instrument card's Remove, the Manage
Portfolio danger zone — writes a timestamped backup of ``portfolio.json`` first.
This is the single implementation of that rolling-window backup.
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


def backup_portfolio_before_purge() -> None:
    """Back up ``portfolio.json`` before a destructive purge, if it exists yet.

    Reads the configured paths itself so every caller gets the same rolling
    window without repeating the wiring. No-op when there is nothing to purge.
    """
    from app.config import get_settings

    settings = get_settings()
    portfolio_path = Path(settings.portfolio_json_path)
    if portfolio_path.exists():
        write_portfolio_backup(portfolio_path, settings.backups_dir)
