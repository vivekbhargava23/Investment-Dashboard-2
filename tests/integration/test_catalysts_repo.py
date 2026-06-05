"""Integration tests for JsonCatalystsRepository and the seed file."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.adapters.catalysts.repo import JsonCatalystsRepository
from app.domain.catalysts import CatalystEvent, CatalystsDocument


def _doc() -> CatalystsDocument:
    return CatalystsDocument(
        version=1,
        updated=date(2026, 6, 5),
        events=[
            CatalystEvent(
                ticker="NVDA",
                date=date(2026, 8, 26),
                label="Q2 FY27 earnings",
                category="earnings",
                impact="high",
                scope="position",
                date_confidence="estimated",
                source="investor.nvidia.com",
            ),
            CatalystEvent(
                ticker=None,
                date=date(2026, 6, 17),
                label="FOMC rate decision",
                category="macro",
                impact="med",
                scope="portfolio",
                date_confidence="confirmed",
                source="federalreserve.gov",
            ),
        ],
    )


@pytest.mark.integration
def test_missing_file_returns_empty_document(tmp_path: Path) -> None:
    repo = JsonCatalystsRepository(tmp_path / "does_not_exist.json")
    doc = repo.load()
    assert doc == CatalystsDocument()
    assert doc.events == []


@pytest.mark.integration
def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "catalysts.json"
    repo = JsonCatalystsRepository(path)
    doc = _doc()

    repo.save(doc)
    loaded = repo.load()

    assert loaded == doc


@pytest.mark.integration
def test_round_trip_stable_json(tmp_path: Path) -> None:
    """The serialised form is stable across a save → load → save cycle."""
    path = tmp_path / "catalysts.json"
    repo = JsonCatalystsRepository(path)
    doc = _doc()

    repo.save(doc)
    first = path.read_text()
    repo.save(repo.load())
    second = path.read_text()

    assert first == second
    # And it matches model_dump(mode="json") content.
    assert json.loads(first) == doc.model_dump(mode="json")


@pytest.mark.integration
def test_atomic_write_preserves_original_on_failure(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "catalysts.json"
    repo = JsonCatalystsRepository(path)
    repo.save(_doc())

    def _fail_replace(src: str, dst: str) -> None:
        raise OSError("Simulated disk failure")

    monkeypatch.setattr(
        "app.adapters.catalysts.repo.os.replace", _fail_replace
    )

    with pytest.raises(OSError):
        repo.save(CatalystsDocument())

    assert JsonCatalystsRepository(path).load() == _doc()


@pytest.mark.integration
def test_seed_file_validates_and_has_sources() -> None:
    """The committed seed validates and every event carries a source."""
    seed_path = Path(__file__).parent.parent.parent / "data" / "catalysts.json"
    repo = JsonCatalystsRepository(seed_path)

    doc = repo.load()

    assert doc.version == 1
    assert doc.events, "seed should contain events"
    assert all(e.source.strip() for e in doc.events)
    # At least one portfolio-wide macro event is present.
    assert any(e.scope == "portfolio" for e in doc.events)
