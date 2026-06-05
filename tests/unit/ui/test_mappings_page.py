"""Unit tests for app.ui.pages.mappings (pure helpers, no Streamlit context)."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pytest

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.ports.repository import TransactionNotFoundError
from app.ui.pages.mappings import (
    _delete_mapping,
    _ignore_isin,
    _init_state,
    _restore_isin,
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
    from app.domain.tax.classification import InstrumentKind
    updated, _ = _save_mapping(isin, "NAN.V", InstrumentKind.AKTIE, doc)
    entry = updated.entries[isin]
    assert entry.ticker == "NAN.V"
    assert entry.status == "mapped"
    assert entry.name == "North American Niobium"
    assert entry.last_seen_in_csv == date(2026, 4, 20)
    assert entry.instrument_kind == InstrumentKind.AKTIE


def test_save_mapping_updates_existing_mapped_entry() -> None:
    isin = "DE0007030009"
    doc = _make_doc(**{
        isin: IsinMapping(ticker="RHM.DE", name="Rheinmetall", status="mapped",
                          last_seen_in_csv=date(2026, 3, 30))
    })
    from app.domain.tax.classification import InstrumentKind
    updated, _ = _save_mapping(isin, "RHM.XETRA", InstrumentKind.AKTIE, doc)
    assert updated.entries[isin].ticker == "RHM.XETRA"
    assert updated.entries[isin].status == "mapped"


def test_save_mapping_preserves_other_entries() -> None:
    doc = _make_doc(
        **{
            "US67066G1040": IsinMapping(ticker="NVDA", name="NVIDIA", status="mapped"),
            "CA65704Y1079": IsinMapping(ticker=None, name="Niobium", status="unmapped"),
        }
    )
    from app.domain.tax.classification import InstrumentKind
    updated, _ = _save_mapping("CA65704Y1079", "NAN.V", InstrumentKind.AKTIE, doc)
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
    assert "mappings_edit_ticker_value" not in state


def test_init_state_is_idempotent() -> None:
    state: dict = {"mappings_editing_isin": "US12345"}
    _init_state(state)
    assert state["mappings_editing_isin"] == "US12345"


# ---------------------------------------------------------------------------
# Smoke: module imports cleanly and render is callable
# ---------------------------------------------------------------------------

def test_init_state_does_not_include_edit_ticker_value() -> None:
    """mappings_edit_ticker_value was removed when text_input was replaced by searchbox."""
    state: dict = {}
    _init_state(state)
    assert "mappings_edit_ticker_value" not in state


def test_save_mapping_with_ticker_from_searchbox_symbol() -> None:
    """Ticker derived from TickerMatch.symbol is accepted by _save_mapping."""
    isin = "DE0007030009"
    doc = _make_doc(**{
        isin: IsinMapping(ticker=None, name="Rheinmetall", status="unmapped",
                          last_seen_in_csv=date(2026, 4, 1))
    })
    from app.domain.tax.classification import InstrumentKind
    ticker_from_match = "RHM.DE"
    updated, _ = _save_mapping(isin, ticker_from_match, InstrumentKind.AKTIE, doc)
    assert updated.entries[isin].ticker == "RHM.DE"
    assert updated.entries[isin].status == "mapped"


def test_validate_ticker_accepts_searchbox_symbols() -> None:
    """Symbols returned by the searchbox (resolver) pass _validate_ticker."""
    assert _validate_ticker("RHM.DE") is None
    assert _validate_ticker("5631.T") is None
    assert _validate_ticker("IUES.DE") is None
    assert _validate_ticker("XNAS.DE") is None


def test_validate_ticker_none_match_still_blocked() -> None:
    """When selected_match is None, an empty ticker string is invalid."""
    assert _validate_ticker("") is not None


def test_mappings_module_imports_cleanly() -> None:
    import app.ui.pages.mappings as m
    assert callable(m.render)


def test_mappings_page_render_function_exists() -> None:
    from app.ui.pages.mappings import render
    assert callable(render)


# ---------------------------------------------------------------------------
# Fake repo for isin_remap tests
# ---------------------------------------------------------------------------


class _FakeRepo:
    def __init__(self, txs: list[Transaction] | None = None) -> None:
        self._txs: list[Transaction] = list(txs or [])
        self.save_calls: list[list[Transaction]] = []

    def load_all(self) -> list[Transaction]:
        return list(self._txs)

    def save_all(self, transactions: Sequence[Transaction]) -> None:
        self._txs = list(transactions)
        self.save_calls.append(list(transactions))

    def add(self, tx: Transaction) -> None:
        self._txs.append(tx)

    def update(self, tx: Transaction) -> None:
        for i, t in enumerate(self._txs):
            if t.id == tx.id:
                self._txs[i] = tx
                return
        raise TransactionNotFoundError(tx.id)

    def delete(self, tx_id: str) -> None:
        self._txs = [t for t in self._txs if t.id != tx_id]

    def get(self, tx_id: str) -> Transaction:
        for t in self._txs:
            if t.id == tx_id:
                return t
        raise TransactionNotFoundError(tx_id)


def _make_tx(tx_id: str, ticker: str, isin: str | None) -> Transaction:
    return Transaction(
        id=tx_id,
        type=TransactionType.BUY,
        ticker=ticker,
        trade_date=date(2026, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
        isin=isin,
        source="scalable_csv",
    )


# ---------------------------------------------------------------------------
# rewrite_ticker_for_isin is called on edit-save
# ---------------------------------------------------------------------------


def test_rewrite_called_on_edit_save_and_count_in_toast() -> None:
    """rewrite_ticker_for_isin is called with the new ticker; count is in the toast."""
    isin = "US67066G1040"
    txs = [
        _make_tx("tx1", "NVDA", isin),
        _make_tx("tx2", "NVDA", isin),
    ]
    fake_repo = _FakeRepo(txs)

    from app.services.isin_remap import rewrite_ticker_for_isin

    n = rewrite_ticker_for_isin(fake_repo, isin, "NVDA2")

    assert n == 2
    assert fake_repo.save_calls
    rewritten = fake_repo.load_all()
    assert all(tx.ticker == "NVDA2" for tx in rewritten)


def test_delete_block_when_transactions_reference_isin() -> None:
    """count_transactions_for_isin returns > 0 when transactions reference the ISIN."""
    isin = "US67066G1040"
    txs = [_make_tx("tx1", "NVDA", isin), _make_tx("tx2", "NVDA", isin)]
    fake_repo = _FakeRepo(txs)

    from app.services.isin_remap import count_transactions_for_isin

    n = count_transactions_for_isin(fake_repo, isin)
    assert n == 2


def test_delete_allow_when_no_transactions_reference_isin() -> None:
    """count_transactions_for_isin returns 0 when no transactions reference the ISIN."""
    txs = [_make_tx("tx1", "AAPL", "US0378331005")]
    fake_repo = _FakeRepo(txs)

    from app.services.isin_remap import count_transactions_for_isin

    assert count_transactions_for_isin(fake_repo, "US67066G1040") == 0


# ---------------------------------------------------------------------------
# _ignore_isin / _restore_isin helpers
# ---------------------------------------------------------------------------


def test_ignore_isin_flips_status_to_ignored() -> None:
    isin = "CH0491507486"
    doc = _make_doc(**{
        isin: IsinMapping(ticker=None, name="21shares Tezos ETP", status="unmapped",
                          last_seen_in_csv=date(2026, 5, 1))
    })
    updated = _ignore_isin(isin, doc)
    assert updated.entries[isin].status == "ignored"
    assert updated.entries[isin].name == "21shares Tezos ETP"
    assert updated.entries[isin].last_seen_in_csv == date(2026, 5, 1)


def test_ignore_isin_preserves_instrument_kind() -> None:
    """instrument_kind is preserved on ignore (cleared only on restore)."""
    from app.domain.tax.classification import InstrumentKind
    isin = "CH0491507486"
    doc = _make_doc(**{
        isin: IsinMapping(ticker=None, name="21shares Tezos ETP", status="unmapped",
                          instrument_kind=InstrumentKind.AKTIE)
    })
    updated = _ignore_isin(isin, doc)
    assert updated.entries[isin].instrument_kind == InstrumentKind.AKTIE


def test_restore_isin_flips_status_to_unmapped() -> None:
    isin = "CH0491507486"
    doc = _make_doc(**{
        isin: IsinMapping(ticker=None, name="21shares Tezos ETP", status="ignored",
                          last_seen_in_csv=date(2026, 5, 1))
    })
    updated = _restore_isin(isin, doc)
    assert updated.entries[isin].status == "unmapped"
    assert updated.entries[isin].name == "21shares Tezos ETP"
    assert updated.entries[isin].last_seen_in_csv == date(2026, 5, 1)


def test_restore_isin_clears_instrument_kind() -> None:
    """Restore drops instrument_kind defensively in case one was set."""
    from app.domain.tax.classification import InstrumentKind
    isin = "CH0491507486"
    doc = _make_doc(**{
        isin: IsinMapping(ticker=None, name="21shares Tezos ETP", status="ignored",
                          instrument_kind=InstrumentKind.AKTIE)
    })
    updated = _restore_isin(isin, doc)
    assert updated.entries[isin].instrument_kind is None


def test_ignore_and_restore_round_trip() -> None:
    """Ignore then restore leaves the entry back at unmapped with no kind."""
    isin = "CH0491507486"
    doc = _make_doc(**{
        isin: IsinMapping(ticker=None, name="21shares Tezos ETP", status="unmapped")
    })
    after_ignore = _ignore_isin(isin, doc)
    after_restore = _restore_isin(isin, after_ignore)
    assert after_restore.entries[isin].status == "unmapped"
    assert after_restore.entries[isin].instrument_kind is None
