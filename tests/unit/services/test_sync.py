"""Unit tests for the sync service (one session: analyse, apply, decide, undo)."""
from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.adapters.scalable_csv.planner import plan_import
from app.domain.csv_import import ImportPlan, RowStatus
from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.tax.classification import InstrumentKind
from app.ports.ticker_resolver import TickerMatch
from app.services.isin_admin import apply_ignore
from app.services.sync import (
    UndoNotPossible,
    analyse,
    apply_safe,
    build_transaction,
    change_feed_in_session,
    ignore_in_session,
    repair_in_session,
    resolve_conflict,
    set_kind_in_session,
    start_session,
    undo_last,
)
from tests.fakes.repository import FakeTransactionRepository
from tests.fakes.sync_store import FakeSyncStore

HEADER = (
    "date;time;status;reference;description;assetType;type;isin;"
    "shares;price;amount;fee;tax;currency\n"
)
ISIN = "DE0007164600"


# ─── doubles ──────────────────────────────────────────────────────────────────

class LinkedTxRepo(FakeTransactionRepository):
    """A transaction repo whose writes land in the fake store's portfolio bytes."""

    def __init__(self, store: FakeSyncStore, txs: Sequence[Transaction] = ()) -> None:
        super().__init__(txs)
        self._store = store
        self._flush()

    def save_all(self, transactions: Sequence[Transaction]) -> None:
        super().save_all(transactions)
        self._flush()

    def _flush(self) -> None:
        self._store.portfolio_bytes = json.dumps(
            [tx.model_dump(mode="json") for tx in self.load_all()], sort_keys=True
        ).encode()


class LinkedIsinRepo:
    """An ISIN-map repo whose writes land in the fake store's isin_map bytes."""

    def __init__(self, store: FakeSyncStore, doc: IsinMapDocument | None = None) -> None:
        self._store = store
        self._doc = doc or IsinMapDocument()
        self._flush()

    def load(self) -> IsinMapDocument:
        return self._doc

    def save(self, doc: IsinMapDocument) -> None:
        self._doc = doc
        self._flush()

    def _flush(self) -> None:
        self._store.isin_map_bytes = json.dumps(
            self._doc.model_dump(mode="json"), sort_keys=True
        ).encode()


class FakeResolver:
    def __init__(self, matches: list[TickerMatch] | None = None) -> None:
        self._matches = matches if matches is not None else []

    def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]:
        return list(self._matches)

    def lookup(self, symbol: str) -> TickerMatch | None:
        return None

    def clear_cache(self) -> None:
        pass


class FakeCompanyProvider:
    def __init__(self, quote_type: str | None = "EQUITY") -> None:
        self._quote_type = quote_type

    def get_company(self, ticker: str) -> Any:
        raise AssertionError("get_company must not be called")

    def refresh_section(self, ticker: str, section: Any) -> Any:
        raise AssertionError("refresh_section must not be called")

    def get_quote_type(self, ticker: str) -> str | None:
        return self._quote_type


def _rows(*lines: str) -> list[Any]:
    from app.adapters.scalable_csv.parser import parse_csv_bytes

    return list(parse_csv_bytes((HEADER + "".join(lines)).encode("utf-8")))


def _buy(reference: str, day: int = 5, shares: str = "10", month: int = 1) -> str:
    return (
        f"2026-{month:02d}-{day:02d};10:00:00;Executed;{reference};SAP SE;Security;Buy;"
        f"{ISIN};{shares};100,00;-{int(float(shares) * 100)},00;0,99;0,00;EUR\n"
    )


def _mapped_doc(ticker: str = "SAP.DE") -> IsinMapDocument:
    return IsinMapDocument(
        entries={
            ISIN: IsinMapping(
                ticker=ticker,
                name="SAP SE",
                status="mapped",
                instrument_kind=InstrumentKind.AKTIE,
            )
        }
    )


def _manual_tx(ticker: str = "SAP.DE", trade_date: date = date(2026, 1, 5)) -> Transaction:
    return Transaction(
        id="manual-1",
        type=TransactionType.BUY,
        ticker=ticker,
        trade_date=trade_date,
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
        isin=ISIN,
        source="manual",
    )


def _setup(
    doc: IsinMapDocument | None = None,
    txs: Sequence[Transaction] = (),
    matches: list[TickerMatch] | None = None,
    quote_type: str | None = "EQUITY",
) -> tuple[FakeSyncStore, LinkedTxRepo, LinkedIsinRepo, FakeResolver, FakeCompanyProvider]:
    store = FakeSyncStore()
    tx_repo = LinkedTxRepo(store, txs)
    isin_repo = LinkedIsinRepo(store, doc)
    return store, tx_repo, isin_repo, FakeResolver(matches), FakeCompanyProvider(quote_type)


def _analyse(rows: list[Any], session_id: str, store, tx_repo, isin_repo, resolver, company):
    return analyse(
        rows,
        session_id,
        tx_repo,
        isin_repo,
        resolver,
        company,
        store,
        plan_import,
    )


# ─── analyse + apply ──────────────────────────────────────────────────────────

def test_first_apply_inserts_and_second_apply_inserts_nothing() -> None:
    store, tx_repo, isin_repo, resolver, company = _setup(_mapped_doc())
    rows = _rows(_buy("ref-1"), _buy("ref-2", day=6))

    session = start_session("export.csv", "md5-1", store)
    analysis = _analyse(rows, session, store, tx_repo, isin_repo, resolver, company)
    applied = apply_safe(analysis, session, tx_repo, store)

    assert applied.inserted == 2
    assert applied.already_known == 0
    assert applied.snapshot_id == "snap-1"
    assert {tx.csv_reference for tx in tx_repo.load_all()} == {"ref-1", "ref-2"}

    second = _analyse(rows, session, store, tx_repo, isin_repo, resolver, company)
    assert second.safe_rows == []
    applied_again = apply_safe(second, session, tx_repo, store)
    assert applied_again.inserted == 0
    assert applied_again.already_known == 2
    assert len(tx_repo.load_all()) == 2


def test_apply_safe_never_touches_conflict_rows() -> None:
    store, tx_repo, isin_repo, resolver, company = _setup(
        _mapped_doc(), txs=[_manual_tx()]
    )
    rows = _rows(_buy("ref-1"))

    session = start_session("export.csv", "md5-1", store)
    analysis = _analyse(rows, session, store, tx_repo, isin_repo, resolver, company)

    assert [r.status for r in analysis.decision_rows] == [RowStatus.CONFLICT_WITH_MANUAL]
    assert analysis.safe_rows == []

    applied = apply_safe(analysis, session, tx_repo, store)

    assert applied.inserted == 0
    assert [tx.id for tx in tx_repo.load_all()] == ["manual-1"]


def test_resolve_conflict_replace_swaps_the_manual_row() -> None:
    store, tx_repo, isin_repo, resolver, company = _setup(
        _mapped_doc(), txs=[_manual_tx()]
    )
    session = start_session("export.csv", "md5-1", store)
    analysis = _analyse(
        _rows(_buy("ref-1")), session, store, tx_repo, isin_repo, resolver, company
    )

    resolve_conflict(analysis.decision_rows[0], "replace", session, tx_repo, store)

    ids = [tx.id for tx in tx_repo.load_all()]
    assert ids == ["ref-1"]
    assert store.log[-1]["event"] == "conflict_resolved"
    assert store.log[-1]["choice"] == "replace"


def test_resolve_conflict_keep_both_keeps_the_manual_row() -> None:
    store, tx_repo, isin_repo, resolver, company = _setup(
        _mapped_doc(), txs=[_manual_tx()]
    )
    session = start_session("export.csv", "md5-1", store)
    analysis = _analyse(
        _rows(_buy("ref-1")), session, store, tx_repo, isin_repo, resolver, company
    )

    resolve_conflict(analysis.decision_rows[0], "keep_both", session, tx_repo, store)

    assert sorted(tx.id for tx in tx_repo.load_all()) == ["manual-1", "ref-1"]


def test_unmapped_isin_still_imports_under_a_placeholder_ticker() -> None:
    store, tx_repo, isin_repo, resolver, company = _setup(matches=[])
    session = start_session("export.csv", "md5-1", store)

    analysis = _analyse(
        _rows(_buy("ref-1")), session, store, tx_repo, isin_repo, resolver, company
    )
    apply_safe(analysis, session, tx_repo, store)

    [tx] = tx_repo.load_all()
    assert tx.ticker == ISIN
    assert tx.isin == ISIN


def test_auto_resolve_maps_a_confident_match_and_imports_under_it() -> None:
    match = TickerMatch(
        symbol="SAP.DE",
        name="SAP SE",
        exchange="XETRA",
        currency=Currency.EUR,
        recent_price=None,
    )
    store, tx_repo, isin_repo, resolver, company = _setup(matches=[match])
    session = start_session("export.csv", "md5-1", store)

    analysis = _analyse(
        _rows(_buy("ref-1")), session, store, tx_repo, isin_repo, resolver, company
    )
    apply_safe(analysis, session, tx_repo, store)

    assert isin_repo.load().entries[ISIN].ticker == "SAP.DE"
    assert [tx.ticker for tx in tx_repo.load_all()] == ["SAP.DE"]
    assert "auto_resolve" in store.events()


def test_auto_resolve_refuses_a_ticker_another_isin_already_uses() -> None:
    other = IsinMapDocument(
        entries={
            "US0378331005": IsinMapping(
                ticker="SAP.DE",
                name="Other",
                status="mapped",
                instrument_kind=InstrumentKind.AKTIE,
            )
        }
    )
    match = TickerMatch(
        symbol="SAP.DE",
        name="SAP SE",
        exchange="XETRA",
        currency=Currency.EUR,
        recent_price=None,
    )
    store, tx_repo, isin_repo, resolver, company = _setup(doc=other, matches=[match])
    session = start_session("export.csv", "md5-1", store)

    analysis = _analyse(
        _rows(_buy("ref-1")), session, store, tx_repo, isin_repo, resolver, company
    )

    # It is recorded as seen, but never mapped onto the other ISIN's feed.
    assert isin_repo.load().entries[ISIN].status == "unmapped"
    assert isin_repo.load().entries[ISIN].ticker is None
    assert analysis.auto_resolved[ISIN].confidence == "low"


# ─── completeness ─────────────────────────────────────────────────────────────

def test_first_sync_on_an_empty_book_is_never_partial_and_logs_file_start() -> None:
    store, tx_repo, isin_repo, resolver, company = _setup(_mapped_doc())
    session = start_session("export.csv", "md5-1", store)

    analysis = _analyse(
        _rows(_buy("ref-1", month=6)), session, store, tx_repo, isin_repo, resolver, company
    )
    applied = apply_safe(analysis, session, tx_repo, store)

    assert analysis.completeness.partial is False
    assert applied.log_entry["file_start"] == "2026-06-05"


def test_a_partial_file_still_inserts_safe_rows() -> None:
    store, tx_repo, isin_repo, resolver, company = _setup(_mapped_doc())
    first = start_session("jan.csv", "md5-1", store)
    apply_safe(
        _analyse(_rows(_buy("ref-1")), first, store, tx_repo, isin_repo, resolver, company),
        first,
        tx_repo,
        store,
    )

    second = start_session("june.csv", "md5-2", store)
    analysis = _analyse(
        _rows(_buy("ref-2", month=6)), second, store, tx_repo, isin_repo, resolver, company
    )
    applied = apply_safe(analysis, second, tx_repo, store)

    assert analysis.completeness.partial is True
    assert applied.inserted == 1
    assert len(tx_repo.load_all()) == 2


def test_a_file_starting_after_a_logged_file_start_is_partial() -> None:
    store, tx_repo, isin_repo, resolver, company = _setup(_mapped_doc())
    store.append_log(
        {"event": "apply", "session_id": "old", "file_start": "2026-01-05"}
    )

    session = start_session("june.csv", "md5-2", store)
    analysis = _analyse(
        _rows(_buy("ref-2", month=6)), session, store, tx_repo, isin_repo, resolver, company
    )

    assert analysis.completeness.partial is True


# ─── undo ─────────────────────────────────────────────────────────────────────

def test_undo_restores_both_files_after_a_multi_step_session() -> None:
    match = TickerMatch(
        symbol="SAP.DE",
        name="SAP SE",
        exchange="XETRA",
        currency=Currency.EUR,
        recent_price=None,
    )
    store, tx_repo, isin_repo, resolver, company = _setup(
        matches=[match], txs=[_manual_tx(ticker="SAP.DE", trade_date=date(2026, 1, 6))]
    )
    portfolio_before = store.portfolio_bytes
    isin_map_before = store.isin_map_bytes

    session = start_session("export.csv", "md5-1", store)
    analysis = _analyse(
        _rows(_buy("ref-1"), _buy("ref-2", day=6)),
        session,
        store,
        tx_repo,
        isin_repo,
        resolver,
        company,
    )
    apply_safe(analysis, session, tx_repo, store)
    if analysis.decision_rows:
        resolve_conflict(analysis.decision_rows[0], "replace", session, tx_repo, store)
    change_feed_in_session(
        ISIN, "SAP.F", InstrumentKind.AKTIE, session, isin_repo, tx_repo, store
    )

    assert store.portfolio_bytes != portfolio_before
    assert store.isin_map_bytes != isin_map_before

    assert undo_last(store) == session

    assert store.portfolio_bytes == portfolio_before
    assert store.isin_map_bytes == isin_map_before
    assert store.events()[-1] == "undo"


def test_undo_removes_a_mapping_auto_resolve_persisted() -> None:
    match = TickerMatch(
        symbol="SAP.DE",
        name="SAP SE",
        exchange="XETRA",
        currency=Currency.EUR,
        recent_price=None,
    )
    store, tx_repo, isin_repo, resolver, company = _setup(matches=[match])
    isin_map_before = store.isin_map_bytes

    session = start_session("export.csv", "md5-1", store)
    _analyse(_rows(_buy("ref-1")), session, store, tx_repo, isin_repo, resolver, company)
    assert store.isin_map_bytes != isin_map_before

    undo_last(store)

    assert store.isin_map_bytes == isin_map_before


def test_undo_refuses_after_a_later_write_outside_the_session() -> None:
    store, tx_repo, isin_repo, resolver, company = _setup(_mapped_doc())
    session = start_session("export.csv", "md5-1", store)
    analysis = _analyse(
        _rows(_buy("ref-1")), session, store, tx_repo, isin_repo, resolver, company
    )
    apply_safe(analysis, session, tx_repo, store)

    # A Manage-page edit: writes portfolio.json without logging a sync entry.
    tx_repo.save_all([])

    with pytest.raises(UndoNotPossible):
        undo_last(store)


def test_undo_refuses_twice_in_a_row() -> None:
    store, tx_repo, isin_repo, resolver, company = _setup(_mapped_doc())
    session = start_session("export.csv", "md5-1", store)
    apply_safe(
        _analyse(_rows(_buy("ref-1")), session, store, tx_repo, isin_repo, resolver, company),
        session,
        tx_repo,
        store,
    )
    undo_last(store)

    with pytest.raises(UndoNotPossible):
        undo_last(store)


def test_undo_with_no_sync_at_all_refuses() -> None:
    with pytest.raises(UndoNotPossible):
        undo_last(FakeSyncStore())


# ─── logging ──────────────────────────────────────────────────────────────────

def test_every_entry_carries_session_and_md5s() -> None:
    store, tx_repo, isin_repo, resolver, company = _setup(_mapped_doc())
    session = start_session("export.csv", "md5-1", store)
    apply_safe(
        _analyse(_rows(_buy("ref-1")), session, store, tx_repo, isin_repo, resolver, company),
        session,
        tx_repo,
        store,
    )

    assert store.events() == ["session_start", "apply"]
    for entry in store.log:
        assert entry["session_id"] == session
        assert entry["timestamp"]
        assert entry["portfolio_md5_after"]
        assert entry["isin_map_md5_after"]


def test_a_session_with_zero_writes_still_has_its_snapshot() -> None:
    store, *_ = _setup(_mapped_doc())
    session = start_session("export.csv", "md5-1", store)

    assert store.snapshots
    assert store.log[0]["snapshot_id"] == "snap-1"
    assert store.log[0]["session_id"] == session


def test_change_feed_in_session_rewrites_and_logs() -> None:
    store, tx_repo, isin_repo, resolver, company = _setup(_mapped_doc())
    session = start_session("export.csv", "md5-1", store)
    apply_safe(
        _analyse(_rows(_buy("ref-1")), session, store, tx_repo, isin_repo, resolver, company),
        session,
        tx_repo,
        store,
    )

    rewritten = change_feed_in_session(
        ISIN, "SAP.F", InstrumentKind.AKTIE, session, isin_repo, tx_repo, store
    )

    assert rewritten == 1
    assert [tx.ticker for tx in tx_repo.load_all()] == ["SAP.F"]
    assert isin_repo.load().entries[ISIN].ticker == "SAP.F"
    assert store.events()[-1] == "feed_change"


def test_plan_is_an_import_plan() -> None:
    store, tx_repo, isin_repo, resolver, company = _setup(_mapped_doc())
    session = start_session("export.csv", "md5-1", store)
    analysis = _analyse(
        _rows(_buy("ref-1")), session, store, tx_repo, isin_repo, resolver, company
    )
    assert isinstance(analysis.plan, ImportPlan)


# ─── corporate actions (TICKET-SYNC-7) ────────────────────────────────────────

_KNOCKOUT_FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "scalable_knockout.csv"
)


def test_build_transaction_turns_a_knock_out_into_a_sell() -> None:
    from app.adapters.scalable_csv.parser import parse_csv

    plan = plan_import(parse_csv(_KNOCKOUT_FIXTURE), [], IsinMapDocument())
    leg = next(
        r for r in plan.rows
        if r.csv_type == "Corporate action" and r.asset_type == "Security"
    )

    tx = build_transaction(leg)

    assert tx is not None
    assert tx.type == TransactionType.SELL
    assert tx.shares == Decimal("26")
    assert tx.price_native == Money(amount=Decimal("0.001"), currency=Currency.EUR)
    assert tx.isin == "DE000HT41XN9"
    assert tx.source == "scalable_csv"
    assert tx.notes is not None
    assert tx.notes.startswith("corporate action: Apple Short")


def test_the_knock_out_pair_imports_exactly_one_transaction() -> None:
    from app.adapters.scalable_csv.parser import parse_csv

    plan = plan_import(parse_csv(_KNOCKOUT_FIXTURE), [], IsinMapDocument())
    txs = [tx for tx in (build_transaction(r) for r in plan.rows) if tx is not None]

    corporate = [t for t in txs if (t.notes or "").startswith("corporate action")]
    assert len(corporate) == 1
    # Both legs share one Scalable reference; only one becomes a transaction, so
    # the book never writes two rows under one identity.
    assert len({t.id for t in txs}) == len(txs)


# ─── every write while a file is open belongs to the session (TICKET-SYNC-7) ──

def _undo_still_possible(store: FakeSyncStore) -> bool:
    """The exact condition the Undo button and :func:`undo_last` both apply."""
    last = store.log[-1]
    return store.current_md5s() == (
        last["portfolio_md5_after"],
        last["isin_map_md5_after"],
    )


def _open_session_with_one_import() -> tuple[Any, Any, Any, str, bytes, bytes]:
    store, tx_repo, isin_repo, resolver, company = _setup(_mapped_doc())
    portfolio_before = store.portfolio_bytes
    isin_map_before = store.isin_map_bytes
    session = start_session("export.csv", "md5-1", store)
    apply_safe(
        _analyse(_rows(_buy("ref-1")), session, store, tx_repo, isin_repo, resolver, company),
        session,
        tx_repo,
        store,
    )
    return store, tx_repo, isin_repo, session, portfolio_before, isin_map_before


def test_ignore_in_session_keeps_undo_possible_and_undo_restores_both_files() -> None:
    store, tx_repo, isin_repo, session, portfolio_before, isin_map_before = (
        _open_session_with_one_import()
    )

    ignore_in_session(ISIN, "SAP SE", session, isin_repo, store)

    assert isin_repo.load().entries[ISIN].status == "ignored"
    assert store.events()[-1] == "ignore"
    assert _undo_still_possible(store)

    undo_last(store)

    assert store.portfolio_bytes == portfolio_before
    assert store.isin_map_bytes == isin_map_before


def test_set_kind_in_session_keeps_undo_possible() -> None:
    store, tx_repo, isin_repo, session, portfolio_before, isin_map_before = (
        _open_session_with_one_import()
    )

    set_kind_in_session(ISIN, InstrumentKind.SONSTIGE, session, isin_repo, store)

    entry = isin_repo.load().entries[ISIN]
    assert entry.instrument_kind == InstrumentKind.SONSTIGE
    assert entry.ticker == "SAP.DE"  # the feed is untouched
    assert store.events()[-1] == "kind_change"
    assert _undo_still_possible(store)

    undo_last(store)

    assert store.portfolio_bytes == portfolio_before
    assert store.isin_map_bytes == isin_map_before


def test_a_tax_kind_can_be_set_on_a_holding_with_no_feed() -> None:
    store, tx_repo, isin_repo, resolver, company = _setup()
    session = start_session("export.csv", "md5-1", store)

    set_kind_in_session(
        "DE000HT41XN9", InstrumentKind.SONSTIGE, session, isin_repo, store, name="Turbo"
    )

    entry = isin_repo.load().entries["DE000HT41XN9"]
    assert entry.instrument_kind == InstrumentKind.SONSTIGE
    assert entry.ticker is None
    assert entry.name == "Turbo"


def test_repair_in_session_keeps_undo_possible() -> None:
    store, tx_repo, isin_repo, session, portfolio_before, isin_map_before = (
        _open_session_with_one_import()
    )
    # Bypass the mapping write path, exactly the state Repair exists to fix.
    tx_repo.save_all(
        [tx.model_copy(update={"ticker": "SAP.F"}) for tx in tx_repo.load_all()]
    )

    changed = repair_in_session(session, isin_repo, tx_repo, store)

    assert changed == 1
    assert [tx.ticker for tx in tx_repo.load_all()] == ["SAP.DE"]
    assert store.events()[-1] == "repair"
    assert _undo_still_possible(store)

    undo_last(store)

    assert store.portfolio_bytes == portfolio_before
    assert store.isin_map_bytes == isin_map_before


def test_an_unlogged_write_still_blocks_undo() -> None:
    """The md5 guard is not weakened: a write outside the session still stops undo."""
    store, tx_repo, isin_repo, session, _, _ = _open_session_with_one_import()

    isin_repo.save(apply_ignore(isin_repo.load(), ISIN, "SAP SE"))

    assert not _undo_still_possible(store)
    with pytest.raises(UndoNotPossible):
        undo_last(store)
