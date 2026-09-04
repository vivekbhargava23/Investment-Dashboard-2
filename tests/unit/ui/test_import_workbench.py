"""Smoke + unit tests for app.ui.pages.import_workbench."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from app.domain.csv_import import (
    FeedState,
    ImportPlan,
    PlannedAction,
    PlannedRow,
    RowStatus,
)
from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import TransactionType
from app.domain.money import Currency, Money
from app.domain.tax.classification import InstrumentKind
from app.services.isin_autoresolve import AutoResolveResult
from app.ui.pages.import_workbench import (
    _append_import_log,
    _build_transaction,
    _count_blocked,
    _count_ready,
    _get_unique_unmapped_isins,
    _ignore_isin,
    _load_import_log,
    _md5,
    _ticker_cell,
    _write_backup,
)

# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_planned_row(
    *,
    reference: str = "REF001",
    status: RowStatus = RowStatus.NEW,
    action: PlannedAction = PlannedAction.INSERT,
    ticker: str | None = "SAP.DE",
    shares: Decimal | None = Decimal("10"),
    price: Decimal | None = Decimal("100"),
    csv_type: str = "Buy",
    conflict_tx_id: str | None = None,
    fx_rate_eur: Decimal | None = None,
    isin: str = "DE0007164600",
    feed_state: FeedState | None = "mapped",
) -> PlannedRow:
    return PlannedRow(
        row_number=2,
        trade_date=date(2026, 3, 1),
        csv_type=csv_type,
        isin=isin,
        reference=reference,
        description="SAP SE",
        shares=shares,
        price=price,
        amount=Decimal("-1000"),
        fee=Decimal("0.99"),
        tax=Decimal("0"),
        status=status,
        action=action,
        proposed_ticker=ticker,
        feed_state=feed_state,
        conflict_tx_id=conflict_tx_id,
        fx_rate_eur=fx_rate_eur,
    )


# ─── _build_transaction ───────────────────────────────────────────────────────

def test_build_transaction_buy() -> None:
    row = _make_planned_row()
    tx = _build_transaction(row)
    assert tx is not None
    assert tx.type == TransactionType.BUY
    assert tx.ticker == "SAP.DE"
    assert tx.shares == Decimal("10")
    assert tx.price_native == Money(amount=Decimal("100"), currency=Currency.EUR)
    assert tx.csv_reference == "REF001"
    assert tx.source == "scalable_csv"


def test_build_transaction_stamps_isin() -> None:
    row = _make_planned_row(isin="KYG0535Q1331")
    tx = _build_transaction(row)
    assert tx is not None and tx.isin == "KYG0535Q1331"


def test_build_transaction_sell_with_tax() -> None:
    row = PlannedRow(
        row_number=3,
        trade_date=date(2026, 4, 1),
        csv_type="Sell",
        isin="DE0007164600",
        reference="REF002",
        description="SAP SE",
        shares=Decimal("5"),
        price=Decimal("120"),
        amount=Decimal("600"),
        fee=None,
        tax=Decimal("15"),
        status=RowStatus.NEW,
        action=PlannedAction.INSERT,
        proposed_ticker="SAP.DE",
    )
    tx = _build_transaction(row)
    assert tx is not None
    assert tx.type == TransactionType.SELL
    assert tx.notes is not None
    assert "tax_withheld_eur" in tx.notes
    assert "15" in tx.notes
    assert tx.isin == row.isin


def test_build_transaction_no_ticker_returns_none() -> None:
    row = _make_planned_row(ticker=None)
    assert _build_transaction(row) is None


def test_build_transaction_no_shares_returns_none() -> None:
    row = _make_planned_row(shares=None)
    assert _build_transaction(row) is None


def test_build_transaction_savings_plan_is_buy() -> None:
    row = _make_planned_row(csv_type="Savings plan")
    tx = _build_transaction(row)
    assert tx is not None
    assert tx.type == TransactionType.BUY


# ─── _count_ready ─────────────────────────────────────────────────────────────

def test_count_ready_all_new() -> None:
    plan = ImportPlan(rows=(
        _make_planned_row(reference="A"),
        _make_planned_row(reference="B"),
    ))
    assert _count_ready(plan, {}, set()) == 2


def test_count_ready_excluded_new_row() -> None:
    plan = ImportPlan(rows=(
        _make_planned_row(reference="A"),
        _make_planned_row(reference="B"),
    ))
    assert _count_ready(plan, {}, {"A"}) == 1


def test_count_ready_conflict_replace() -> None:
    plan = ImportPlan(rows=(
        _make_planned_row(
            reference="C",
            status=RowStatus.CONFLICT_WITH_MANUAL,
            action=PlannedAction.REPLACE,
            conflict_tx_id="manual-1",
        ),
    ))
    assert _count_ready(plan, {"C": "replace"}, set()) == 1


def test_count_ready_conflict_keep() -> None:
    plan = ImportPlan(rows=(
        _make_planned_row(
            reference="C",
            status=RowStatus.CONFLICT_WITH_MANUAL,
            action=PlannedAction.REPLACE,
            conflict_tx_id="manual-1",
        ),
    ))
    assert _count_ready(plan, {"C": "keep"}, set()) == 0


def test_count_ready_already_imported_not_counted() -> None:
    plan = ImportPlan(rows=(
        _make_planned_row(
            reference="D",
            status=RowStatus.ALREADY_IMPORTED,
            action=PlannedAction.NOOP,
        ),
    ))
    assert _count_ready(plan, {}, set()) == 0


# ─── blocked rows and feed-less tickers (TICKET-SYNC-1B) ──────────────────────

def _skip_row(reference: str, status: RowStatus) -> PlannedRow:
    return _make_planned_row(reference=reference, status=status, action=PlannedAction.SKIP)


def test_count_blocked_counts_only_unimportable_rows() -> None:
    plan = ImportPlan(rows=(
        _make_planned_row(reference="A", status=RowStatus.NEW),
        _skip_row("B", RowStatus.INTERNAL_TRANSFER),
        _skip_row("C", RowStatus.VALIDATION_ERROR),
    ))
    assert _count_blocked(plan) == 2


def test_count_blocked_zero_for_feedless_rows() -> None:
    """A CSV of nothing but unmapped ISINs has nothing blocked — it all imports."""
    plan = ImportPlan(rows=(
        _make_planned_row(reference="A", status=RowStatus.NEW, feed_state="unmapped"),
        _make_planned_row(reference="B", status=RowStatus.NEW, feed_state="ignored"),
    ))
    assert _count_blocked(plan) == 0
    assert _count_ready(plan, {}, set()) == 2


def test_ticker_cell_marks_feedless_rows() -> None:
    unmapped = _make_planned_row(ticker="KYG0535Q1331", feed_state="unmapped")
    ignored = _make_planned_row(ticker="KYG0535Q1331", feed_state="ignored")
    mapped = _make_planned_row(ticker="SAP.DE", feed_state="mapped")
    assert _ticker_cell(unmapped) == "KYG0535Q1331 (no feed)"
    assert _ticker_cell(ignored) == "KYG0535Q1331 (no feed)"
    assert _ticker_cell(mapped) == "SAP.DE"


def test_unmapped_isins_panel_lists_only_unmapped_feed_state() -> None:
    plan = ImportPlan(rows=(
        _make_planned_row(reference="A", isin="KYG0535Q1331", feed_state="unmapped"),
        _make_planned_row(reference="B", isin="KYG0535Q1331", feed_state="unmapped"),
        _make_planned_row(reference="C", isin="IE00B3RBWM25", feed_state="ignored"),
        _make_planned_row(reference="D", isin="DE0007164600", feed_state="mapped"),
    ))
    assert [isin for isin, _ in _get_unique_unmapped_isins(plan)] == ["KYG0535Q1331"]


# ─── import log ───────────────────────────────────────────────────────────────

def test_load_import_log_nonexistent(tmp_path: Path) -> None:
    assert _load_import_log(tmp_path / "log.json") == []


def test_append_import_log(tmp_path: Path) -> None:
    log_path = tmp_path / "import_log.json"
    _append_import_log(log_path, {"filename": "test.csv", "applied_count": 3})
    _append_import_log(log_path, {"filename": "test2.csv", "applied_count": 1})
    entries = _load_import_log(log_path)
    assert len(entries) == 2
    assert entries[0]["filename"] == "test.csv"
    assert entries[1]["applied_count"] == 1


# ─── backup rolling window ────────────────────────────────────────────────────

def test_backup_rolling_window_keeps_ten(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text('{"version":2,"transactions":[]}')
    backups_dir = tmp_path / "backups"
    backups_dir.mkdir()

    # Create 11 backup files with distinct names directly to test rolling-window logic
    for i in range(11):
        bak = backups_dir / f"portfolio.2026-01-{i+1:02d}_00-00-00-000000.json.bak"
        bak.write_text("{}")

    # Simulate one more write_backup call: should delete the oldest, leaving 10
    _write_backup(portfolio, backups_dir)

    remaining = list(backups_dir.glob("portfolio.*.json.bak"))
    assert len(remaining) == 10


# ─── md5 ──────────────────────────────────────────────────────────────────────

def test_md5_deterministic() -> None:
    data = b"hello world"
    assert _md5(data) == _md5(data)
    assert _md5(data) != _md5(b"other")


# ─── _build_transaction: non-EUR ticker is always EUR-native ─────────────────

def test_build_transaction_usd_ticker_is_eur_native() -> None:
    """NVDA (USD ticker) row → EUR-native Transaction; fx_rate_eur is always 1."""
    row = PlannedRow(
        row_number=2,
        trade_date=date(2026, 3, 15),
        csv_type="Buy",
        isin="US67066G1040",
        reference="REF_NVDA",
        description="NVIDIA Corp",
        shares=Decimal("4"),
        price=Decimal("82.65"),
        amount=Decimal("-330.60"),
        fee=None,
        tax=Decimal("0"),
        status=RowStatus.NEW,
        action=PlannedAction.INSERT,
        proposed_ticker="NVDA",
        fx_rate_eur=None,
    )
    tx = _build_transaction(row)
    assert tx is not None
    assert tx.price_native.currency == Currency.EUR
    assert tx.price_native.amount == Decimal("82.65")
    assert tx.fx_rate_eur == Decimal("1")


# ─── _ignore_isin ─────────────────────────────────────────────────────────────

def test_ignore_isin_creates_entry_when_absent() -> None:
    doc = IsinMapDocument(entries={})
    updated = _ignore_isin("DE0007164600", "SAP SE", doc)
    entry = updated.entries["DE0007164600"]
    assert entry.status == "ignored"
    assert entry.ticker is None
    assert entry.name == "SAP SE"


def test_ignore_isin_falls_back_to_isin_when_no_description() -> None:
    doc = IsinMapDocument(entries={})
    updated = _ignore_isin("DE0007164600", "", doc)
    assert updated.entries["DE0007164600"].name == "DE0007164600"


def test_ignore_isin_preserves_existing_name_and_clears_mapping() -> None:
    doc = IsinMapDocument(
        entries={
            "DE0007164600": IsinMapping(
                ticker="SAP.DE",
                name="Existing Name",
                status="mapped",
                last_seen_in_csv=date(2026, 1, 2),
                instrument_kind=InstrumentKind.AKTIE,
            )
        }
    )
    updated = _ignore_isin("DE0007164600", "SAP SE", doc)
    entry = updated.entries["DE0007164600"]
    assert entry.status == "ignored"
    assert entry.ticker is None
    assert entry.instrument_kind is None
    assert entry.name == "Existing Name"
    assert entry.last_seen_in_csv == date(2026, 1, 2)


def test_ignore_isin_leaves_other_entries_untouched() -> None:
    other = IsinMapping(ticker="MSF.DE", name="Microsoft", status="mapped")
    doc = IsinMapDocument(entries={"US5949181045": other})
    updated = _ignore_isin("DE0007164600", "SAP SE", doc)
    assert updated.entries["US5949181045"] == other
    assert updated.version == doc.version


# ─── page import smoke ────────────────────────────────────────────────────────

def test_import_workbench_module_importable() -> None:
    import app.ui.pages.import_workbench as page
    assert callable(page.render)


def test_import_workbench_has_render_function() -> None:
    from app.ui.pages.import_workbench import render
    assert callable(render)


# ---------------------------------------------------------------------------
# Auto-resolve refuses a ticker another mapped ISIN already feeds off (ADR-014 rule 4)
# ---------------------------------------------------------------------------


class _FakeIsinRepo:
    def __init__(self, doc: IsinMapDocument) -> None:
        self.doc = doc
        self.saved: IsinMapDocument | None = None

    def load(self) -> IsinMapDocument:
        return self.doc

    def save(self, doc: IsinMapDocument) -> None:
        self.saved = doc
        self.doc = doc


class _FakeTxRepo:
    def __init__(self, txs: list[object] | None = None) -> None:
        self._txs = list(txs or [])

    def load_all(self) -> list[object]:
        return list(self._txs)

    def save_all(self, txs: object) -> None:
        self._txs = list(txs)  # type: ignore[arg-type]


def _autoresolve_env(monkeypatch, doc: IsinMapDocument, result: AutoResolveResult):
    import app.ui.pages.import_workbench as iw

    isin_repo = _FakeIsinRepo(doc)
    monkeypatch.setattr(iw, "get_isin_map_repo", lambda: isin_repo)
    monkeypatch.setattr(iw, "get_repository", _FakeTxRepo)
    monkeypatch.setattr(iw, "get_ticker_resolver", lambda: None)
    monkeypatch.setattr(iw, "get_company_provider", lambda: None)
    monkeypatch.setattr(iw, "autoresolve_isin", lambda *a, **k: result)
    return iw, isin_repo


def test_autoresolve_demotes_a_result_whose_ticker_is_already_taken(
    monkeypatch, tmp_path: Path
) -> None:
    doc = IsinMapDocument(
        entries={
            "US0378331005": IsinMapping(
                ticker="NVDA", name="Nvidia (old ISIN)", status="mapped",
                instrument_kind=InstrumentKind.AKTIE,
            )
        }
    )
    result = AutoResolveResult(
        isin="US67066G1040", ticker="NVDA", name="Nvidia",
        instrument_kind=InstrumentKind.AKTIE, confidence="high", reason="exact match",
    )
    iw, isin_repo = _autoresolve_env(monkeypatch, doc, result)

    results, saved = iw._run_autoresolve(
        [("US67066G1040", "NVIDIA CORP")], tmp_path / "log.jsonl"
    )

    assert saved == set()
    assert isin_repo.saved is None
    assert results["US67066G1040"].confidence == "low"
    assert "already the feed for US0378331005" in results["US67066G1040"].reason


def test_autoresolve_saves_a_free_ticker(monkeypatch, tmp_path: Path) -> None:
    result = AutoResolveResult(
        isin="US67066G1040", ticker="NVDA", name="Nvidia",
        instrument_kind=InstrumentKind.AKTIE, confidence="high", reason="exact match",
    )
    iw, isin_repo = _autoresolve_env(monkeypatch, IsinMapDocument(), result)

    _, saved = iw._run_autoresolve(
        [("US67066G1040", "NVIDIA CORP")], tmp_path / "log.jsonl"
    )

    assert saved == {"US67066G1040"}
    assert isin_repo.saved is not None
    assert isin_repo.saved.entries["US67066G1040"].ticker == "NVDA"
