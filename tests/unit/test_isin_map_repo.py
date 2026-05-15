"""Unit tests for app.adapters.isin_map.repo.JsonIsinMapRepository."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.adapters.isin_map.repo import JsonIsinMapRepository
from app.domain.isin_map import IsinMapDocument, IsinMapping


def test_load_missing_file_returns_empty_document(tmp_path: Path):
    repo = JsonIsinMapRepository(tmp_path / "isin_map.json")
    doc = repo.load()
    assert doc.version == 1
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
    assert loaded.version == 1
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
    assert raw["version"] == 1
    assert "DE0007164600" in raw["entries"]
    assert raw["entries"]["DE0007164600"]["ticker"] == "SAP.DE"
    # date should be serialized as ISO string
    assert raw["entries"]["DE0007164600"]["last_seen_in_csv"] == "2026-01-01"
