"""Unit tests for app.adapters.scalable_csv.planner — row classification logic."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from app.adapters.scalable_csv.parser import ParsedCsvRow, parse_csv
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

def test_unmapped_isin_imports_with_placeholder_ticker() -> None:
    """No mapping is not a reason to drop a trade (ADR-014 rule 7)."""
    rows = [_row(isin="UNKNOWN000001")]
    plan = plan_import(rows, [], _EUR_MAP)
    r = plan.rows[0]
    assert r.status == RowStatus.NEW
    assert r.action == PlannedAction.INSERT
    assert r.proposed_ticker == "UNKNOWN000001"
    assert r.feed_state == "unmapped"


def test_ignored_isin_imports_with_placeholder_ticker() -> None:
    """``ignored`` means "no feed wanted", not "no trade"."""
    doc = IsinMapDocument(
        entries={_SAP_ISIN: IsinMapping(ticker=None, name="SAP", status="ignored")}
    )
    plan = plan_import([_row()], [], doc)
    r = plan.rows[0]
    assert r.status == RowStatus.NEW
    assert r.proposed_ticker == _SAP_ISIN
    assert r.feed_state == "ignored"


def test_mapped_isin_uses_mapping_ticker() -> None:
    plan = plan_import([_row()], [], _EUR_MAP)
    r = plan.rows[0]
    assert r.proposed_ticker == "SAP.DE"
    assert r.feed_state == "mapped"


def test_missing_isin_is_validation_error() -> None:
    plan = plan_import([_row(isin="")], [], _EUR_MAP)
    r = plan.rows[0]
    assert r.status == RowStatus.VALIDATION_ERROR
    assert r.action == PlannedAction.SKIP
    assert r.error_message == "row has no ISIN"


def test_the_dead_feed_statuses_are_gone() -> None:
    """A missing or ignored feed has never blocked an import since SYNC-1B."""
    assert not hasattr(RowStatus, "UNMAPPED_ISIN")
    assert not hasattr(RowStatus, "IGNORED_ISIN")


def test_an_unmapped_or_ignored_feed_still_imports_the_trade() -> None:
    rows = [
        _row(reference="A", isin="UNKNOWN000001"),
        _row(reference="B"),
        _row(reference="C", isin=_VWCE_ISIN),
    ]
    doc = IsinMapDocument(
        entries={
            _SAP_ISIN: IsinMapping(ticker=None, name="SAP", status="ignored"),
            _VWCE_ISIN: IsinMapping(ticker=None, name="VWCE", status="unmapped"),
        }
    )

    plan = plan_import(rows, [], doc)

    assert [r.status for r in plan.rows] == [RowStatus.NEW] * 3


# ─── test 4: USD ticker is NEW (EUR-native, no FX needed) ────────────────────

def test_usd_ticker_is_new() -> None:
    """NVDA (USD ticker) is classified as NEW — EUR-native, no FX lookup required."""
    rows = [_row(isin=_NVDA_ISIN, description="NVIDIA")]
    plan = plan_import(rows, [], _USD_MAP)
    assert plan.rows[0].status == RowStatus.NEW
    assert plan.rows[0].proposed_ticker == "NVDA"
    assert plan.rows[0].fx_rate_eur is None


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


# ─── test 6: security transfer — both legs are INTERNAL_TRANSFER ──────────────

def test_outgoing_transfer_is_internal_transfer() -> None:
    rows = [_row(type_="Security transfer", shares=Decimal("-17"))]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.INTERNAL_TRANSFER
    assert plan.rows[0].action == PlannedAction.SKIP


def test_incoming_transfer_is_internal_transfer() -> None:
    rows = [_row(type_="Security transfer", shares=Decimal("17"), amount=Decimal("194"))]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.INTERNAL_TRANSFER
    assert plan.rows[0].action == PlannedAction.SKIP


def test_both_transfer_legs_classified_internal() -> None:
    """Both legs of a paired security transfer get INTERNAL_TRANSFER/SKIP."""
    rows = [
        _row(reference="OUT", type_="Security transfer",
             shares=Decimal("-17"), amount=Decimal("-19.4")),
        _row(reference="IN", type_="Security transfer",
             shares=Decimal("17"), amount=Decimal("19.4")),
    ]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.INTERNAL_TRANSFER
    assert plan.rows[1].status == RowStatus.INTERNAL_TRANSFER
    assert all(r.action == PlannedAction.SKIP for r in plan.rows)


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


# ─── test 12: savings plan is NEW ─────────────────────────────────────────────

def test_savings_plan_is_new() -> None:
    rows = [_row(type_="Savings plan")]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.NEW


# ─── test 13: unmapped ISIN (status=unmapped in doc) ─────────────────────────

def test_isin_status_unmapped_in_doc() -> None:
    """A stale ticker on an ``unmapped`` entry is not a feed — the ISIN is used."""
    doc = IsinMapDocument(
        entries={_SAP_ISIN: IsinMapping(ticker="SAP.DE", name="SAP", status="unmapped")}
    )
    rows = [_row()]
    plan = plan_import(rows, [], doc)
    r = plan.rows[0]
    assert r.status == RowStatus.NEW
    assert r.proposed_ticker == _SAP_ISIN
    assert r.feed_state == "unmapped"


# ─── test 14: proposed_ticker populated for new rows ─────────────────────────

def test_proposed_ticker_populated() -> None:
    rows = [_row()]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].proposed_ticker == "SAP.DE"


# ─── test 15: EUR ticker classified as NEW ────────────────────────────────────

def test_eur_ticker_classified_as_new() -> None:
    rows = [_row()]  # SAP.DE → EUR
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.NEW
    assert plan.rows[0].fx_rate_eur is None  # EUR rows don't need fx_rate_eur


# ─── test 16: JPY ticker is NEW (EUR-native, no FX) ──────────────────────────

_JP_ISIN = "JP3633400001"
_JP_MAP = _mapped_doc((_JP_ISIN, "5631.T"))


def test_jpy_ticker_is_new() -> None:
    """5631.T (JPY ticker) is classified as NEW — EUR-native, no FX lookup."""
    row = _row(isin=_JP_ISIN, description="Japan Steel Works")
    plan = plan_import([row], [], _JP_MAP)
    r = plan.rows[0]
    assert r.status == RowStatus.NEW
    assert r.proposed_ticker == "5631.T"
    assert r.fx_rate_eur is None


# ─── test 17: fx_rate_eur is None for all new rows ───────────────────────────

def test_eur_new_row_has_no_fx_rate_eur() -> None:
    rows = [_row()]
    plan = plan_import(rows, [], _EUR_MAP)
    r = plan.rows[0]
    assert r.status == RowStatus.NEW
    assert r.fx_rate_eur is None


# ─── validation guards (ported from the deleted run_import path) ──────────────

def test_amount_mismatch_is_validation_error() -> None:
    """abs(amount) ≠ abs(shares×price) beyond 0.01 EUR → VALIDATION_ERROR, never imported."""
    # 10 × 100 = 1000, but amount is -999 → diff 1.00 ≥ 0.01
    rows = [_row(amount=Decimal("-999"))]
    plan = plan_import(rows, [], _EUR_MAP)
    r = plan.rows[0]
    assert r.status == RowStatus.VALIDATION_ERROR
    assert r.action == PlannedAction.SKIP
    assert r.error_message is not None
    assert "Amount sanity check failed" in r.error_message
    assert plan.ready_to_import() == []


def test_amount_within_tolerance_is_new() -> None:
    """A sub-0.01 EUR difference is within tolerance and still classified NEW."""
    # 10 × 100 = 1000.00; amount -1000.009 → diff 0.009 < 0.01
    rows = [_row(amount=Decimal("-1000.009"))]
    plan = plan_import(rows, [], _EUR_MAP)
    assert plan.rows[0].status == RowStatus.NEW


def test_wrong_sign_is_validation_error() -> None:
    """A Buy with a positive amount (cash in) is a directional sign error → VALIDATION_ERROR."""
    rows = [_row(amount=Decimal("1000"))]
    plan = plan_import(rows, [], _EUR_MAP)
    r = plan.rows[0]
    assert r.status == RowStatus.VALIDATION_ERROR
    assert r.action == PlannedAction.SKIP
    assert r.error_message is not None
    assert "Directional sign error" in r.error_message
    assert plan.ready_to_import() == []


def test_sell_wrong_sign_is_validation_error() -> None:
    """A Sell with a negative amount (cash out) is a directional sign error."""
    # 10 × 100 = 1000; Sell expects positive amount, give -1000
    rows = [_row(type_="Sell", amount=Decimal("-1000"))]
    plan = plan_import(rows, [], _EUR_MAP)
    r = plan.rows[0]
    assert r.status == RowStatus.VALIDATION_ERROR
    assert r.error_message is not None
    assert "Directional sign error" in r.error_message


def test_non_eur_currency_is_validation_error() -> None:
    """A non-EUR row becomes VALIDATION_ERROR, never a silently-EUR transaction."""
    rows = [_row(isin=_NVDA_ISIN, description="NVIDIA", currency="USD")]
    plan = plan_import(rows, [], _USD_MAP)
    r = plan.rows[0]
    assert r.status == RowStatus.VALIDATION_ERROR
    assert r.action == PlannedAction.SKIP
    assert r.error_message is not None
    assert "Unexpected currency" in r.error_message
    assert plan.ready_to_import() == []


def test_validation_error_does_not_fire_for_already_imported() -> None:
    """A malformed row that matches an existing tx by reference stays ALREADY_IMPORTED."""
    rows = [_row(amount=Decimal("-999"))]  # would be VALIDATION_ERROR if NEW
    existing = [_eur_tx("REF001")]
    plan = plan_import(rows, existing, _EUR_MAP)
    assert plan.rows[0].status == RowStatus.ALREADY_IMPORTED


def test_validation_error_fires_for_unmapped_row() -> None:
    """Unmapped rows import like any other, so the guards apply to them too."""
    rows = [_row(isin="UNKNOWN000001", amount=Decimal("-999"))]
    plan = plan_import(rows, [], _EUR_MAP)
    r = plan.rows[0]
    assert r.status == RowStatus.VALIDATION_ERROR
    assert r.proposed_ticker == "UNKNOWN000001"


# ─── corporate actions (TICKET-SYNC-7) ────────────────────────────────────────

_KNOCKOUT_ISIN = "DE000HT41XN9"
_KNOCKOUT_FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "scalable_knockout.csv"
)


def _knockout_rows() -> list[ParsedCsvRow]:
    """The real Scalable rows for the HSBC Apple turbo knock-out, verbatim."""
    return parse_csv(_KNOCKOUT_FIXTURE)


def test_real_knockout_pair_parses_despite_the_shared_reference() -> None:
    """Both legs carry `WWUM 00477772743`; only one of them is importable."""
    rows = _knockout_rows()
    shared = [r for r in rows if r.reference == "WWUM 00477772743"]
    assert len(shared) == 2
    assert {r.asset_type for r in shared} == {"Cash", "Security"}


def test_corporate_action_security_leg_imports_as_a_sell() -> None:
    plan = plan_import(_knockout_rows(), [], IsinMapDocument())
    by_row = {r.row_number: r for r in plan.rows}

    security_leg = next(
        r for r in plan.rows if r.csv_type == "Corporate action" and r.asset_type == "Security"
    )
    assert security_leg.status == RowStatus.NEW
    assert security_leg.action == PlannedAction.INSERT
    assert security_leg.proposed_type == "sell"
    # Stored positive: the direction lives in proposed_type, not in the sign.
    assert security_leg.shares == Decimal("26")
    assert security_leg.price == Decimal("0.001")
    assert security_leg.proposed_ticker == _KNOCKOUT_ISIN

    cash_leg = next(
        r for r in plan.rows if r.csv_type == "Corporate action" and r.asset_type == "Cash"
    )
    assert cash_leg.status == RowStatus.OUT_OF_SCOPE_V1
    assert cash_leg.action == PlannedAction.SKIP

    # The original buy is still a plain new buy, the cancelled sell still cancelled.
    buy = next(r for r in plan.rows if r.csv_type == "Buy")
    assert buy.status == RowStatus.NEW
    assert buy.proposed_type == "buy"
    assert by_row[buy.row_number].shares == Decimal("26")
    cancelled = next(r for r in plan.rows if r.status == RowStatus.CANCELLED_OR_EXPIRED)
    assert cancelled.csv_type == "Sell"

    new_rows = [r for r in plan.rows if r.status == RowStatus.NEW]
    assert len(new_rows) == 2


def test_positive_corporate_action_security_leg_imports_as_a_buy() -> None:
    row = _row(
        type_="Corporate action",
        reference="CA-POS",
        shares=Decimal("5"),
        price=Decimal("0.001"),
        amount=Decimal("0.005"),
    )
    plan = plan_import([row], [], IsinMapDocument())
    assert plan.rows[0].status == RowStatus.NEW
    assert plan.rows[0].proposed_type == "buy"
    assert plan.rows[0].shares == Decimal("5")


def test_zero_share_corporate_action_stays_out_of_scope() -> None:
    row = _row(
        type_="Corporate action",
        reference="CA-ZERO",
        shares=Decimal("0"),
        price=Decimal("0"),
        amount=Decimal("0"),
    )
    plan = plan_import([row], [], IsinMapDocument())
    assert plan.rows[0].status == RowStatus.OUT_OF_SCOPE_V1
