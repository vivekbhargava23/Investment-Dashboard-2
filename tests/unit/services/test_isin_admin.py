"""Unit tests for app.services.isin_admin — the map edits that are not a feed change.

These moved off the ISIN Mappings page in TICKET-SYNC-7: they were page helpers,
but the sync service needs them too, and a page is not a place to keep a rule.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.tax.classification import InstrumentKind
from app.services.isin_admin import (
    apply_ignore,
    apply_kind,
    apply_restore,
    apply_unmap,
    delete_mapping,
    open_shares_for_isin,
    validate_ticker,
)
from tests.fakes.repository import FakeTransactionRepository

_ISIN = "US0378331005"
_OTHER = "DE0007164600"


def _doc(**overrides: object) -> IsinMapDocument:
    entry: dict[str, object] = {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "status": "mapped",
        "last_seen_in_csv": date(2026, 3, 1),
        "instrument_kind": InstrumentKind.AKTIE,
    }
    entry.update(overrides)
    return IsinMapDocument(
        entries={
            _ISIN: IsinMapping(**entry),  # type: ignore[arg-type]
            _OTHER: IsinMapping(ticker="SAP.DE", name="SAP SE", status="mapped"),
        }
    )


# ─── ignore / restore ─────────────────────────────────────────────────────────

def test_ignore_drops_the_feed_and_keeps_the_tax_kind() -> None:
    entry = apply_ignore(_doc(), _ISIN, "Apple Inc.").entries[_ISIN]

    assert entry.status == "ignored"
    assert entry.ticker is None
    assert entry.instrument_kind == InstrumentKind.AKTIE
    assert entry.last_seen_in_csv == date(2026, 3, 1)


def test_ignore_creates_an_entry_for_an_isin_the_map_has_never_seen() -> None:
    entry = apply_ignore(IsinMapDocument(), "XX0000000000", "Mystery ETP").entries[
        "XX0000000000"
    ]

    assert entry.status == "ignored"
    assert entry.name == "Mystery ETP"


def test_ignore_leaves_every_other_entry_alone() -> None:
    doc = apply_ignore(_doc(), _ISIN, "Apple Inc.")

    assert doc.entries[_OTHER].status == "mapped"
    assert doc.entries[_OTHER].ticker == "SAP.DE"


def test_restore_puts_an_ignored_instrument_back_in_the_queue() -> None:
    ignored = apply_ignore(_doc(), _ISIN, "Apple Inc.")

    entry = apply_restore(ignored, _ISIN).entries[_ISIN]

    assert entry.status == "unmapped"
    assert entry.ticker is None
    # The kind survives: it was never a fact about the feed.
    assert entry.instrument_kind == InstrumentKind.AKTIE


def test_restore_of_an_unknown_isin_changes_nothing() -> None:
    doc = _doc()
    assert apply_restore(doc, "XX0000000000") == doc


# ─── tax kind ─────────────────────────────────────────────────────────────────

def test_kind_change_touches_nothing_but_the_kind() -> None:
    entry = apply_kind(_doc(), _ISIN, InstrumentKind.SONSTIGE).entries[_ISIN]

    assert entry.instrument_kind == InstrumentKind.SONSTIGE
    assert entry.ticker == "AAPL"
    assert entry.status == "mapped"
    assert entry.last_seen_in_csv == date(2026, 3, 1)


def test_kind_can_be_set_on_an_ignored_instrument() -> None:
    ignored = apply_ignore(_doc(), _ISIN, "Apple Inc.")

    entry = apply_kind(ignored, _ISIN, InstrumentKind.SONSTIGE).entries[_ISIN]

    assert entry.status == "ignored"
    assert entry.instrument_kind == InstrumentKind.SONSTIGE


# ─── unmap / delete ───────────────────────────────────────────────────────────

def test_unmap_clears_the_feed_and_the_kind_but_keeps_the_name() -> None:
    entry = apply_unmap(_doc(), _ISIN).entries[_ISIN]

    assert entry.status == "unmapped"
    assert entry.ticker is None
    assert entry.instrument_kind is None
    assert entry.name == "Apple Inc."
    assert entry.last_seen_in_csv == date(2026, 3, 1)


def test_delete_removes_only_the_named_entry() -> None:
    doc = delete_mapping(_doc(), _ISIN)

    assert _ISIN not in doc.entries
    assert _OTHER in doc.entries


# ─── ticker validation ────────────────────────────────────────────────────────

@pytest.mark.parametrize("ticker", ["NVDA", "VUAA.DE", "5631.T", "BRK-B"])
def test_valid_tickers_pass(ticker: str) -> None:
    assert validate_ticker(ticker) is None


@pytest.mark.parametrize("ticker", ["", "   ", "nvda", "NV DA", ".DE", "A" * 31])
def test_invalid_tickers_are_rejected(ticker: str) -> None:
    assert validate_ticker(ticker) is not None


# ─── open shares ──────────────────────────────────────────────────────────────

def _tx(
    id: str, type: TransactionType, shares: str, isin: str | None = _ISIN
) -> Transaction:
    return Transaction(
        id=id,
        type=type,
        ticker="AAPL",
        trade_date=date(2026, 1, 1),
        shares=Decimal(shares),
        price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
        isin=isin,
        source="scalable_csv",
    )


def test_open_shares_nets_buys_against_sells_for_one_isin() -> None:
    repo = FakeTransactionRepository(
        [
            _tx("a", TransactionType.BUY, "26"),
            _tx("b", TransactionType.SELL, "10"),
            _tx("c", TransactionType.BUY, "5", isin=_OTHER),
        ]
    )

    assert open_shares_for_isin(repo, _ISIN) == Decimal("16")
    assert open_shares_for_isin(repo, _OTHER) == Decimal("5")


def test_open_shares_is_zero_for_an_isin_the_book_never_saw() -> None:
    assert open_shares_for_isin(FakeTransactionRepository([]), _ISIN) == Decimal("0")
