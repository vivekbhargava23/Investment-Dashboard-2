"""Unit tests for app.adapters.scalable_csv.planner — row classification logic."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.adapters.scalable_csv.parser import ParsedCsvRow
from app.adapters.scalable_csv.planner import plan_import
from app.domain.csv_import import PlannedAction, RowStatus
from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money

# ─── fixtures ─────────────────────────────────────────────────────────────────

_SAP_ISIN = "DE0007164600"
_NVDA_ISIN = "US67066G1040"
_VWCE_ISIN = "IE00B3RBWM25"


def _row(
    *,
    reference: str = "REF001",
    status: str = "Executed",
    type_: str = "Buy",
    isin: str = _SAP_ISIN,
    description: str = "SAP SE",
    shares: Decimal | None = Decimal("10"),
    price: Decimal | None = Decimal("100"),
    amount: Decimal | None = Decimal("-1000"),
    row_number: int = 2,
    trade_date: date = date(2026, 3, 1),
    currency: str = "EUR",
) -> ParsedCsvRow:
    return ParsedCsvRow(
        row_number=row_number,
        date=trade_date,
        time="10:00:00",
        status=status,
        reference=reference,
        description=description,
        asset_type="Security",
        type=type_,
        isin=isin,
        shares=shares,
        price=price,
        amount=amount,
        fee=Decimal("0.99"),
        tax=Decimal("0"),
        currency=currency,
    )


def _eur_tx(
    ref: str = "REF001",
    ticker: str = "SAP.DE",
    *,
    trade_date: date = date(2026, 3, 1),
    shares: Decimal = Decimal("10"),
    price: Decimal = Decimal("100"),
    source: str = "scalable_csv",
    csv_reference: str | None = None,
) -> Transaction:
    return Transaction(
        id=ref,
        type=TransactionType.BUY,
        ticker=ticker,
        trade_date=trade_date,
        shares=shares,
        price_native=Money(amount=price, currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
        source=source,  # type: ignore[arg-type]
        csv_reference=csv_reference or ref,
    )


def _mapped_doc(*entries: tuple[str, str]) -> IsinMapDocument:
    """Build IsinMapDocument from (isin, ticker) pairs — all mapped."""
    return IsinMapDocument(
        entries={
            isin: IsinMapping(ticker=ticker, name=ticker, status="mapped")
            for isin, ticker in entries
        }
    )


_EUR_MAP = _mapped_doc((_SAP_ISIN, "SAP.DE"), (_VWCE_ISIN, "VWCE.DE"))
_USD_MAP = _mapped_doc((_NVDA_ISIN, "NVDA"))
_EMPTY_MAP = IsinMapDocument()


# ─── test 1: reference matches existing csv tx ────────────────────────────────

def test_already_imported_by_reference() -> None:
    rows = [_row()]
    existing = [_eur_tx("REF001")]
    plan = plan_import(rows, existing, _EUR_MAP)
    assert plan.rows[0].status == RowStatus.ALREADY_IMPORTED
    assert plan.rows[0].action == PlannedAction.NOOP


# ─── test 2: content-hash matches manual tx ───────────────────────────────────

def test_conflict_with_manual_tx() -> None:
    rows = [_row(reference="CSV_NEW_REF")]
    existing = [_eur_tx("MANUAL_UUID", source="manual", csv_reference=None)]
    plan = plan_import(rows, existing, _EUR_MAP)
    r = plan.rows[0]
    assert r.status == RowStatus.CONFLICT_WITH_MANUAL
    assert r.action == PlannedAction.REPLACE
    assert r.conflict_tx_id == "MANUAL_UUID"


# ─── test 3: ISIN not in map ──────────────────────────────────────────────────

def test_unmapped_isin() -> None:
    rows = [_row(isin="UNKNOWN000001")]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.UNMAPPED_ISIN


# ─── test 4: ticker is non-EUR ────────────────────────────────────────────────

def test_needs_currency_support_usd_ticker() -> None:
    rows = [_row(isin=_NVDA_ISIN, description="NVIDIA")]
    plan = plan_import(rows, [], _USD_MAP)
    assert plan.rows[0].status == RowStatus.NEEDS_CURRENCY_SUPPORT


# ─── test 5: out-of-scope row type ────────────────────────────────────────────

def test_distribution_is_out_of_scope() -> None:
    rows = [_row(type_="Distribution")]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.OUT_OF_SCOPE_V1


def test_interest_is_out_of_scope() -> None:
    rows = [_row(type_="Interest")]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.OUT_OF_SCOPE_V1


def test_deposit_is_out_of_scope() -> None:
    rows = [_row(type_="Deposit")]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.OUT_OF_SCOPE_V1


# ─── test 6: outgoing security transfer ──────────────────────────────────────

def test_outgoing_transfer_flagged() -> None:
    rows = [_row(type_="Security transfer", shares=Decimal("-17"))]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.OUTGOING_TRANSFER


# ─── test 7: cancelled/expired ────────────────────────────────────────────────

def test_cancelled_status() -> None:
    rows = [_row(status="Cancelled")]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.CANCELLED_OR_EXPIRED


def test_expired_status() -> None:
    rows = [_row(status="Expired")]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.CANCELLED_OR_EXPIRED


# ─── test 8: content-hash match with existing scalable tx (edge case) ─────────

def test_content_hash_match_existing_scalable_is_already_imported() -> None:
    """Scalable tx with no csv_reference matches by content → already_imported, not conflict."""
    rows = [_row(reference="NEW_REF")]
    # Simulate a migration-untagged scalable row (same content, different/no ref)
    existing = [
        Transaction(
            id="OLD_REF",
            type=TransactionType.BUY,
            ticker="SAP.DE",
            trade_date=date(2026, 3, 1),
            shares=Decimal("10"),
            price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
            fx_rate_eur=Decimal("1"),
            source="scalable_csv",
            csv_reference=None,
        )
    ]
    plan = plan_import(rows, existing, _EUR_MAP)
    assert plan.rows[0].status == RowStatus.ALREADY_IMPORTED


# ─── test 9: empty portfolio + valid rows ─────────────────────────────────────

def test_empty_portfolio_all_new() -> None:
    rows = [
        _row(reference="A"),
        _row(reference="B", isin=_VWCE_ISIN, description="VWCE"),
    ]
    plan = plan_import(rows, [], _EUR_MAP)
    statuses = [r.status for r in plan.rows]
    assert all(s == RowStatus.NEW for s in statuses)
    assert len(plan.ready_to_import()) == 2


# ─── test 10: import_plan aggregates ─────────────────────────────────────────

def test_import_plan_counts() -> None:
    rows = [
        # Row A: distinct content (different date) from row B — classified as new
        _row(reference="A", trade_date=date(2026, 4, 15)),
        _row(reference="B"),          # already imported (matches tx by reference)
        _row(reference="C", status="Cancelled"),  # cancelled
    ]
    existing = [_eur_tx("B")]
    plan = plan_import(rows, existing, _EUR_MAP)
    counts = plan.count_by_status()
    assert counts[RowStatus.NEW] == 1
    assert counts[RowStatus.ALREADY_IMPORTED] == 1
    assert counts[RowStatus.CANCELLED_OR_EXPIRED] == 1
    assert len(plan.ready_to_import()) == 1


# ─── test 11: legacy id-as-reference dedup ────────────────────────────────────

def test_legacy_id_as_reference_dedup() -> None:
    """Old importer stored csv reference as tx.id — still deduped."""
    rows = [_row(reference="SCALabc123")]
    existing = [
        Transaction(
            id="SCALabc123",
            type=TransactionType.BUY,
            ticker="SAP.DE",
            trade_date=date(2026, 3, 1),
            shares=Decimal("10"),
            price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
            fx_rate_eur=Decimal("1"),
            source="scalable_csv",
            csv_reference=None,  # migration didn't match it
        )
    ]
    plan = plan_import(rows, existing, _EUR_MAP)
    assert plan.rows[0].status == RowStatus.ALREADY_IMPORTED


# ─── test 12: incoming security transfer is NEW ───────────────────────────────

def test_incoming_transfer_is_new() -> None:
    rows = [_row(type_="Security transfer", shares=Decimal("17"), amount=Decimal("194"))]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.NEW


# ─── test 13: savings plan is NEW ─────────────────────────────────────────────

def test_savings_plan_is_new() -> None:
    rows = [_row(type_="Savings plan")]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.NEW


# ─── test 14: unmapped ISIN (status=unmapped in doc) ─────────────────────────

def test_isin_status_unmapped_in_doc() -> None:
    doc = IsinMapDocument(
        entries={_SAP_ISIN: IsinMapping(ticker="SAP.DE", name="SAP", status="unmapped")}
    )
    rows = [_row()]
    plan = plan_import(rows, [], doc)
    assert plan.rows[0].status == RowStatus.UNMAPPED_ISIN


# ─── test 15: proposed_ticker populated for new rows ─────────────────────────

def test_proposed_ticker_populated() -> None:
    rows = [_row()]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].proposed_ticker == "SAP.DE"
