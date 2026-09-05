"""Orchestration for one sync session: analyse, apply, decide, undo.

A sync session is everything that happens while one uploaded file is open. It
opens with a snapshot of both data files taken *before* any write (auto-resolve
included), and every write logs the same ``session_id`` plus the md5s of both
files afterwards. "Undo last sync" restores that snapshot, and only while the
files still carry the md5s the session's last entry recorded.

No I/O lives here: bytes, temp files and hashing are the store's job.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from app.domain.csv_import import (
    CORPORATE_ACTION_TYPE,
    ImportPlan,
    PlannedRow,
    RowStatus,
)
from app.domain.isin_map import IsinMapDocument
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.sync_completeness import CompletenessResult, check_completeness
from app.domain.tax.classification import InstrumentKind
from app.ports.company_data import CompanyDataProvider
from app.ports.csv_planner import ImportPlanner
from app.ports.isin_map import IsinMapRepository
from app.ports.repository import TransactionRepository
from app.ports.sync_store import SyncStore
from app.ports.ticker_resolver import TickerResolver
from app.services.isin_admin import apply_ignore, apply_kind, open_shares_for_isin
from app.services.isin_autoresolve import AutoResolveResult, autoresolve_isin
from app.services.isin_remap import (
    change_feed,
    mapped_owner_of_ticker,
    record_seen_isins,
    repair,
)

EVENT_SESSION_START = "session_start"
EVENT_AUTO_RESOLVE = "auto_resolve"
EVENT_APPLY = "apply"
EVENT_CONFLICT = "conflict_resolved"
EVENT_FEED_CHANGE = "feed_change"
EVENT_IGNORE = "ignore"
EVENT_KIND = "kind_change"
EVENT_REPAIR = "repair"
EVENT_WRITE_OFF = "write_off"
EVENT_UNDO = "undo"


@dataclass(frozen=True)
class SyncAnalysis:
    plan: ImportPlan
    completeness: CompletenessResult
    safe_rows: list[PlannedRow]
    decision_rows: list[PlannedRow]
    auto_resolved: dict[str, AutoResolveResult]


@dataclass(frozen=True)
class SyncApplied:
    inserted: int
    already_known: int
    snapshot_id: str | None
    log_entry: dict[str, object]


class UndoNotPossible(Exception):
    """Raised when the last sync session can no longer be rolled back safely."""


# ─── logging ──────────────────────────────────────────────────────────────────

def _log(
    store: SyncStore,
    session_id: str,
    event: str,
    **fields: object,
) -> dict[str, object]:
    """Append one log entry carrying the md5s of both files as they are now."""
    portfolio_md5, isin_map_md5 = store.current_md5s()
    entry: dict[str, object] = {
        "timestamp": datetime.now().isoformat(),
        "event": event,
        "session_id": session_id,
        "portfolio_md5_after": portfolio_md5,
        "isin_map_md5_after": isin_map_md5,
        **fields,
    }
    store.append_log(entry)
    return entry


def earliest_logged_file_start(store: SyncStore) -> date | None:
    """Earliest ``file_start`` any previous sync recorded, if any."""
    starts: list[date] = []
    for entry in store.read_log():
        raw = entry.get("file_start")
        if isinstance(raw, str):
            try:
                starts.append(date.fromisoformat(raw))
            except ValueError:
                continue
    return min(starts) if starts else None


# ─── session ──────────────────────────────────────────────────────────────────

def start_session(file_name: str, file_md5: str, store: SyncStore) -> str:
    """Snapshot both data files and open a session. Nothing may write before this."""
    snapshot = store.snapshot()
    session_id = uuid4().hex
    _log(
        store,
        session_id,
        EVENT_SESSION_START,
        snapshot_id=snapshot.id,
        filename=file_name,
        file_md5=file_md5,
    )
    return session_id


def analyse(
    rows: Sequence[object],
    session_id: str,
    tx_repo: TransactionRepository,
    isin_repo: IsinMapRepository,
    resolver: TickerResolver,
    company_provider: CompanyDataProvider,
    store: SyncStore,
    planner: ImportPlanner,
) -> SyncAnalysis:
    """Plan the file, auto-resolve what it can, and re-plan with the new feeds.

    ``session_id`` is required: analysing before :func:`start_session` would let
    auto-resolve write outside the snapshot that undo restores.
    """
    isin_doc = isin_repo.load()
    plan = planner(rows, tx_repo.load_all(), isin_doc)

    # Every ISIN in the file gets an entry before anything else looks at the map,
    # so an unmapped holding has a name to show and a row to be mapped from.
    seen_doc = record_seen_isins(plan.rows, isin_doc)
    if seen_doc is not None:
        isin_repo.save(seen_doc)
        isin_doc = seen_doc

    auto_resolved, isin_doc = _auto_resolve(
        plan, session_id, isin_doc, tx_repo, isin_repo, resolver, company_provider, store
    )
    if auto_resolved:
        plan = planner(rows, tx_repo.load_all(), isin_doc)

    book = tx_repo.load_all()
    completeness = check_completeness(
        plan.rows, book, earliest_logged_file_start(store)
    )

    return SyncAnalysis(
        plan=plan,
        completeness=completeness,
        safe_rows=[r for r in plan.rows if r.status == RowStatus.NEW],
        decision_rows=[
            r for r in plan.rows if r.status == RowStatus.CONFLICT_WITH_MANUAL
        ],
        auto_resolved=auto_resolved,
    )


def _unmapped_isins(plan: ImportPlan) -> list[tuple[str, str]]:
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for row in plan.rows:
        if row.feed_state == "unmapped" and row.isin and row.isin not in seen:
            seen.add(row.isin)
            result.append((row.isin, row.description))
    return result


def _auto_resolve(
    plan: ImportPlan,
    session_id: str,
    isin_doc: IsinMapDocument,
    tx_repo: TransactionRepository,
    isin_repo: IsinMapRepository,
    resolver: TickerResolver,
    company_provider: CompanyDataProvider,
    store: SyncStore,
) -> tuple[dict[str, AutoResolveResult], IsinMapDocument]:
    """Give every unmapped ISIN a feed where the match is confident enough.

    A ticker another mapped ISIN already uses counts as ``low``: merging two
    instruments onto one feed is a deliberate act (ADR-014 rule 4), never
    something auto-resolve does on its own.
    """
    unmapped = _unmapped_isins(plan)
    if not unmapped:
        return {}, isin_doc

    results: dict[str, AutoResolveResult] = {}
    entries = dict(isin_doc.entries)
    saved: list[dict[str, object]] = []

    for isin, description in unmapped:
        result = autoresolve_isin(
            isin,
            description,
            resolver=resolver,
            company_provider=company_provider,
        )
        ticker, kind = result.ticker, result.instrument_kind
        if result.confidence in ("high", "medium") and ticker is not None and kind is not None:
            doc_so_far = IsinMapDocument(version=isin_doc.version, entries=entries)
            owner = mapped_owner_of_ticker(doc_so_far, ticker, isin)
            if owner is not None:
                result = replace(
                    result,
                    confidence="low",
                    reason=f"{ticker} is already the feed for {owner}",
                )
            else:
                new_doc, _ = change_feed(
                    isin,
                    ticker,
                    kind,
                    doc_so_far,
                    tx_repo,
                    name=result.name or description,
                )
                entries = dict(new_doc.entries)
                saved.append({"isin": isin, "ticker": ticker, "kind": kind.value})
        results[isin] = result

    new_doc = IsinMapDocument(version=isin_doc.version, entries=entries)
    if saved:
        isin_repo.save(new_doc)

    _log(
        store,
        session_id,
        EVENT_AUTO_RESOLVE,
        auto_resolved=[
            {
                "isin": isin,
                "ticker": r.ticker,
                "kind": r.instrument_kind.value if r.instrument_kind else None,
                "confidence": r.confidence,
                "reason": r.reason,
            }
            for isin, r in results.items()
        ],
        mapped=saved,
    )
    return results, new_doc


# ─── writes ───────────────────────────────────────────────────────────────────

def build_transaction(row: PlannedRow) -> Transaction | None:
    """Build a Transaction from a planned row, or None if the row cannot be one.

    All Scalable CSV rows are EUR-native: price_native is EUR, fx_rate_eur is 1.
    The ticker is whatever the plan proposed, including an ISIN placeholder — a
    missing feed changes valuation, never what is in the book (ADR-014 rule 7).
    """
    if row.proposed_ticker is None or row.shares is None or row.price is None:
        return None

    # The planner decides the direction: a corporate action carries it in the sign
    # of its share count, not in its CSV type.
    proposed = row.proposed_type or ("sell" if row.csv_type == "Sell" else "buy")
    tx_type = TransactionType.SELL if proposed == "sell" else TransactionType.BUY

    notes_parts = [
        f"corporate action: {row.description}"
        if row.csv_type == CORPORATE_ACTION_TYPE
        else row.description
    ]
    if proposed == "sell" and row.tax is not None and row.tax != Decimal("0"):
        notes_parts.append(f"tax_withheld_eur={row.tax}")
    notes = "; ".join(notes_parts) or None

    fees_native: Money | None = (
        Money(amount=row.fee, currency=Currency.EUR) if row.fee is not None else None
    )

    return Transaction(
        id=row.reference,
        type=tx_type,
        ticker=row.proposed_ticker,
        trade_date=row.trade_date,
        # A corporate action's share count is signed in the file; a transaction
        # always holds a positive quantity and says its direction in ``type``.
        shares=abs(row.shares),
        price_native=Money(amount=row.price, currency=Currency.EUR),
        fees_native=fees_native,
        fx_rate_eur=Decimal("1"),
        notes=notes,
        isin=row.isin or None,
        csv_reference=row.reference,
        source="scalable_csv",
    )


def _snapshot_id_for(store: SyncStore, session_id: str) -> str | None:
    for entry in store.read_log():
        if (
            entry.get("session_id") == session_id
            and entry.get("event") == EVENT_SESSION_START
        ):
            snapshot_id = entry.get("snapshot_id")
            return snapshot_id if isinstance(snapshot_id, str) else None
    return None


def apply_safe(
    analysis: SyncAnalysis,
    session_id: str,
    tx_repo: TransactionRepository,
    store: SyncStore,
) -> SyncApplied:
    """Import every row that is new by Scalable reference. Conflicts are untouched."""
    new_txs = [tx for tx in (build_transaction(r) for r in analysis.safe_rows) if tx]
    already_known = sum(
        1 for r in analysis.plan.rows if r.status == RowStatus.ALREADY_IMPORTED
    )

    if new_txs:
        tx_repo.save_all([*tx_repo.load_all(), *new_txs])

    file_start = analysis.completeness.file_start
    log_entry = _log(
        store,
        session_id,
        EVENT_APPLY,
        inserted=len(new_txs),
        already_known=already_known,
        applied_references=[tx.csv_reference for tx in new_txs],
        partial=analysis.completeness.partial,
        file_start=file_start.isoformat() if file_start else None,
    )

    return SyncApplied(
        inserted=len(new_txs),
        already_known=already_known,
        snapshot_id=_snapshot_id_for(store, session_id),
        log_entry=log_entry,
    )


def resolve_conflict(
    row: PlannedRow,
    choice: Literal["replace", "keep_both"],
    session_id: str,
    tx_repo: TransactionRepository,
    store: SyncStore,
) -> None:
    """Apply the user's decision on a row that looks like a duplicate of a manual entry."""
    tx = build_transaction(row)
    if tx is None:
        raise ValueError(f"Row {row.row_number} cannot be imported as a transaction")

    txs = tx_repo.load_all()
    if choice == "replace" and row.conflict_tx_id is not None:
        txs = [t for t in txs if t.id != row.conflict_tx_id]
    tx_repo.save_all([*txs, tx])

    _log(
        store,
        session_id,
        EVENT_CONFLICT,
        reference=row.reference,
        choice=choice,
        replaced_tx_id=row.conflict_tx_id if choice == "replace" else None,
    )


def change_feed_in_session(
    isin: str,
    ticker: str,
    kind: InstrumentKind,
    session_id: str,
    isin_repo: IsinMapRepository,
    tx_repo: TransactionRepository,
    store: SyncStore,
    *,
    allow_shared_ticker: bool = False,
) -> int:
    """Point ``isin`` at ``ticker`` inside the open session. Returns rows rewritten."""
    isin_doc = isin_repo.load()
    new_doc, rewritten = change_feed(
        isin,
        ticker,
        kind,
        isin_doc,
        tx_repo,
        allow_shared_ticker=allow_shared_ticker,
    )
    isin_repo.save(new_doc)

    _log(
        store,
        session_id,
        EVENT_FEED_CHANGE,
        isin=isin,
        ticker=ticker,
        kind=kind.value,
        rewritten=rewritten,
    )
    return rewritten



def ignore_in_session(
    isin: str,
    name: str,
    session_id: str,
    isin_repo: IsinMapRepository,
    store: SyncStore,
) -> None:
    """Value ``isin`` at its last trade price and stop asking, inside the session.

    The write itself is the same one the idle state makes; logging it under the
    open session is what keeps "Undo last sync" available, because undo compares
    the files against the md5s of the session's *latest* entry.
    """
    isin_repo.save(apply_ignore(isin_repo.load(), isin, name))
    _log(store, session_id, EVENT_IGNORE, isin=isin, name=name)


def set_kind_in_session(
    isin: str,
    kind: InstrumentKind,
    session_id: str,
    isin_repo: IsinMapRepository,
    store: SyncStore,
    *,
    name: str = "",
) -> None:
    """Set the tax kind for ``isin`` inside the session. The feed is untouched."""
    isin_repo.save(apply_kind(isin_repo.load(), isin, kind, name=name))
    _log(store, session_id, EVENT_KIND, isin=isin, kind=kind.value)


def repair_in_session(
    session_id: str,
    isin_repo: IsinMapRepository,
    tx_repo: TransactionRepository,
    store: SyncStore,
) -> int:
    """Re-run the mapping rewrite inside the session. Returns rows changed."""
    changed = repair(isin_repo.load(), tx_repo)
    _log(store, session_id, EVENT_REPAIR, changed=changed)
    return changed


class WriteOffNotPossible(Exception):
    """Raised when a write-off would take a holding below zero shares."""


def _ticker_for(isin: str, isin_repo: IsinMapRepository) -> str:
    """The ticker a write-off trades under: the ISIN's feed, else the ISIN itself.

    Same rule as an imported trade (ADR-014 rule 2), so the row lands on the same
    FIFO position the buys did rather than opening a second one.
    """
    mapping = isin_repo.load().entries.get(isin)
    if mapping is not None and mapping.status == "mapped" and mapping.ticker:
        return mapping.ticker
    return isin.upper()


def build_write_off(
    isin: str,
    name: str,
    shares: Decimal,
    on_date: date,
    isin_repo: IsinMapRepository,
    tx_repo: TransactionRepository,
) -> Transaction:
    """The €0 sell that closes a holding the broker never closed.

    Refuses to write off more than is open: a write-off is an admission that the
    shares are gone, not a way to go short.
    """
    if shares <= Decimal("0"):
        raise WriteOffNotPossible("Write off a positive number of shares.")
    open_shares = open_shares_for_isin(tx_repo, isin)
    if shares > open_shares:
        raise WriteOffNotPossible(
            f"Only {open_shares.normalize():f} share(s) of {name or isin} are open; "
            f"{shares.normalize():f} cannot be written off."
        )

    return Transaction(
        id=f"writeoff-{isin}-{on_date.isoformat()}",
        type=TransactionType.SELL,
        ticker=_ticker_for(isin, isin_repo),
        trade_date=on_date,
        shares=shares,
        price_native=Money(amount=Decimal("0"), currency=Currency.EUR),
        fees_native=None,
        fx_rate_eur=Decimal("1"),
        notes=f"write-off: {name or isin}",
        isin=isin,
        csv_reference=None,
        source="write_off",
    )


def write_off(
    isin: str,
    name: str,
    shares: Decimal,
    on_date: date,
    isin_repo: IsinMapRepository,
    tx_repo: TransactionRepository,
) -> Transaction:
    """Write a holding down to €0, keeping its history. No session open."""
    tx = build_write_off(isin, name, shares, on_date, isin_repo, tx_repo)
    tx_repo.save_all([*tx_repo.load_all(), tx])
    return tx


def write_off_in_session(
    isin: str,
    name: str,
    shares: Decimal,
    on_date: date,
    session_id: str,
    tx_repo: TransactionRepository,
    isin_repo: IsinMapRepository,
    store: SyncStore,
) -> Transaction:
    """Write a holding down to €0 inside the open session, so undo can take it back."""
    tx = build_write_off(isin, name, shares, on_date, isin_repo, tx_repo)
    tx_repo.save_all([*tx_repo.load_all(), tx])
    _log(
        store,
        session_id,
        EVENT_WRITE_OFF,
        isin=isin,
        shares=str(shares),
        on_date=on_date.isoformat(),
    )
    return tx

# ─── undo ─────────────────────────────────────────────────────────────────────

def undo_last(store: SyncStore) -> str:
    """Roll the last sync session back to its pre-upload snapshot.

    Refuses when anything wrote to either file after the session's last entry —
    a Manage-page edit, another session — because restoring would silently
    discard that write.
    """
    log = store.read_log()
    if not log:
        raise UndoNotPossible("There is no sync to undo.")

    last = log[-1]
    if last.get("event") == EVENT_UNDO:
        raise UndoNotPossible("The last sync has already been undone.")

    session_id = last.get("session_id")
    if not isinstance(session_id, str):
        raise UndoNotPossible("The last sync log entry has no session.")

    snapshot_id = _snapshot_id_for(store, session_id)
    if snapshot_id is None:
        raise UndoNotPossible("That sync session has no snapshot to restore.")

    expected = (last.get("portfolio_md5_after"), last.get("isin_map_md5_after"))
    if store.current_md5s() != expected:
        raise UndoNotPossible(
            "Your data changed after that sync — undo would discard the newer change."
        )

    store.restore(snapshot_id)
    _log(store, session_id, EVENT_UNDO, snapshot_id=snapshot_id)
    return session_id
