"""Filesystem implementation of the SyncStore port.

Snapshots live in ``<backups_dir>/sync/<snapshot_id>/`` and hold byte-for-byte
copies of ``portfolio.json`` and ``isin_map.json``. Restore uses ``os.replace``
so the files are never loaded and re-serialised — a round-trip through the
models would silently rewrite anything the current schema does not carry.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from app.ports.nav_repository import NavSnapshotRepository
from app.ports.sync_store import SnapshotNotFoundError, SyncSnapshot

MAX_SNAPSHOTS = 10

_PORTFOLIO_NAME = "portfolio.json"
_ISIN_MAP_NAME = "isin_map.json"
_EMPTY_MD5 = hashlib.md5(b"").hexdigest()


def _md5_of(path: Path) -> str:
    """md5 of the file's bytes; a missing file hashes as empty."""
    if not path.exists():
        return _EMPTY_MD5
    return hashlib.md5(path.read_bytes()).hexdigest()


class JsonSyncStore:
    def __init__(
        self,
        portfolio_path: Path,
        isin_map_path: Path,
        backups_dir: Path,
        log_path: Path,
        nav_repo: NavSnapshotRepository,
    ) -> None:
        self.portfolio_path = Path(portfolio_path)
        self.isin_map_path = Path(isin_map_path)
        self.snapshots_dir = Path(backups_dir) / "sync"
        self.log_path = Path(log_path)
        self._nav_repo = nav_repo

    # ─── snapshots ────────────────────────────────────────────────────────────

    def snapshot(self) -> SyncSnapshot:
        created_at = datetime.now()
        snapshot_dir = self._new_snapshot_dir(created_at)
        snapshot_dir.mkdir(parents=True)

        for source, name in (
            (self.portfolio_path, _PORTFOLIO_NAME),
            (self.isin_map_path, _ISIN_MAP_NAME),
        ):
            if source.exists():
                shutil.copyfile(source, snapshot_dir / name)

        self._prune()
        return SyncSnapshot(
            id=snapshot_dir.name,
            created_at=created_at,
            portfolio_md5=_md5_of(self.portfolio_path),
            isin_map_md5=_md5_of(self.isin_map_path),
        )

    def restore(self, snapshot_id: str) -> None:
        snapshot_dir = self.snapshots_dir / snapshot_id
        if not snapshot_dir.is_dir():
            raise SnapshotNotFoundError(snapshot_id)

        for name, target in (
            (_PORTFOLIO_NAME, self.portfolio_path),
            (_ISIN_MAP_NAME, self.isin_map_path),
        ):
            saved = snapshot_dir / name
            if saved.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix(target.suffix + ".restore.tmp")
                shutil.copyfile(saved, tmp)
                os.replace(tmp, target)
            else:
                # The file did not exist when the snapshot was taken, so the
                # pre-session state is "absent", not "empty".
                target.unlink(missing_ok=True)

        self._nav_repo.clear()

    def current_md5s(self) -> tuple[str, str]:
        return _md5_of(self.portfolio_path), _md5_of(self.isin_map_path)

    def _new_snapshot_dir(self, created_at: datetime) -> Path:
        base = created_at.strftime("%Y%m%dT%H%M%S%f")
        candidate = self.snapshots_dir / base
        suffix = 1
        while candidate.exists():
            candidate = self.snapshots_dir / f"{base}-{suffix}"
            suffix += 1
        return candidate

    def _prune(self) -> None:
        existing = sorted(
            (d for d in self.snapshots_dir.iterdir() if d.is_dir()),
            key=lambda d: d.name,
        )
        for stale in existing[:-MAX_SNAPSHOTS]:
            shutil.rmtree(stale, ignore_errors=True)

    # ─── log ──────────────────────────────────────────────────────────────────

    def read_log(self) -> list[dict[str, object]]:
        if not self.log_path.exists():
            return []
        try:
            with open(self.log_path, encoding="utf-8") as f:
                entries: list[dict[str, object]] = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
        return entries

    def append_log(self, entry: dict[str, object]) -> None:
        entries = self.read_log()
        entries.append(entry)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.log_path.with_suffix(self.log_path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.log_path)
