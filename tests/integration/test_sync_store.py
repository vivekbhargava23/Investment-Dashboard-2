"""Integration tests for JsonSyncStore on a real temp filesystem."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.adapters.sync_store.json_store import MAX_SNAPSHOTS, JsonSyncStore
from app.ports.sync_store import SnapshotNotFoundError
from tests.fakes.nav import FakeNavSnapshotRepository


def _make_store(tmp_path: Path) -> tuple[JsonSyncStore, Path, Path, FakeNavSnapshotRepository]:
    portfolio = tmp_path / "data" / "portfolio.json"
    isin_map = tmp_path / "data" / "isin_map.json"
    portfolio.parent.mkdir(parents=True, exist_ok=True)
    portfolio.write_bytes(b'{"version": 3, "transactions": []}')
    isin_map.write_bytes(b'{"version": 2, "entries": {}}')
    nav_repo = FakeNavSnapshotRepository()
    store = JsonSyncStore(
        portfolio_path=portfolio,
        isin_map_path=isin_map,
        backups_dir=tmp_path / "data" / "backups",
        log_path=tmp_path / "data" / "sync_log.json",
        nav_repo=nav_repo,
    )
    return store, portfolio, isin_map, nav_repo


def test_snapshot_restore_is_byte_for_byte(tmp_path: Path):
    store, portfolio, isin_map, nav_repo = _make_store(tmp_path)
    before_portfolio = portfolio.read_bytes()
    before_isin_map = isin_map.read_bytes()

    snapshot = store.snapshot()

    portfolio.write_bytes(b'{"version": 3, "transactions": [1, 2, 3]}')
    isin_map.write_bytes(b'{"version": 2, "entries": {"DE0007164600": {}}}')
    assert store.current_md5s() != (snapshot.portfolio_md5, snapshot.isin_map_md5)

    store.restore(snapshot.id)

    assert portfolio.read_bytes() == before_portfolio
    assert isin_map.read_bytes() == before_isin_map
    assert store.current_md5s() == (snapshot.portfolio_md5, snapshot.isin_map_md5)
    assert nav_repo.clear_count == 1


def test_snapshot_records_current_md5s(tmp_path: Path):
    store, portfolio, isin_map, _ = _make_store(tmp_path)
    snapshot = store.snapshot()
    assert snapshot.portfolio_md5 == hashlib.md5(portfolio.read_bytes()).hexdigest()
    assert snapshot.isin_map_md5 == hashlib.md5(isin_map.read_bytes()).hexdigest()


def test_restore_removes_a_file_that_did_not_exist_at_snapshot_time(tmp_path: Path):
    store, _, isin_map, _ = _make_store(tmp_path)
    isin_map.unlink()

    snapshot = store.snapshot()
    isin_map.write_bytes(b'{"version": 2, "entries": {"X": {}}}')
    store.restore(snapshot.id)

    assert not isin_map.exists()


def test_restore_unknown_snapshot_raises(tmp_path: Path):
    store, _, _, _ = _make_store(tmp_path)
    with pytest.raises(SnapshotNotFoundError):
        store.restore("nope")


def test_only_the_ten_newest_snapshots_are_kept(tmp_path: Path):
    store, _, _, _ = _make_store(tmp_path)
    ids = [store.snapshot().id for _ in range(MAX_SNAPSHOTS + 3)]
    kept = sorted(d.name for d in store.snapshots_dir.iterdir())
    assert kept == sorted(ids[-MAX_SNAPSHOTS:])


def test_log_round_trips(tmp_path: Path):
    store, _, _, _ = _make_store(tmp_path)
    assert store.read_log() == []

    store.append_log({"event": "session_start", "session_id": "s1"})
    store.append_log({"event": "apply", "session_id": "s1", "inserted": 3})

    assert store.read_log() == [
        {"event": "session_start", "session_id": "s1"},
        {"event": "apply", "session_id": "s1", "inserted": 3},
    ]


def test_unreadable_log_reads_as_empty(tmp_path: Path):
    store, _, _, _ = _make_store(tmp_path)
    store.log_path.parent.mkdir(parents=True, exist_ok=True)
    store.log_path.write_text("not json")
    assert store.read_log() == []
