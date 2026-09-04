"""In-memory SyncStore for tests.

Files are dicts of name → bytes so a test can assert "restored byte-for-byte"
without touching the filesystem.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from app.ports.sync_store import SnapshotNotFoundError, SyncSnapshot


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


class FakeSyncStore:
    def __init__(
        self,
        portfolio_bytes: bytes = b"{}",
        isin_map_bytes: bytes = b"{}",
    ) -> None:
        self.portfolio_bytes = portfolio_bytes
        self.isin_map_bytes = isin_map_bytes
        self.snapshots: dict[str, tuple[bytes, bytes]] = {}
        self.log: list[dict[str, object]] = []
        self.restore_calls: list[str] = []
        self._counter = 0

    def snapshot(self) -> SyncSnapshot:
        self._counter += 1
        snapshot_id = f"snap-{self._counter}"
        self.snapshots[snapshot_id] = (self.portfolio_bytes, self.isin_map_bytes)
        return SyncSnapshot(
            id=snapshot_id,
            created_at=datetime(2026, 9, 4, 12, 0, self._counter),
            portfolio_md5=_md5(self.portfolio_bytes),
            isin_map_md5=_md5(self.isin_map_bytes),
        )

    def restore(self, snapshot_id: str) -> None:
        if snapshot_id not in self.snapshots:
            raise SnapshotNotFoundError(snapshot_id)
        self.restore_calls.append(snapshot_id)
        self.portfolio_bytes, self.isin_map_bytes = self.snapshots[snapshot_id]

    def current_md5s(self) -> tuple[str, str]:
        return _md5(self.portfolio_bytes), _md5(self.isin_map_bytes)

    def append_log(self, entry: dict[str, object]) -> None:
        self.log.append(entry)

    def read_log(self) -> list[dict[str, object]]:
        return list(self.log)

    # ─── test helpers ─────────────────────────────────────────────────────────

    def events(self) -> list[str]:
        return [str(entry["event"]) for entry in self.log]
