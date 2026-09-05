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
from app.domain.csv_import import (
    CASH_ASSET_TYPE,
    CORPORATE_ACTION_TYPE,
    PlannedRow,
    RowStatus,
)
from app.domain.feed_check import FeedCheck
from app.domain.fifo import SellExceedsOpenSharesError, compute_positions
from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction
from app.domain.reconcile import ReconcileRow
from app.domain.sync_tasks import SyncTask, build_tasks
from app.services.feed_check import check_feeds
from app.services.isin_admin import apply_restore, open_shares_for_isin
from app.services.isin_remap import (
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
    repair_in_session,
    resolve_conflict,
    start_session,
    undo_last,
)
from app.ui.cache_keys import transactions_signature
from app.ui.components.explainers import (
    ALL_INSTRUMENTS,
    CASH_EVENTS,
    HOLDINGS_TABLE,
    HOW_THIS_PAGE_WORKS,
    TASK_EXPLAINERS,
    UNDO,
    render_explainer,
)
from app.ui.components.instrument_card import (
    KIND_LABEL,
    CardContext,
    invalidate_view_caches,
    render_instrument_card,
)
from app.ui.components.instrument_card import render_feedback as render_card_feedback
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

_CORPORATE_ACTION_LABEL = "corporate actions"

# The order the cash line reads in.
_CASH_LABELS = ("dividends", "interest", "taxes", _CORPORATE_ACTION_LABEL)


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
    totals: dict[str, Decimal] = {label: Decimal("0") for label in _CASH_LABELS}
    seen = False
    for row in rows:
        if row.status == RowStatus.CANCELLED_OR_EXPIRED or row.amount is None:
            continue
        # The Cash leg of a corporate action is the payout that came with the
        # share movement — information, never imported (SYNC-TAB import scope).
        if (
            row.csv_type == CORPORATE_ACTION_TYPE
            and row.asset_type == CASH_ASSET_TYPE
        ):
            label = _CORPORATE_ACTION_LABEL
        else:
            cash_label = _CASH_TYPES.get(row.csv_type)
            if cash_label is None:
                continue
            label = cash_label
        totals[label] += abs(row.amount)
        seen = True
    if not seen:
        return None
    parts = [f"€{totals[label]:,.2f} {label}" for label in _CASH_LABELS]
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
    render_card_feedback()
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
            session_id = st.session_state.get(_KEY_SESSION_ID)
            if session_id:
                changed = repair_in_session(
                    session_id, get_isin_map_repo(), get_repository(), get_sync_store()
                )
            else:
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
    col_btn, col_why, _ = st.columns([1.2, 1.4, 3.4])
    with col_why:
        render_explainer(UNDO, key=f"{key}_why")
    if col_btn.button("Undo last sync", key=key, disabled=not enabled, help=help_text):
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


def _render_card(
    isin: str,
    name: str,
    doc: IsinMapDocument,
    session_id: str | None,
    *,
    key_prefix: str,
    context: CardContext = "task",
) -> None:
    """One instrument card: feed, tax kind, and (in All instruments) removal."""
    render_instrument_card(
        isin,
        name,
        doc,
        session_id=session_id,
        key_prefix=key_prefix,
        context=context,
    )


def _render_tasks(
    tasks: list[SyncTask],
    analysis: SyncAnalysis,
    doc: IsinMapDocument,
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
            explainer = TASK_EXPLAINERS.get(task.kind)
            if explainer is not None:
                render_explainer(explainer, key=f"sync_task_why_{index}")

            if task.kind in ("no_feed", "feed_suspicious"):
                _render_card(
                    task.isin,
                    task.name,
                    doc,
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
    col_title, col_why = st.columns([3, 1.4])
    col_title.subheader("Holdings")
    with col_why:
        render_explainer(HOLDINGS_TABLE, key="sync_holdings_why")
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
        st.caption("Select a holding to change its price feed or value it at its last trade price.")
        return

    row = open_rows[selected[0]]
    _render_card(
        row.isin, row.name, doc, session_id, key_prefix="sync_holding", context="holding"
    )


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


def build_mapped_dataframe(items: list[tuple[str, IsinMapping]]) -> pd.DataFrame:
    """The Mapped table. Row order matches ``items`` so a selection index maps back."""
    records = [
        {
            "ISIN": isin,
            "Name": mapping.name or "—",
            "Feed": mapping.ticker or "—",
            "Tax kind": (
                KIND_LABEL.get(mapping.instrument_kind, mapping.instrument_kind.value)
                if mapping.instrument_kind is not None
                else "⚠ unset"
            ),
            "Last seen": mapping.last_seen_in_csv,
        }
        for isin, mapping in items
    ]
    return pd.DataFrame(
        records, columns=["ISIN", "Name", "Feed", "Tax kind", "Last seen"]
    )


def build_closed_dataframe(items: list[tuple[str, IsinMapping]]) -> pd.DataFrame:
    """Instruments with no feed and nothing left open — tax history only."""
    records = [
        {"ISIN": isin, "Name": mapping.name or "—", "Last seen": mapping.last_seen_in_csv}
        for isin, mapping in items
    ]
    return pd.DataFrame(records, columns=["ISIN", "Name", "Last seen"])


def _select_one(df: pd.DataFrame, key: str) -> int | None:
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=key,
        column_config={"Last seen": st.column_config.DateColumn(format="YYYY-MM-DD")},
    )
    rows = cast(Any, event).selection.rows
    return rows[0] if rows else None


def _render_all_instruments(doc: IsinMapDocument, session_id: str | None) -> None:
    """Everything the ISIN Mappings page offered, on the Sync tab's own terms."""
    mapped = sorted(
        ((i, m) for i, m in doc.entries.items() if m.status == "mapped"),
        key=lambda pair: (pair[1].name or pair[0]).lower(),
    )
    ignored = sorted(
        ((i, m) for i, m in doc.entries.items() if m.status == "ignored"),
        key=lambda pair: (pair[1].name or pair[0]).lower(),
    )
    repo = get_repository()
    closed = sorted(
        (
            (i, m)
            for i, m in doc.entries.items()
            if m.status == "unmapped" and open_shares_for_isin(repo, i) <= 0
        ),
        key=lambda pair: (pair[1].name or pair[0]).lower(),
    )

    with st.expander("All instruments", expanded=False):
        unclassified = sum(1 for _, m in mapped if m.instrument_kind is None)
        caption = f"{len(mapped)} with a feed · {len(closed)} closed without one"
        if ignored:
            caption += f" · {len(ignored)} valued at last trade price"
        if unclassified:
            caption += f" · ⚠ {unclassified} missing a tax kind"
        col_caption, col_why = st.columns([4, 1.4])
        col_caption.caption(caption)
        with col_why:
            render_explainer(ALL_INSTRUMENTS, key="sync_all_why")

        st.markdown("**Mapped**")
        if not mapped:
            st.caption("No instrument has a price feed yet.")
        else:
            index = _select_one(
                build_mapped_dataframe(mapped), "sync_all_mapped_table"
            )
            if index is None:
                st.caption("Select a row to change its feed, tax kind, or remove it.")
            else:
                isin, mapping = mapped[index]
                _render_card(
                    isin,
                    mapping.name,
                    doc,
                    session_id,
                    key_prefix="sync_all_mapped",
                    context="all_instruments",
                )

        if closed:
            st.markdown("**Closed, no feed**")
            st.caption("Nothing open — these only affect your tax history.")
            index = _select_one(
                build_closed_dataframe(closed), "sync_all_closed_table"
            )
            if index is not None:
                isin, mapping = closed[index]
                _render_card(
                    isin,
                    mapping.name,
                    doc,
                    session_id,
                    key_prefix="sync_all_closed",
                    context="all_instruments",
                )

        if ignored:
            st.markdown("**Valued at last trade price**")
            for isin, mapping in ignored:
                col_name, col_btn = st.columns([5, 1])
                col_name.write(f"{mapping.name or '—'} · `{isin}`")
                if col_btn.button("Restore", key=f"sync_restore_{isin}"):
                    get_isin_map_repo().save(apply_restore(doc, isin))
                    invalidate_view_caches()
                    st.session_state[_KEY_FEEDBACK] = (
                        "success",
                        f"{mapping.name or isin} will be asked about again.",
                    )
                    st.rerun()


# ─── page entry point ─────────────────────────────────────────────────────────

def render() -> None:
    # The topbar already names the page; a second title just eats vertical space.
    _render_feedback()

    store = get_sync_store()
    doc = get_isin_map_repo().load()
    _render_consistency_banner(doc)

    render_explainer(HOW_THIS_PAGE_WORKS, key="sync_page_why")

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
        _render_all_instruments(doc, None)
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
        with st.spinner("Checking price feeds against your trades…"):
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
    _render_tasks(tasks, analysis, doc, session_id)

    _render_holdings(rows, checks, doc, session_id)

    line = cash_line(analysis.plan.rows)
    if line:
        col_line, col_why = st.columns([4, 1.2])
        col_line.caption(line)
        with col_why:
            render_explainer(CASH_EVENTS, key="sync_cash_why")

    _render_details(analysis, store.read_log())
    _render_all_instruments(doc, session_id)
