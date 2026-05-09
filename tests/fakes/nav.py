from datetime import date

from app.domain.nav import DailyNavPoint


class FakeNavSnapshotRepository:
    """In-memory NavSnapshotRepository for testing.

    Tracks call counts so tests can assert clearing / saving behaviour.
    """

    def __init__(self, initial_points: list[DailyNavPoint] | None = None) -> None:
        self._points: list[DailyNavPoint] = list(initial_points or [])
        self.clear_count = 0
        self.save_count = 0
        self.saved_batches: list[list[DailyNavPoint]] = []

    def load_range(self, start: date, end: date) -> list[DailyNavPoint]:
        return [p for p in self._points if start <= p.snapshot_date <= end]

    def save_points(self, points: list[DailyNavPoint]) -> None:
        self.save_count += 1
        self.saved_batches.append(list(points))
        existing = {p.snapshot_date: p for p in self._points}
        for point in points:
            existing[point.snapshot_date] = point
        self._points = sorted(existing.values(), key=lambda p: p.snapshot_date)

    def clear(self) -> None:
        self.clear_count += 1
        self._points.clear()

    @property
    def all_points(self) -> list[DailyNavPoint]:
        return list(self._points)
