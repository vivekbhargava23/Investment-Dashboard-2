"""Unit tests for the Sync page: its pure helpers, and the flow it drives."""
from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.adapters.scalable_csv.parser import parse_csv_bytes
from app.adapters.scalable_csv.planner import plan_import
from app.domain.csv_import import PlannedAction, PlannedRow, RowStatus
from app.domain.feed_check import FeedCheck
from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.reconcile import ReconcileRow, reconcile
from app.domain.sync_completeness import CompletenessResult
from app.domain.sync_tasks import build_tasks
from app.domain.tax.classification import InstrumentKind
from app.ports.ticker_resolver import TickerMatch
from app.services.sync import (
    analyse,
    apply_safe,
    change_feed_in_session,
    resolve_conflict,
    start_session,
)
from app.ui.pages.sync import (
    build_holdings_dataframe,
    cash_line,
    feed_check_cell,
    last_sync_line,
    market_values_line,
    sell_errors_by_isin,
    summary_card_lines,
    undo_enabled,
)
from tests.fakes.repository import FakeTransactionRepository
from tests.fakes.sync_store import FakeSyncStore

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "scalable_csv"
SAP = "DE0007164600"


# ─── doubles ──────────────────────────────────────────────────────────────────

class LinkedTxRepo(FakeTransactionRepository):
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
    def __init__(self, store: FakeSyncStore, doc: IsinMapDocument | None = None) -> None:
        self._store = store
        self._doc = doc or IsinMapDocument()

    def load(self) -> IsinMapDocument:
        return self._doc

    def save(self, doc: IsinMapDocument) -> None:
        self._doc = doc
        self._store.isin_map_bytes = json.dumps(
            doc.model_dump(mode="json"), sort_keys=True
        ).encode()


class FakeResolver:
    def __init__(self, matches: list[TickerMatch] | None = None) -> None:
        self._matches = matches or []

    def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]:
        return list(self._matches)

    def lookup(self, symbol: str) -> TickerMatch | None:
        return None

    def clear_cache(self) -> None:
        pass


class FakeCompanyProvider:
    def get_company(self, ticker: str) -> Any:
        raise AssertionError("not used")

    def refresh_section(self, ticker: str, section: Any) -> Any:
        raise AssertionError("not used")

    def get_quote_type(self, ticker: str) -> str | None:
        return "EQUITY"


def _env(doc: IsinMapDocument | None = None, txs: Sequence[Transaction] = (), matches=None):
    store = FakeSyncStore()
    return store, LinkedTxRepo(store, txs), LinkedIsinRepo(store, doc), FakeResolver(matches)


def _sync(store, tx_repo, isin_repo, resolver, data: bytes, name: str = "export.csv"):
    session_id = start_session(name, "md5", store)
    analysis = analyse(
        parse_csv_bytes(data),
        session_id,
        tx_repo,
        isin_repo,
        resolver,
        FakeCompanyProvider(),
        store,
        plan_import,
    )
    applied = apply_safe(analysis, session_id, tx_repo, store)
    return session_id, analysis, applied


def _tasks(analysis, tx_repo, checks=None):
    rows = reconcile(analysis.plan.rows, tx_repo.load_all())
    feed_states = {
        r.isin: r.feed_state for r in analysis.plan.rows if r.isin and r.feed_state
    }
    return build_tasks(
        rows,
        checks or {},
        sell_errors_by_isin(tx_repo.load_all()),
        analysis.decision_rows,
        analysis.completeness,
        feed_states,
    )


def _mapped_doc() -> IsinMapDocument:
    return IsinMapDocument(
        entries={
            SAP: IsinMapping(
                ticker="SAP.DE",
                name="SAP SE",
                status="mapped",
                instrument_kind=InstrumentKind.AKTIE,
            ),
            "DE0007030009": IsinMapping(
                ticker="RHM.DE",
                name="Rheinmetall AG",
                status="mapped",
                instrument_kind=InstrumentKind.AKTIE,
            ),
            "IE00B3RBWM25": IsinMapping(
                ticker="VWCE.DE",
                name="Vanguard FTSE All-World",
                status="mapped",
                instrument_kind=InstrumentKind.AKTIENFONDS,
            ),
        }
    )


def _sap_buy_csv(reference: str = "REF001") -> bytes:
    return (
        "date;time;status;reference;description;assetType;type;isin;"
        "shares;price;amount;fee;tax;currency\n"
        f"2026-03-01;10:00:00;Executed;{reference};SAP SE;Security;Buy;"
        f"{SAP};10;100,00;-1.000,00;0,99;0,00;EUR\n"
    ).encode()


# ─── page smoke ───────────────────────────────────────────────────────────────

def test_sync_page_has_render_function() -> None:
    from app.ui.pages import sync

    assert callable(sync.render)


def test_state_a_line_without_any_sync() -> None:
    assert last_sync_line([]) == "No sync yet — drop a Scalable export below to start."


def test_state_a_line_after_a_sync() -> None:
    log = [
        {
            "event": "apply",
            "timestamp": "2026-09-04T12:00:00",
            "inserted": 20,
            "partial": False,
        }
    ]
    assert last_sync_line(log) == "Last sync: 2026-09-04 · 20 trades · holdings matched Scalable"


def test_state_a_line_after_a_partial_sync() -> None:
    log = [
        {
            "event": "apply",
            "timestamp": "2026-09-04T12:00:00",
            "inserted": 3,
            "partial": True,
        }
    ]
    assert "partial file" in last_sync_line(log)


# ─── state B: a healthy file ──────────────────────────────────────────────────

def test_healthy_file_imports_every_trade_and_says_holdings_match() -> None:
    store, tx_repo, isin_repo, resolver = _env(_mapped_doc())
    _, analysis, applied = _sync(
        store, tx_repo, isin_repo, resolver, (FIXTURES / "healthy_three_trades.csv").read_bytes()
    )

    assert applied.inserted == 3
    assert len(tx_repo.load_all()) == 3

    rows = reconcile(analysis.plan.rows, tx_repo.load_all())
    lines = summary_card_lines(applied, analysis, rows, first_sync=False)
    assert lines[0] == "3 new trades imported · 0 already known"
    assert lines[1].startswith("Holdings match this Scalable export")


def test_first_sync_card_warns_about_coverage_instead() -> None:
    store, tx_repo, isin_repo, resolver = _env(_mapped_doc())
    _, analysis, applied = _sync(store, tx_repo, isin_repo, resolver, _sap_buy_csv())

    lines = summary_card_lines(applied, analysis, [], first_sync=True)
    assert lines[1] == "First sync — make sure the export covers all time"


def test_partial_file_card_skips_the_holdings_claim() -> None:
    partial = CompletenessResult(
        partial=True, reason="…", file_start=date(2026, 6, 1), book_start=date(2026, 1, 5)
    )
    store, tx_repo, isin_repo, resolver = _env(_mapped_doc())
    _, analysis, applied = _sync(store, tx_repo, isin_repo, resolver, _sap_buy_csv())
    analysis = type(analysis)(
        plan=analysis.plan,
        completeness=partial,
        safe_rows=analysis.safe_rows,
        decision_rows=analysis.decision_rows,
        auto_resolved=analysis.auto_resolved,
    )

    lines = summary_card_lines(applied, analysis, [], first_sync=False)
    assert lines[1] == "Holdings comparison skipped — this file looks partial"


# ─── state C: tasks ───────────────────────────────────────────────────────────

def test_one_unmapped_open_isin_yields_exactly_one_no_feed_task() -> None:
    store, tx_repo, isin_repo, resolver = _env(matches=[])
    _, analysis, _ = _sync(store, tx_repo, isin_repo, resolver, _sap_buy_csv())

    tasks = _tasks(analysis, tx_repo)

    assert [t.kind for t in tasks] == ["no_feed"]
    assert tasks[0].isin == SAP


def test_mapping_the_isin_removes_the_no_feed_task() -> None:
    store, tx_repo, isin_repo, resolver = _env(matches=[])
    session_id, analysis, _ = _sync(store, tx_repo, isin_repo, resolver, _sap_buy_csv())
    assert [t.kind for t in _tasks(analysis, tx_repo)] == ["no_feed"]

    change_feed_in_session(
        SAP, "SAP.DE", InstrumentKind.AKTIE, session_id, isin_repo, tx_repo, store
    )
    reanalysed = analyse(
        parse_csv_bytes(_sap_buy_csv()),
        session_id,
        tx_repo,
        isin_repo,
        resolver,
        FakeCompanyProvider(),
        store,
        plan_import,
    )

    assert _tasks(reanalysed, tx_repo) == []


def test_conflict_row_becomes_a_duplicate_task_and_imports_nothing() -> None:
    manual = Transaction(
        id="manual-1",
        type=TransactionType.BUY,
        ticker="SAP.DE",
        trade_date=date(2026, 3, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
        isin=SAP,
        source="manual",
    )
    store, tx_repo, isin_repo, resolver = _env(_mapped_doc(), txs=[manual])
    session_id, analysis, applied = _sync(
        store, tx_repo, isin_repo, resolver, _sap_buy_csv()
    )

    assert applied.inserted == 0
    assert [tx.id for tx in tx_repo.load_all()] == ["manual-1"]
    assert [t.kind for t in _tasks(analysis, tx_repo)] == ["possible_duplicate"]

    resolve_conflict(analysis.decision_rows[0], "replace", session_id, tx_repo, store)

    assert [tx.id for tx in tx_repo.load_all()] == ["REF001"]


# ─── cells and lines ──────────────────────────────────────────────────────────

def _check(status: str, **kwargs: Any) -> FeedCheck:
    defaults: dict[str, Any] = {
        "isin": SAP,
        "ticker": "SAP.DE",
        "status": status,
        "compared": 3,
        "median_deviation_pct": Decimal("1.23"),
        "avg_trade_price_eur": Decimal("20.44"),
        "avg_close_eur": Decimal("0.20"),
        "detail": "detail",
    }
    defaults.update(kwargs)
    return FeedCheck(**defaults)


def test_feed_check_cell_ok() -> None:
    assert feed_check_cell(_check("ok")) == "✓ within 1.2 %"


def test_feed_check_cell_suspicious() -> None:
    assert feed_check_cell(_check("suspicious")) == (
        "⚠ looks wrong · you €20.44 / feed €0.20"
    )


def test_feed_check_cell_no_feed() -> None:
    assert feed_check_cell(_check("no_feed")) == "⚠ no feed"


def test_feed_check_cell_unchecked_and_missing() -> None:
    assert feed_check_cell(_check("unchecked", ticker=None)) == "—"
    assert feed_check_cell(None) == "—"


def test_holdings_dataframe_columns_and_feed_cell() -> None:
    row = ReconcileRow(
        isin=SAP,
        name="SAP SE",
        shares_csv=Decimal("10"),
        shares_book=Decimal("10"),
        diff=Decimal("0"),
        matches=True,
        cause=None,
        last_trade_price_eur=Decimal("100"),
    )
    df = build_holdings_dataframe([row], {SAP: _check("ok")}, _mapped_doc())

    assert list(df.columns) == [
        "Name (Scalable)",
        "Shares Scalable",
        "Shares dashboard",
        "Feed",
        "Feed check",
        "Tax kind",
    ]
    assert df.iloc[0]["Feed"] == "SAP.DE"
    assert df.iloc[0]["Feed check"] == "✓ within 1.2 %"


def test_holdings_dataframe_marks_a_holding_with_no_mapping() -> None:
    row = ReconcileRow(
        isin="FR0004038263",
        name="Parrot SA",
        shares_csv=Decimal("50"),
        shares_book=Decimal("0"),
        diff=Decimal("50"),
        matches=False,
        cause="unknown — check Details",
        last_trade_price_eur=Decimal("8.68"),
    )
    df = build_holdings_dataframe([row], {}, _mapped_doc())

    assert df.iloc[0]["Feed"] == "—"
    assert df.iloc[0]["Tax kind"] == "⚠ unset"


def _cash_row(csv_type: str, amount: str) -> PlannedRow:
    return PlannedRow(
        row_number=2,
        trade_date=date(2026, 3, 1),
        csv_type=csv_type,
        isin="",
        reference="",
        description=csv_type,
        shares=None,
        price=None,
        amount=Decimal(amount),
        fee=None,
        tax=None,
        status=RowStatus.OUT_OF_SCOPE_V1,
        action=PlannedAction.SKIP,
    )


def test_cash_line_sums_by_kind() -> None:
    rows = [
        _cash_row("Distribution", "12.50"),
        _cash_row("Distribution", "7.50"),
        _cash_row("Interest", "1.25"),
        _cash_row("Taxes", "-3.00"),
    ]

    assert cash_line(rows) == (
        "Cash events in this file: €20.00 dividends · €1.25 interest · €3.00 taxes"
    )


def test_cash_line_is_absent_without_cash_events() -> None:
    assert cash_line([]) is None


def test_market_values_line() -> None:
    assert market_values_line(None) == (
        "Market values are estimates from yfinance as of not fetched yet."
    )
    assert market_values_line(datetime(2026, 9, 3, 19, 20)) == (
        "Market values are estimates from yfinance as of 03 Sep 2026 19:20."
    )


# ─── undo eligibility ─────────────────────────────────────────────────────────

def test_undo_enabled_when_the_files_still_match_the_last_entry() -> None:
    log = [{"event": "apply", "portfolio_md5_after": "a", "isin_map_md5_after": "b"}]
    assert undo_enabled(log, ("a", "b")) is True


def test_undo_disabled_after_a_later_write() -> None:
    log = [{"event": "apply", "portfolio_md5_after": "a", "isin_map_md5_after": "b"}]
    assert undo_enabled(log, ("changed", "b")) is False


def test_undo_disabled_with_no_log_and_after_an_undo() -> None:
    assert undo_enabled([], ("a", "b")) is False
    assert undo_enabled(
        [{"event": "undo", "portfolio_md5_after": "a", "isin_map_md5_after": "b"}],
        ("a", "b"),
    ) is False


# ─── FIFO breakage ────────────────────────────────────────────────────────────

def test_sell_errors_are_reported_per_isin() -> None:
    sell = Transaction(
        id="s1",
        type=TransactionType.SELL,
        ticker="SAP.DE",
        trade_date=date(2026, 3, 2),
        shares=Decimal("5"),
        price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
        isin=SAP,
        source="scalable_csv",
    )

    errors = sell_errors_by_isin([sell])

    assert SAP in errors
    assert "exceeds open position" in errors[SAP]


def test_a_healthy_book_has_no_sell_errors() -> None:
    buy = Transaction(
        id="b1",
        type=TransactionType.BUY,
        ticker="SAP.DE",
        trade_date=date(2026, 3, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
        isin=SAP,
        source="scalable_csv",
    )

    assert sell_errors_by_isin([buy]) == {}
