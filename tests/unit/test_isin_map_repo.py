"""Unit tests for app.adapters.isin_map.repo.JsonIsinMapRepository."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from app.adapters.isin_map.repo import JsonIsinMapRepository
from app.domain.isin_map import IsinMapDocument, IsinMapping


def test_load_missing_file_returns_empty_document(tmp_path: Path):
    repo = JsonIsinMapRepository(tmp_path / "isin_map.json")
    doc = repo.load()
    assert doc.version == 2
    assert doc.entries == {}


def test_save_then_load_roundtrips(tmp_path: Path):
    path = tmp_path / "isin_map.json"
    repo = JsonIsinMapRepository(path)

    doc = IsinMapDocument(
        entries={
            "DE0007164600": IsinMapping(
                ticker="SAP.DE",
                name="SAP SE",
                status="mapped",
                last_seen_in_csv=date(2026, 3, 1),
            ),
            "JP3721400004": IsinMapping(
                ticker=None,
                name="Japan Steel Works",
                status="unmapped",
                last_seen_in_csv=None,
            ),
        }
    )
    repo.save(doc)

    loaded = repo.load()
    assert loaded.version == 2
    assert len(loaded.entries) == 2

    sap = loaded.entries["DE0007164600"]
    assert sap.ticker == "SAP.DE"
    assert sap.name == "SAP SE"
    assert sap.status == "mapped"
    assert sap.last_seen_in_csv == date(2026, 3, 1)

    jsw = loaded.entries["JP3721400004"]
    assert jsw.ticker is None
    assert jsw.status == "unmapped"
    assert jsw.last_seen_in_csv is None


def test_entries_dict_enforces_unique_isin():
    """The entries field is a dict so the same ISIN cannot appear twice."""
    # Build via regular dict assignment to prove uniqueness is enforced
    raw: dict[str, IsinMapping] = {}
    raw["DE0007164600"] = IsinMapping(ticker="SAP.DE", name="SAP SE", status="mapped")
    raw["DE0007164600"] = IsinMapping(ticker="SAP2.DE", name="SAP SE alt", status="mapped")
    doc = IsinMapDocument(entries=raw)
    assert len(doc.entries) == 1
    assert doc.entries["DE0007164600"].ticker == "SAP2.DE"


def test_atomic_save_no_tmp_leftover(tmp_path: Path):
    """After a successful save, no .tmp file remains."""
    path = tmp_path / "isin_map.json"
    repo = JsonIsinMapRepository(path)

    repo.save(IsinMapDocument())

    tmp = path.with_suffix(path.suffix + ".tmp")
    assert not tmp.exists()
    assert path.exists()


def test_save_creates_parent_directory(tmp_path: Path):
    nested = tmp_path / "subdir" / "isin_map.json"
    repo = JsonIsinMapRepository(nested)
    repo.save(IsinMapDocument())
    assert nested.exists()


def test_saved_file_is_valid_json(tmp_path: Path):
    path = tmp_path / "isin_map.json"
    repo = JsonIsinMapRepository(path)

    doc = IsinMapDocument(
        entries={
            "DE0007164600": IsinMapping(
                ticker="SAP.DE",
                name="SAP SE",
                status="mapped",
                last_seen_in_csv=date(2026, 1, 1),
            )
        }
    )
    repo.save(doc)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 2
    assert "DE0007164600" in raw["entries"]
    assert raw["entries"]["DE0007164600"]["ticker"] == "SAP.DE"
    # date should be serialized as ISO string
    assert raw["entries"]["DE0007164600"]["last_seen_in_csv"] == "2026-01-01"


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------


def test_load_migrates_v1_to_v2(tmp_path: Path):
    """Loading a v1 file upgrades it to v2 and rewrites the file atomically."""
    path = tmp_path / "isin_map.json"
    v1_fixture = {
        "version": 1,
        "entries": {
            "DE0007164600": {
                "ticker": "SAP.DE",
                "name": "SAP SE",
                "status": "mapped",
                "last_seen_in_csv": "2026-03-01",
                "instrument_kind": None,
            }
        },
    }
    path.write_text(json.dumps(v1_fixture), encoding="utf-8")

    repo = JsonIsinMapRepository(path)
    doc = repo.load()

    assert doc.version == 2
    assert doc.entries["DE0007164600"].ticker == "SAP.DE"

    # Confirm the file was rewritten with version 2
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["version"] == 2


def test_load_v2_no_migration(tmp_path: Path):
    """Loading a v2 file does not trigger a rewrite."""
    path = tmp_path / "isin_map.json"
    v2_fixture = {
        "version": 2,
        "entries": {
            "DE0007164600": {
                "ticker": "SAP.DE",
                "name": "SAP SE",
                "status": "mapped",
                "last_seen_in_csv": None,
                "instrument_kind": None,
            }
        },
    }
    path.write_text(json.dumps(v2_fixture), encoding="utf-8")

    repo = JsonIsinMapRepository(path)
    with patch.object(repo, "_atomic_write") as mock_write:
        loaded = repo.load()

    mock_write.assert_not_called()
    assert loaded.version == 2
    assert loaded.entries["DE0007164600"].ticker == "SAP.DE"


def test_load_ignored_status_roundtrip(tmp_path: Path):
    """A v2 file with an ignored entry survives load with status intact."""
    path = tmp_path / "isin_map.json"
    v2_fixture = {
        "version": 2,
        "entries": {
            "CH0491507486": {
                "ticker": None,
                "name": "21shares Tezos ETP",
                "status": "ignored",
                "last_seen_in_csv": "2026-05-01",
                "instrument_kind": None,
            }
        },
    }
    path.write_text(json.dumps(v2_fixture), encoding="utf-8")

    repo = JsonIsinMapRepository(path)
    doc = repo.load()

    assert doc.entries["CH0491507486"].status == "ignored"
    assert doc.entries["CH0491507486"].ticker is None
