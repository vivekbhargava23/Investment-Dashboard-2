"""Port for the sync session store: snapshots, restore, md5s and the sync log."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class SyncSnapshot(BaseModel):
    """A byte-for-byte copy of both data files, taken before a sync session writes."""

    model_config = ConfigDict(frozen=True)

    id: str
    created_at: datetime
    portfolio_md5: str
    isin_map_md5: str


class SnapshotNotFoundError(Exception):
    def __init__(self, snapshot_id: str) -> None:
        super().__init__(f"Snapshot {snapshot_id} not found")
        self.snapshot_id = snapshot_id


class SyncStore(Protocol):
    """Snapshot/restore of ``portfolio.json`` + ``isin_map.json`` plus the sync log."""

    def snapshot(self) -> SyncSnapshot:
        """Copy both data files aside and return the snapshot's identity."""
        ...

    def restore(self, snapshot_id: str) -> None:
        """Put both files back byte-for-byte and clear the NAV cache.

        Raises :class:`SnapshotNotFoundError` if the snapshot no longer exists.
        """
        ...

    def current_md5s(self) -> tuple[str, str]:
        """Return ``(portfolio_md5, isin_map_md5)`` for the files as they are now."""
        ...

    def append_log(self, entry: dict[str, object]) -> None:
        """Append one entry to the sync log."""
        ...

    def read_log(self) -> list[dict[str, object]]:
        """Return the sync log, oldest first."""
        ...
