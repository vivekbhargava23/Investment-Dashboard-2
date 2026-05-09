"""Integration tests for JsonNavSnapshotRepository.

Uses real files in a temp directory — no mocking.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from app.adapters.repo_json.nav_repo import JsonNavSnapshotRepository, SchemaVersionError
from app.domain.money import Currency, Money
from app.domain.nav import DailyNavPoint


def _make_point(d: date, nav: str = "1000", cost: str = "900", n: int = 3) -> DailyNavPoint:
    return DailyNavPoint(
        snapshot_date=d,
        nav_eur=Money(amount=Decimal(nav), currency=Currency.EUR),
        cost_basis_eur=Money(amount=Decimal(cost), currency=Currency.EUR),
        n_positions=n,
        is_reconstructed=True,
    )


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> JsonNavSnapshotRepository:
    return JsonNavSnapshotRepository(tmp_path / "nav_snapshots.json")


# ---------------------------------------------------------------------------
# Test 13 — Save → load round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_decimal_precision_preserved(self, tmp_repo: JsonNavSnapshotRepository) -> None:
        p = _make_point(date(2025, 6, 1), nav="12345.6789", cost="10000.1234")
        tmp_repo.save_points([p])
        loaded = tmp_repo.load_range(date(2025, 1, 1), date(2025, 12, 31))
        assert len(loaded) == 1
        assert loaded[0].nav_eur.amount == p.nav_eur.amount
        assert loaded[0].cost_basis_eur.amount == p.cost_basis_eur.amount

    def test_date_preserved(self, tmp_repo: JsonNavSnapshotRepository) -> None:
        d = date(2024, 12, 31)
        tmp_repo.save_points([_make_point(d)])
        loaded = tmp_repo.load_range(d, d)
        assert loaded[0].snapshot_date == d

    def test_sort_order_ascending(self, tmp_repo: JsonNavSnapshotRepository) -> None:
        points = [
            _make_point(date(2025, 3, 1)),
            _make_point(date(2025, 1, 15)),
            _make_point(date(2025, 2, 10)),
        ]
        tmp_repo.save_points(points)
        loaded = tmp_repo.load_range(date(2025, 1, 1), date(2025, 12, 31))
        dates = [p.snapshot_date for p in loaded]
        assert dates == sorted(dates)

    def test_load_range_filters_by_date(self, tmp_repo: JsonNavSnapshotRepository) -> None:
        tmp_repo.save_points([
            _make_point(date(2025, 1, 1)),
            _make_point(date(2025, 6, 1)),
            _make_point(date(2025, 12, 31)),
        ])
        loaded = tmp_repo.load_range(date(2025, 5, 1), date(2025, 7, 1))
        assert len(loaded) == 1
        assert loaded[0].snapshot_date == date(2025, 6, 1)

    def test_save_points_merges_by_date(self, tmp_repo: JsonNavSnapshotRepository) -> None:
        d = date(2025, 6, 1)
        tmp_repo.save_points([_make_point(d, nav="1000")])
        tmp_repo.save_points([_make_point(d, nav="1500")])  # upsert
        loaded = tmp_repo.load_range(d, d)
        assert len(loaded) == 1
        assert loaded[0].nav_eur.amount == Decimal("1500")

    def test_empty_repo_returns_empty_list(self, tmp_repo: JsonNavSnapshotRepository) -> None:
        result = tmp_repo.load_range(date(2025, 1, 1), date(2025, 12, 31))
        assert result == []


# ---------------------------------------------------------------------------
# Test 14 — Atomic write: crash mid-write leaves original intact
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_crash_mid_write_leaves_original(self, tmp_repo: JsonNavSnapshotRepository) -> None:
        # Write a good initial state.
        p1 = _make_point(date(2025, 1, 1), nav="1000")
        tmp_repo.save_points([p1])

        # Simulate a crash at os.replace (after fsync but before rename).
        with patch("os.replace", side_effect=OSError("simulated crash")):
            with pytest.raises(OSError):
                tmp_repo.save_points([_make_point(date(2025, 2, 1), nav="2000")])

        # The original file must still be the good state.
        loaded = tmp_repo.load_range(date(2025, 1, 1), date(2025, 12, 31))
        assert len(loaded) == 1
        assert loaded[0].nav_eur.amount == Decimal("1000")

        # The tmp file must have been cleaned up.
        tmp_path = tmp_repo.path.with_suffix(tmp_repo.path.suffix + ".tmp")
        assert not tmp_path.exists()


# ---------------------------------------------------------------------------
# Test 15 — Schema versioning
# ---------------------------------------------------------------------------


class TestSchemaVersioning:
    def test_missing_version_raises(self, tmp_repo: JsonNavSnapshotRepository) -> None:
        tmp_repo.path.write_text('{"snapshots": []}')
        with pytest.raises(SchemaVersionError, match="missing 'version'"):
            tmp_repo.load_range(date(2025, 1, 1), date(2025, 12, 31))

    def test_future_version_raises(self, tmp_repo: JsonNavSnapshotRepository) -> None:
        tmp_repo.path.write_text('{"version": 99, "snapshots": []}')
        with pytest.raises(SchemaVersionError, match="not supported"):
            tmp_repo.load_range(date(2025, 1, 1), date(2025, 12, 31))

    def test_current_version_loads_fine(self, tmp_repo: JsonNavSnapshotRepository) -> None:
        data = {"version": 1, "snapshots": []}
        tmp_repo.path.write_text(json.dumps(data))
        result = tmp_repo.load_range(date(2025, 1, 1), date(2025, 12, 31))
        assert result == []


# ---------------------------------------------------------------------------
# Test 16 — clear() deletes the file
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_removes_file(self, tmp_repo: JsonNavSnapshotRepository) -> None:
        tmp_repo.save_points([_make_point(date(2025, 6, 1))])
        assert tmp_repo.path.exists()
        tmp_repo.clear()
        assert not tmp_repo.path.exists()

    def test_clear_on_nonexistent_file_is_safe(self, tmp_repo: JsonNavSnapshotRepository) -> None:
        assert not tmp_repo.path.exists()
        tmp_repo.clear()  # Should not raise.

    def test_load_after_clear_returns_empty(self, tmp_repo: JsonNavSnapshotRepository) -> None:
        tmp_repo.save_points([_make_point(date(2025, 6, 1))])
        tmp_repo.clear()
        result = tmp_repo.load_range(date(2025, 1, 1), date(2025, 12, 31))
        assert result == []
