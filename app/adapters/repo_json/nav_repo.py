"""JSON-backed NAV snapshot repository.

Uses the same atomic-write pattern as JsonTransactionRepository:
  temp file → fsync → os.replace

Storage format (data/nav_snapshots.json):
  {"version": 1, "snapshots": [...DailyNavPoint as dicts...]}

Snapshots are kept sorted ascending by snapshot_date.

clear() deletes the file entirely (simpler than zeroing it; same effect on next load).
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from app.domain.nav import DailyNavPoint
from app.ports.nav_repository import NavSnapshotRepository  # noqa: F401 — satisfies Protocol


class SchemaVersionError(Exception):
    """Raised when the nav_snapshots.json schema version is unrecognised."""

    pass


class JsonNavSnapshotRepository:
    SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path

    # ------------------------------------------------------------------
    # NavSnapshotRepository protocol
    # ------------------------------------------------------------------

    def load_range(self, start: date, end: date) -> list[DailyNavPoint]:
        all_points = self._load_all()
        return [p for p in all_points if start <= p.snapshot_date <= end]

    def save_points(self, points: list[DailyNavPoint]) -> None:
        existing = {p.snapshot_date: p for p in self._load_all()}
        for point in points:
            existing[point.snapshot_date] = point
        merged = sorted(existing.values(), key=lambda p: p.snapshot_date)
        self._write(merged)

    def clear(self) -> None:
        """Delete the snapshots file. On the next load_range call the cache is empty."""
        if self.path.exists():
            self.path.unlink()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_all(self) -> list[DailyNavPoint]:
        if not self.path.exists():
            return []

        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise SchemaVersionError(f"Failed to read nav_snapshots.json: {e}") from e

        version = data.get("version")
        if version is None:
            raise SchemaVersionError(
                "nav_snapshots.json is missing 'version'. "
                "This may be a v0 file; delete it to rebuild."
            )
        if version != self.SCHEMA_VERSION:
            downgrade_note = (
                " Downgrade is not supported; delete the file to rebuild."
                if version > self.SCHEMA_VERSION
                else ""
            )
            raise SchemaVersionError(
                f"nav_snapshots.json version {version} is not supported "
                f"(expected {self.SCHEMA_VERSION}).{downgrade_note}"
            )

        points: list[DailyNavPoint] = []
        for raw in data.get("snapshots", []):
            try:
                points.append(DailyNavPoint.model_validate(raw))
            except ValidationError as e:
                raise SchemaVersionError(f"Invalid snapshot record: {e}") from e

        return sorted(points, key=lambda p: p.snapshot_date)

    def _write(self, points: list[DailyNavPoint]) -> None:
        data = {
            "version": self.SCHEMA_VERSION,
            "snapshots": [p.model_dump(mode="json") for p in points],
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")

        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise
