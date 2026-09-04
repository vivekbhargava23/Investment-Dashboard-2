"""Sync with Scalable — upload the export, safe rows import themselves, the rest is a task list.

The screen is specified in `docs/DESIGN/SYNC-TAB.md`. Everything that decides
anything lives in the sync service and the domain; this file renders.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

import pandas as pd
import streamlit as st

from app.adapters.scalable_csv.parser import ParseError, parse_csv_bytes
from app.adapters.scalable_csv.planner import plan_import
from app.domain.csv_import import PlannedRow, RowStatus
from app.domain.feed_check import FeedCheck
from app.domain.fifo import SellExceedsOpenSharesError, compute_positions
from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction
from app.domain.reconcile import ReconcileRow
from app.domain.sync_tasks import SyncTask, build_tasks
from app.services.feed_check import check_feeds
from app.services.isin_remap import (
    TickerAlreadyMappedError,
    check_consistency,
    repair,
)
from app.services.reconcile import reconcile_book
from app.services.sync import (
    SyncAnalysis,
    SyncApplied,
    UndoNotPossible,
    analyse,
    apply_safe,
    change_feed_in_session,
    resolve_conflict,
    start_session,
    undo_last,
)
from app.ui.cache_keys import transactions_signature
from app.ui.components.isin_mapper import (
    KIND_LABEL,
    SHARED_TICKER_HELP,
    SHARED_TICKER_LABEL,
    invalidate_view_caches,
    render_isin_mapper_row,
    shared_ticker_message,
)
from app.ui.price_clock import last_price_fetch
from app.ui.wiring import (
    get_company_provider,
    get_historical_fx_provider,
    get_isin_map_repo,
    get_price_provider,
    get_repository,
    get_sync_store,
    get_ticker_resolver,
)

_NS = "sync"
_KEY_FILE_MD5 = f"{_NS}.file_md5"
_KEY_FILE_NAME = f"{_NS}.file_name"
_KEY_SESSION_ID = f"{_NS}.session_id"
_KEY_ANALYSIS = f"{_NS}.analysis"
_KEY_APPLIED = f"{_NS}.applied"
_KEY_FEEDBACK = f"{_NS}.feedback"
_KEY_SELECTED = f"{_NS}.selected_isin"

_CASH_TYPES: dict[str, str] = {
    "Distribution": "dividends",
    "Interest": "interest",
    "Taxes": "taxes",
}


# ─── pure helpers ─────────────────────────────────────────────────────────────

def file_md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def summary_card_lines(
    applied: SyncApplied,
    analysis: SyncAnalysis,
    rows: list[ReconcileRow],
    *,
    first_sync: bool,
) -> list[str]:
    """The card's sentences, in order — exactly the design doc's wording.

    The holdings sentence is a claim about the whole book, so it is only made
    when the file covers the whole book.
    """
    lines = [
        f"{applied.inserted} new trades imported · {applied.already_known} already known"
    ]
    if first_sync:
        lines.append("First sync — make sure the export covers all time")
    elif analysis.completeness.partial:
        lines.append("Holdings comparison skipped — this file looks partial")
    else:
        matched = sum(1 for r in rows if r.matches)
        total = len(rows)
        if total and matched == total:
            lines.append(f"Holdings match this Scalable export ({matched}/{total})")
        else:
            lines.append(f"{total - matched} holdings differed")
    return lines


def market_values_line(fetched_at: datetime | None) -> str:
    when = fetched_at.strftime("%d %b %Y %H:%M") if fetched_at else "not fetched yet"
    return f"Market values are estimates from yfinance as of {when}."


def feed_check_cell(check: FeedCheck | None) -> str:
    """One holdings-table cell describing the feed check for that ISIN."""
    if check is None or check.status == "unchecked":
        return "—"
    if check.status == "no_feed":
        return "⚠ no feed"
    if check.status == "suspicious":
        return (
            f"⚠ looks wrong · you €{check.avg_trade_price_eur or Decimal('0'):.2f} / "
            f"feed €{check.avg_close_eur or Decimal('0'):.2f}"
        )
    return f"✓ within {check.median_deviation_pct or Decimal('0'):.1f} %"


def _feed_cell(isin: str, doc: IsinMapDocument) -> str:
    """The ticker this ISIN values off, or "—" when it has no feed.

    The design doc's "ticker · ccy" would need a resolver call per holding; the
    map stores no currency, and a table that fetches one is not worth the wait.
    """
    mapping = doc.entries.get(isin)
    if mapping is None or mapping.status != "mapped" or not mapping.ticker:
        return "—"
    return mapping.ticker


def build_holdings_dataframe(
    rows: list[ReconcileRow],
    checks: dict[str, FeedCheck],
    doc: IsinMapDocument,
) -> pd.DataFrame:
    """One row per ISIN held in the file or in the book. Order matches ``rows``."""
    records = [
        {
            "Name (Scalable)": row.name,
            "Shares Scalable": float(row.shares_csv),
            "Shares dashboard": float(row.shares_book),
            "Feed": _feed_cell(row.isin, doc),
            "Feed check": feed_check_cell(checks.get(row.isin)),
            "Tax kind": _tax_kind_cell(row.isin, doc),
        }
        for row in rows
    ]
    return pd.DataFrame(
        records,
        columns=[
            "Name (Scalable)",
            "Shares Scalable",
            "Shares dashboard",
            "Feed",
            "Feed check",
            "Tax kind",
        ],
    )


def _tax_kind_cell(isin: str, doc: IsinMapDocument) -> str:
    mapping = doc.entries.get(isin)
    if mapping is None or mapping.instrument_kind is None:
        return "⚠ unset"
    return KIND_LABEL.get(mapping.instrument_kind, mapping.instrument_kind.value)


def cash_line(rows: tuple[PlannedRow, ...] | list[PlannedRow]) -> str | None:
    """The cash-events line for this file, or None when the file has none.

    Read from the file only — cash events are information, never stored.
    """
    totals: dict[str, Decimal] = {label: Decimal("0") for label in _CASH_TYPES.values()}
    seen = False
    for row in rows:
        label = _CASH_TYPES.get(row.csv_type)
        if label is None or row.amount is None:
            continue
        if row.status == RowStatus.CANCELLED_OR_EXPIRED:
            continue
        totals[label] += abs(row.amount)
        seen = True
    if not seen:
        return None
    parts = [f"€{totals[label]:,.2f} {label}" for label in ("dividends", "interest", "taxes")]
    return "Cash events in this file: " + " · ".join(parts)


def undo_enabled(log: list[dict[str, object]], current_md5s: tuple[str, str]) -> bool:
    """True when the last logged sync still owns both files as they are now.

    A plain comparison, never a try/except probe: undoing is destructive, so it
    is offered only when it is known to be safe.
    """
    if not log:
        return False
    last = log[-1]
    if last.get("event") == "undo":
        return False
    return (last.get("portfolio_md5_after"), last.get("isin_map_md5_after")) == current_md5s


def last_sync_line(log: list[dict[str, object]]) -> str:
    """The one-line history shown when no file is open."""
    applies = [e for e in log if e.get("event") == "apply"]
    if not applies:
        return "No sync yet — drop a Scalable export below to start."
    last = applies[-1]
    timestamp = str(last.get("timestamp", ""))[:10]
    inserted = last.get("inserted", 0)
    if last.get("partial"):
        tail = "holdings comparison skipped (partial file)"
    else:
        tail = "holdings matched Scalable"
    return f"Last sync: {timestamp} · {inserted} trades · {tail}"


def sell_errors_by_isin(transactions: list[Transaction]) -> dict[str, str]:
    """Per-ISIN FIFO breakages, so one bad holding cannot hide the others."""
    by_isin: dict[str, list[Transaction]] = {}
    for tx in transactions:
        if tx.isin:
            by_isin.setdefault(tx.isin, []).append(tx)

    errors: dict[str, str] = {}
    today = date.today()
    for isin, txs in by_isin.items():
        try:
            compute_positions(txs, today)
        except SellExceedsOpenSharesError as exc:
            errors[isin] = str(exc)
    return errors


# ─── cached reads ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=900, show_spinner=False)
def _cached_feed_checks(tx_sig: str) -> dict[str, FeedCheck]:
    return check_feeds(
        get_repository().load_all(),
        get_isin_map_repo().load(),
        get_price_provider(),
        get_historical_fx_provider(),
    )


# ─── sections ─────────────────────────────────────────────────────────────────

def _render_feedback() -> None:
    feedback = st.session_state.pop(_KEY_FEEDBACK, None)
    if not feedback:
        return
    level, message = feedback
    {"success": st.success, "warning": st.warning, "error": st.error}[level](message)


def _render_consistency_banner(doc: IsinMapDocument) -> None:
    """Mapped ISINs whose stored rows disagree with the map (ADR-014 rule 9)."""
    mismatches = check_consistency(doc, get_repository().load_all())
    if not mismatches:
        return

    n = len({isin for isin, _, _ in mismatches})
    col_msg, col_btn = st.columns([5, 1])
    with col_msg:
        st.warning(f"{n} mapping(s) are out of sync with the book")
        st.caption(
            " · ".join(
                f"{isin}: map says {map_ticker}, book says {stored}"
                for isin, map_ticker, stored in mismatches[:5]
            )
        )
    with col_btn:
        if st.button("Repair", key="sync_repair", type="primary"):
            changed = repair(doc, get_repository())
            invalidate_view_caches()
            st.session_state[_KEY_FEEDBACK] = (
                "success",
                f"Repaired {changed} transaction(s) to match the mapping.",
            )
            st.rerun()


def _run_sync(data: bytes, file_name: str) -> None:
    """Parse, open a session, analyse and apply the safe rows. One shot per file."""
    try:
        rows = parse_csv_bytes(data)
    except ParseError as exc:
        st.error(f"This file could not be read: {exc}")
        return

    store = get_sync_store()
    with st.spinner("Syncing…"):
        session_id = start_session(file_name, file_md5(data), store)
        analysis = analyse(
            rows,
            session_id,
            get_repository(),
            get_isin_map_repo(),
            get_ticker_resolver(),
            get_company_provider(),
            store,
            plan_import,
        )
        applied = apply_safe(analysis, session_id, get_repository(), store)

    st.session_state[_KEY_FILE_MD5] = file_md5(data)
    st.session_state[_KEY_FILE_NAME] = file_name
    st.session_state[_KEY_SESSION_ID] = session_id
    st.session_state[_KEY_ANALYSIS] = analysis
    st.session_state[_KEY_APPLIED] = applied
    invalidate_view_caches()
    st.rerun()


def _render_undo_button(store: Any, *, key: str) -> None:
    enabled = undo_enabled(store.read_log(), store.current_md5s())
    help_text = (
        "Restores portfolio.json and isin_map.json to the state before the last upload."
        if enabled
        else "Your data changed after the last sync, so undo would discard that change."
    )
    if st.button("Undo last sync", key=key, disabled=not enabled, help=help_text):
        try:
            undo_last(store)
        except UndoNotPossible as exc:
            st.session_state[_KEY_FEEDBACK] = ("warning", str(exc))
            st.rerun()
        _clear_file_state()
        invalidate_view_caches()
        st.session_state[_KEY_FEEDBACK] = (
            "success",
            "Undone. Both files are back to their previous state.",
        )
        st.rerun()


def _clear_file_state() -> None:
    for key in (
        _KEY_FILE_MD5,
        _KEY_FILE_NAME,
        _KEY_SESSION_ID,
        _KEY_ANALYSIS,
        _KEY_APPLIED,
        _KEY_SELECTED,
    ):
        st.session_state.pop(key, None)


def _render_summary_card(
    applied: SyncApplied,
    analysis: SyncAnalysis,
    rows: list[ReconcileRow],
    *,
    first_sync: bool,
) -> None:
    with st.container(border=True):
        lines = summary_card_lines(applied, analysis, rows, first_sync=first_sync)
        st.markdown(f"**✅ {lines[0]}**")
        for line in lines[1:]:
            st.markdown(line)
        st.caption(market_values_line(last_price_fetch()))
        _render_undo_button(get_sync_store(), key="sync_undo_card")


def _render_mapper_action(
    isin: str,
    name: str,
    session_id: str,
    *,
    key_prefix: str,
) -> None:
    """Ticker search + tax kind + Save/Ignore for one ISIN."""
    match, kind = render_isin_mapper_row(isin, name, key_prefix=key_prefix)
    allow_shared = st.checkbox(
        SHARED_TICKER_LABEL,
        key=f"{key_prefix}_shared_{isin}",
        help=SHARED_TICKER_HELP,
    )
    col_save, col_ignore, _ = st.columns([1, 1, 4])
    if col_save.button(
        "Save",
        key=f"{key_prefix}_save_{isin}",
        type="primary",
        disabled=match is None or kind is None,
    ):
        if match is None or kind is None:
            return
        try:
            rewritten = change_feed_in_session(
                isin,
                match.symbol,
                kind,
                session_id,
                get_isin_map_repo(),
                get_repository(),
                get_sync_store(),
                allow_shared_ticker=allow_shared,
            )
        except TickerAlreadyMappedError as exc:
            st.session_state[_KEY_FEEDBACK] = ("warning", shared_ticker_message(exc))
            st.rerun()
        invalidate_view_caches()
        st.session_state[_KEY_FEEDBACK] = (
            "success",
            f"{isin} now values off {match.symbol}. Rewrote {rewritten} transaction(s).",
        )
        st.rerun()

    if col_ignore.button("Ignore", key=f"{key_prefix}_ignore_{isin}"):
        _ignore(isin, name)


def _ignore(isin: str, name: str) -> None:
    """Stop asking about this ISIN. It keeps its last-trade valuation."""
    repo = get_isin_map_repo()
    doc = repo.load()
    existing = doc.entries.get(isin)
    entry = IsinMapping(
        ticker=None,
        name=existing.name if existing else (name or isin),
        status="ignored",
        last_seen_in_csv=existing.last_seen_in_csv if existing else None,
        instrument_kind=existing.instrument_kind if existing else None,
    )
    repo.save(
        IsinMapDocument(version=doc.version, entries={**doc.entries, isin: entry})
    )
    invalidate_view_caches()
    st.session_state[_KEY_FEEDBACK] = ("success", f"Ignored {name or isin}.")
    st.rerun()


def _render_tasks(
    tasks: list[SyncTask],
    analysis: SyncAnalysis,
    session_id: str,
) -> None:
    if not tasks:
        return

    noun = "thing needs" if len(tasks) == 1 else "things need"
    st.subheader(f"{len(tasks)} {noun} you")
    decisions = {row.reference: row for row in analysis.decision_rows}

    for index, task in enumerate(tasks):
        with st.container(border=True):
            st.markdown(f"**{index + 1}. {task.headline}**")
            st.caption(task.detail)

            if task.kind in ("no_feed", "feed_suspicious"):
                _render_mapper_action(
                    task.isin,
                    task.name,
                    session_id,
                    key_prefix=f"sync_task_{index}",
                )
            elif task.kind == "possible_duplicate":
                _render_duplicate_actions(task, decisions, session_id, index)


def _render_duplicate_actions(
    task: SyncTask,
    decisions: dict[str, PlannedRow],
    session_id: str,
    index: int,
) -> None:
    row = next(
        (r for r in decisions.values() if r.isin == task.isin and r.description == task.name),
        None,
    )
    if row is None:
        return

    col_replace, col_both, _ = st.columns([1.4, 1, 3])
    if col_replace.button(
        "Replace with Scalable row", key=f"sync_dup_replace_{index}", type="primary"
    ):
        _apply_decision(row, "replace", session_id)
    if col_both.button("Keep both", key=f"sync_dup_keep_{index}"):
        _apply_decision(row, "keep_both", session_id)


def _apply_decision(row: PlannedRow, choice: str, session_id: str) -> None:
    resolve_conflict(
        row,
        cast(Any, choice),
        session_id,
        get_repository(),
        get_sync_store(),
    )
    invalidate_view_caches()
    message = (
        "Replaced your manual entry with the Scalable row."
        if choice == "replace"
        else "Kept both entries."
    )
    st.session_state[_KEY_FEEDBACK] = ("success", message)
    st.rerun()


def _render_holdings(
    rows: list[ReconcileRow],
    checks: dict[str, FeedCheck],
    doc: IsinMapDocument,
    session_id: str,
) -> None:
    st.subheader("Holdings")
    open_rows = [r for r in rows if r.shares_csv > 0 or r.shares_book > 0]
    if not open_rows:
        st.caption("No open holdings in this file.")
        return

    event = st.dataframe(
        build_holdings_dataframe(open_rows, checks, doc),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="sync_holdings_table",
    )
    selected = cast(Any, event).selection.rows
    if not selected:
        st.caption("Select a holding to change its price feed or ignore it.")
        return

    row = open_rows[selected[0]]
    st.caption(f"Selected **{row.name}** ({row.isin})")
    _render_mapper_action(row.isin, row.name, session_id, key_prefix="sync_holding")


def _render_details(analysis: SyncAnalysis, log: list[dict[str, object]]) -> None:
    with st.expander("Details", expanded=False):
        st.caption("Every row of the file, and what the app decided to do with it.")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Row": r.row_number,
                        "Date": r.trade_date,
                        "Type": r.csv_type,
                        "Name": r.description,
                        "ISIN": r.isin,
                        "Shares": float(r.shares) if r.shares is not None else None,
                        "Price": float(r.price) if r.price is not None else None,
                        "Status": str(r.status),
                        "Ticker": r.proposed_ticker or "—",
                    }
                    for r in analysis.plan.rows
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("Row counts by status")
        st.dataframe(
            pd.DataFrame(
                sorted(analysis.plan.count_by_status().items()),
                columns=["Status", "Rows"],
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("Last 5 log entries")
        st.json(log[-5:])


def _render_all_instruments() -> None:
    with st.expander("All instruments", expanded=False):
        st.caption("See ISIN Mappings page.")


# ─── page entry point ─────────────────────────────────────────────────────────

def render() -> None:
    # The topbar already names the page; a second title just eats vertical space.
    _render_feedback()

    store = get_sync_store()
    doc = get_isin_map_repo().load()
    _render_consistency_banner(doc)

    uploaded = st.file_uploader(
        "Drop your Scalable Capital CSV export here",
        type=["csv"],
        key="sync_uploader",
    )
    if uploaded is not None:
        data = uploaded.getvalue()
        if file_md5(data) != st.session_state.get(_KEY_FILE_MD5):
            _run_sync(data, uploaded.name)

    analysis: SyncAnalysis | None = st.session_state.get(_KEY_ANALYSIS)
    applied: SyncApplied | None = st.session_state.get(_KEY_APPLIED)
    session_id: str | None = st.session_state.get(_KEY_SESSION_ID)

    if analysis is None or applied is None or session_id is None:
        st.caption(last_sync_line(store.read_log()))
        _render_undo_button(store, key="sync_undo_idle")
        _render_all_instruments()
        return

    transactions = get_repository().load_all()
    rows = reconcile_book(analysis.plan, get_repository())
    if analysis.completeness.partial:
        rows = []
    # The completeness check ran before anything was applied, so an absent
    # book_start means there was no Scalable history at all: a first-ever sync.
    first_sync = analysis.completeness.book_start is None

    _render_summary_card(applied, analysis, rows, first_sync=first_sync)

    try:
        # Keyed on the book itself: the same book must not re-fetch every close
        # just because this upload inserted a different number of rows.
        checks = _cached_feed_checks(transactions_signature(transactions))
    except Exception:
        checks = {}

    feed_states = {
        r.isin: r.feed_state for r in analysis.plan.rows if r.isin and r.feed_state
    }
    tasks = build_tasks(
        rows,
        checks,
        sell_errors_by_isin(transactions),
        analysis.decision_rows,
        analysis.completeness,
        feed_states,
    )
    _render_tasks(tasks, analysis, session_id)

    _render_holdings(rows, checks, doc, session_id)

    line = cash_line(analysis.plan.rows)
    if line:
        st.caption(line)

    _render_details(analysis, store.read_log())
    _render_all_instruments()
