"""Unit tests for app.adapters.thesis_map.repo.JsonThesisMapRepository."""
from __future__ import annotations

import json
from pathlib import Path

from app.adapters.thesis_map.repo import JsonThesisMapRepository
from app.domain.thesis_map import ThesisEntry, ThesisMapDocument


def test_load_missing_file_returns_empty_document(tmp_path: Path):
    repo = JsonThesisMapRepository(tmp_path / "thesis.json")
    doc = repo.load()
    assert doc.version == 1
    assert doc.entries == {}


def test_save_then_load_roundtrips(tmp_path: Path):
    path = tmp_path / "thesis.json"
    repo = JsonThesisMapRepository(path)

    doc = ThesisMapDocument(
        entries={
            "NVDA": ThesisEntry(thesis="intact", horizon="H1"),
            "APD": ThesisEntry(thesis="watch", horizon="H2"),
        }
    )
    repo.save(doc)

    loaded = repo.load()
    assert loaded.version == 1
    assert len(loaded.entries) == 2
    assert loaded.entries["NVDA"].thesis == "intact"
    assert loaded.entries["NVDA"].horizon == "H1"
    assert loaded.entries["APD"].thesis == "watch"


def test_atomic_save_no_tmp_leftover(tmp_path: Path):
    path = tmp_path / "thesis.json"
    repo = JsonThesisMapRepository(path)
    repo.save(ThesisMapDocument())

    tmp = path.with_suffix(path.suffix + ".tmp")
    assert not tmp.exists()
    assert path.exists()


def test_save_creates_parent_directory(tmp_path: Path):
    nested = tmp_path / "subdir" / "thesis.json"
    repo = JsonThesisMapRepository(nested)
    repo.save(ThesisMapDocument())
    assert nested.exists()


def test_saved_file_is_valid_json(tmp_path: Path):
    path = tmp_path / "thesis.json"
    repo = JsonThesisMapRepository(path)
    repo.save(ThesisMapDocument(entries={"MU": ThesisEntry(thesis="broken", horizon="H3")}))

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert raw["entries"]["MU"]["thesis"] == "broken"
    assert raw["entries"]["MU"]["horizon"] == "H3"


def test_committed_seed_file_loads_with_known_values():
    """The repo-committed data/thesis.json validates and carries the seed values."""
    repo = JsonThesisMapRepository(Path("data/thesis.json"))
    doc = repo.load()
    assert doc.entries["NVDA"].thesis == "intact"
    assert doc.entries["NVDA"].horizon == "H1"
    assert doc.entries["APD"].thesis == "watch"
