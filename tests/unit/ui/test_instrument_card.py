"""Pure-helper tests for the instrument card (no Streamlit context needed)."""
from __future__ import annotations

from decimal import Decimal

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.tax.classification import InstrumentKind
from app.services.isin_admin import apply_kind
from app.ui.components.instrument_card import (
    card_headline,
    feed_state_sentence,
    save_feed_disabled,
)

_ISIN = "DE000HT41XN9"


def _mapping(**kwargs: object) -> IsinMapping:
    defaults: dict[str, object] = {
        "ticker": "AMD",
        "name": "Advanced Micro Devices",
        "status": "mapped",
        "instrument_kind": InstrumentKind.AKTIE,
    }
    defaults.update(kwargs)
    return IsinMapping(**defaults)  # type: ignore[arg-type]


# ─── the state sentence ───────────────────────────────────────────────────────

def test_a_mapped_feed_reads_as_ticker_and_kind() -> None:
    assert feed_state_sentence(_mapping()) == "AMD (Aktie)"


def test_a_mapped_feed_without_a_kind_reads_as_the_ticker_alone() -> None:
    assert feed_state_sentence(_mapping(instrument_kind=None)) == "AMD"


def test_an_ignored_instrument_says_what_it_is_valued_at() -> None:
    sentence = feed_state_sentence(
        _mapping(ticker=None, status="ignored", instrument_kind=InstrumentKind.SONSTIGE)
    )
    assert sentence == "none — valued at last trade price"
    assert "ignor" not in sentence.lower()


def test_an_unmapped_instrument_reads_not_set() -> None:
    assert feed_state_sentence(_mapping(ticker=None, status="unmapped")) == "not set"


def test_an_instrument_the_map_has_never_seen_reads_not_set() -> None:
    assert feed_state_sentence(None) == "not set"


# ─── the headline ─────────────────────────────────────────────────────────────

def test_headline_names_the_open_share_count() -> None:
    assert card_headline("Apple turbo", _ISIN, Decimal("26")) == (
        f"**Apple turbo** · {_ISIN} · 26 shares open"
    )


def test_headline_says_closed_when_nothing_is_held() -> None:
    assert card_headline("Apple turbo", _ISIN, Decimal("0")).endswith("· closed")


def test_headline_falls_back_to_the_isin_when_there_is_no_name() -> None:
    assert card_headline("", _ISIN, Decimal("0")).startswith(f"**{_ISIN}**")


# ─── the three controls are independent ───────────────────────────────────────

def test_only_the_feed_save_is_gated_on_a_ticker_match() -> None:
    assert save_feed_disabled(None) is True


def test_a_tax_kind_can_be_set_with_no_feed_at_all() -> None:
    """The defect this card exists to fix: no feed used to mean no tax kind."""
    doc = IsinMapDocument(
        entries={_ISIN: _mapping(ticker=None, status="unmapped", instrument_kind=None)}
    )

    updated = apply_kind(doc, _ISIN, InstrumentKind.SONSTIGE)

    entry = updated.entries[_ISIN]
    assert entry.instrument_kind == InstrumentKind.SONSTIGE
    assert entry.ticker is None
    assert entry.status == "unmapped"
