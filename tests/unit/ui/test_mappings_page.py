"""Unit tests for app.ui.pages.mappings (pure helpers, no Streamlit context)."""
from __future__ import annotations

from datetime import date

import pytest

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.ui.pages.mappings import (
    _delete_mapping,
    _init_state,
    _save_mapping,
    _validate_ticker,
)

# ---------------------------------------------------------------------------
# _validate_ticker
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ticker", [
    "NVDA",
    "VUAA.DE",
    "5631.T",
    "PARRO.PA",
    "RHM.DE",
    "A",
    "HXSCL",
])
def test_validate_ticker_accepts_valid(ticker: str) -> None:
    assert _validate_ticker(ticker) is None


@pytest.mark.parametrize("ticker", [
    "",
    "   ",
    "nvda",
    "nvda.de",
    "NVDA!",
    "NV DA",
    "NVDA@",
])
def test_validate_ticker_rejects_invalid(ticker: str) -> None:
    assert _validate_ticker(ticker) is not None


def test_validate_ticker_strips_whitespace_before_check() -> None:
    assert _validate_ticker("  ") is not None


# ---------------------------------------------------------------------------
# _save_mapping
# ---------------------------------------------------------------------------

def _make_doc(**entries: IsinMapping) -> IsinMapDocument:
    return IsinMapDocument(entries=dict(entries))


def test_save_mapping_flips_status_to_mapped() -> None:
    isin = "CA65704Y1079"
    doc = _make_doc(**{
        isin: IsinMapping(ticker=None, name="North American Niobium", status="unmapped",
                          last_seen_in_csv=date(2026, 4, 20))
    })
    updated, _ = _save_mapping(isin, "NAN.V", doc)
    entry = updated.entries[isin]
    assert entry.ticker == "NAN.V"
    assert entry.status == "mapped"
    assert entry.name == "North American Niobium"
    assert entry.last_seen_in_csv == date(2026, 4, 20)


def test_save_mapping_updates_existing_mapped_entry() -> None:
    isin = "DE0007030009"
    doc = _make_doc(**{
        isin: IsinMapping(ticker="RHM.DE", name="Rheinmetall", status="mapped",
                          last_seen_in_csv=date(2026, 3, 30))
    })
    updated, _ = _save_mapping(isin, "RHM.XETRA", doc)
    assert updated.entries[isin].ticker == "RHM.XETRA"
    assert updated.entries[isin].status == "mapped"


def test_save_mapping_preserves_other_entries() -> None:
    doc = _make_doc(
        **{
            "US67066G1040": IsinMapping(ticker="NVDA", name="NVIDIA", status="mapped"),
            "CA65704Y1079": IsinMapping(ticker=None, name="Niobium", status="unmapped"),
        }
    )
    updated, _ = _save_mapping("CA65704Y1079", "NAN.V", doc)
    assert "US67066G1040" in updated.entries
    assert updated.entries["US67066G1040"].ticker == "NVDA"


# ---------------------------------------------------------------------------
# _delete_mapping
# ---------------------------------------------------------------------------

def test_delete_mapping_removes_entry() -> None:
    isin = "IE00B8KQN827"
    doc = _make_doc(**{
        isin: IsinMapping(ticker=None, name="Eaton", status="unmapped"),
        "US67066G1040": IsinMapping(ticker="NVDA", name="NVIDIA", status="mapped"),
    })
    updated = _delete_mapping(isin, doc)
    assert isin not in updated.entries
    assert "US67066G1040" in updated.entries


def test_delete_mapping_noop_for_unknown_isin() -> None:
    doc = _make_doc(**{
        "US67066G1040": IsinMapping(ticker="NVDA", name="NVIDIA", status="mapped"),
    })
    updated = _delete_mapping("UNKNOWN", doc)
    assert len(updated.entries) == 1


# ---------------------------------------------------------------------------
# _init_state
# ---------------------------------------------------------------------------

def test_init_state_sets_all_defaults() -> None:
    state: dict = {}
    _init_state(state)
    assert state["mappings_editing_isin"] is None
    assert state["mappings_confirming_delete_isin"] is None
    assert state["mappings_feedback"] is None
    assert state["mappings_edit_ticker_value"] == ""


def test_init_state_is_idempotent() -> None:
    state: dict = {"mappings_editing_isin": "US12345"}
    _init_state(state)
    assert state["mappings_editing_isin"] == "US12345"


# ---------------------------------------------------------------------------
# Smoke: module imports cleanly and render is callable
# ---------------------------------------------------------------------------

def test_mappings_module_imports_cleanly() -> None:
    import app.ui.pages.mappings as m
    assert callable(m.render)


def test_mappings_page_render_function_exists() -> None:
    from app.ui.pages.mappings import render
    assert callable(render)
