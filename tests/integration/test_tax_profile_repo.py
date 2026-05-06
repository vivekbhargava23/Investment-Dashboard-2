"""Integration tests for JsonTaxProfileRepository."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.repo_json.tax_profile_repo import JsonTaxProfileRepository, LegacyTaxProfileError
from app.domain.money import Currency, Money
from app.domain.tax.models import FilingStatus
from app.ports.tax_profile_repo import TaxProfileDocument, YearlyTaxInputs

_EUR = Currency.EUR


def _m(v: str) -> Money:
    return Money(amount=Decimal(v), currency=_EUR)


@pytest.mark.integration
def test_round_trip(tmp_path: Path) -> None:
    """Save a document, load it back, assert equality."""
    repo = JsonTaxProfileRepository(tmp_path / "tax_profile.json")
    doc = TaxProfileDocument(
        version=1,
        filing_status=FilingStatus.SINGLE,
        per_year={
            2026: YearlyTaxInputs(
                carryforward_aktien_eur=_m("300"),
                carryforward_general_eur=_m("200"),
                additional_dividend_income_eur=_m("50"),
                additional_interest_income_eur=_m("10"),
            )
        },
    )
    repo.save(doc)
    loaded = repo.load()
    assert loaded == doc


@pytest.mark.integration
def test_missing_file_returns_default(tmp_path: Path) -> None:
    """load() on a non-existent path returns a default TaxProfileDocument."""
    repo = JsonTaxProfileRepository(tmp_path / "does_not_exist.json")
    doc = repo.load()
    assert doc.version == 1
    assert doc.filing_status == FilingStatus.SINGLE
    assert doc.per_year == {}


@pytest.mark.integration
def test_atomic_write_preserves_original_on_failure(tmp_path: Path, monkeypatch) -> None:
    """Simulate a write failure: original file must remain intact."""
    path = tmp_path / "tax_profile.json"
    repo = JsonTaxProfileRepository(path)

    initial = TaxProfileDocument(
        version=1,
        filing_status=FilingStatus.SINGLE,
        per_year={2025: YearlyTaxInputs(carryforward_aktien_eur=_m("100"))},
    )
    repo.save(initial)

    def _fail_replace(src: str, dst: str) -> None:
        raise OSError("Simulated disk failure")

    monkeypatch.setattr("app.adapters.repo_json.tax_profile_repo.os.replace", _fail_replace)

    corrupt_doc = TaxProfileDocument(
        version=1,
        filing_status=FilingStatus.JOINT,
        per_year={2026: YearlyTaxInputs(carryforward_aktien_eur=_m("9999"))},
    )
    with pytest.raises(OSError):
        repo.save(corrupt_doc)

    # Original must still be intact
    loaded = JsonTaxProfileRepository(path).load()
    assert loaded == initial


@pytest.mark.integration
def test_legacy_version_raises(tmp_path: Path) -> None:
    """load() on a file with version != 1 raises LegacyTaxProfileError."""
    fixture = Path(__file__).parent.parent / "fixtures" / "tax_profile_legacy_v0.json"
    path = tmp_path / "tax_profile.json"
    path.write_text(fixture.read_text())
    repo = JsonTaxProfileRepository(path)
    with pytest.raises(LegacyTaxProfileError) as exc_info:
        repo.load()
    assert exc_info.value.found_version == 0
