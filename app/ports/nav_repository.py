from datetime import date
from typing import Protocol

from app.domain.nav import DailyNavPoint


class NavSnapshotRepository(Protocol):
    """Port for persisting and retrieving daily NAV snapshots."""

    def load_range(self, start: date, end: date) -> list[DailyNavPoint]:
        """Return all cached snapshots with snapshot_date in [start, end], sorted ascending."""
        ...

    def save_points(self, points: list[DailyNavPoint]) -> None:
        """Upsert points into the store (merge by snapshot_date, then sort ascending)."""
        ...

    def clear(self) -> None:
        """Drop all cached snapshots. Called after any transaction edit (ADR-003 replay)."""
        ...
