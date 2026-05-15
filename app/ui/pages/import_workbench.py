"""Import CSV Workbench — row-level visibility into the Scalable Capital CSV import flow."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from app.adapters.scalable_csv.parser import ParsedCsvRow, parse_csv
from app.adapters.scalable_csv.planner import plan_import
from app.domain.csv_import import ImportPlan, PlannedRow, RowStatus
from app.domain.isin_map import IsinMapping
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.ui.wiring import get_isin_map_repo, get_repository

# Session-state key namespace
_NS = "import_workbench"
_KEY_FILE_BYTES = f"{_NS}.file_bytes"
_KEY_FILE_NAME = f"{_NS}.file_name"
_KEY_PARSED_ROWS = f"{_NS}.parsed_rows"
_KEY_PLAN = f"{_NS}.plan"
_KEY_FILTER = f"{_NS}.filter"
_KEY_CONFLICTS = f"{_NS}.conflict_choices"  # {reference: "replace"|"keep"|"skip"}
_KEY_EXCLUDES = f"{_NS}.excluded_refs"      # set of references for new rows to skip

_STATUS_COLORS: dict[str, str] = {
    RowStatus.NEW: "🟢",
    RowStatus.ALREADY_IMPORTED: "⚪",
    RowStatus.CONFLICT_WITH_MANUAL: "🟡",
    RowStatus.UNMAPPED_ISIN: "🔴",
    RowStatus.NEEDS_CURRENCY_SUPPORT: "🔵",
    RowStatus.OUT_OF_SCOPE_V1: "⬜",
    RowStatus.OUTGOING_TRANSFER: "⬜",
    RowStatus.CANCELLED_OR_EXPIRED: "⬜",
    RowStatus.PARSE_ERROR: "🔴",
}


# ─── helpers ──────────────────────────────────────────────────────────────────

def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _load_import_log(log_path: Path) -> list[dict[str, object]]:
    if not log_path.exists():
        return []
    try:
        with open(log_path, encoding="utf-8") as f:
            result: list[dict[str, object]] = json.load(f)
            return result
    except (json.JSONDecodeError, OSError):
        return []


def _append_import_log(log_path: Path, entry: dict[str, object]) -> None:
    entries = _load_import_log(log_path)
    entries.append(entry)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = log_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
    os.replace(tmp, log_path)


def _write_backup(portfolio_path: Path, backups_dir: Path) -> Path:
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    bak = backups_dir / f"portfolio.{stamp}.json.bak"
    shutil.copy2(portfolio_path, bak)
    # Keep only 10 most recent
    existing = sorted(backups_dir.glob("portfolio.*.json.bak"))
    for old in existing[:-10]:
        old.unlink(missing_ok=True)
    return bak


def _build_transaction(row: PlannedRow) -> Transaction | None:
    if row.proposed_ticker is None or row.shares is None or row.price is None:
        return None
    tx_type = (
        TransactionType.SELL
        if row.csv_type == "Sell"
        else TransactionType.BUY
    )
    fees_native: Money | None = (
        Money(amount=row.fee, currency=Currency.EUR) if row.fee is not None else None
    )
    notes_parts = [row.description]
    if row.csv_type == "Sell" and row.tax is not None and row.tax != Decimal("0"):
        notes_parts.append(f"tax_withheld_eur={row.tax}")
    notes = "; ".join(notes_parts) or None
    return Transaction(
        id=row.reference,
        type=tx_type,
        ticker=row.proposed_ticker,
        trade_date=row.trade_date,
        shares=row.shares,
        price_native=Money(amount=row.price, currency=Currency.EUR),
        fees_native=fees_native,
        fx_rate_eur=Decimal("1"),
        notes=notes,
        csv_reference=row.reference,
        source="scalable_csv",
    )


def _count_ready(plan: ImportPlan, conflicts: dict[str, str], excludes: set[str]) -> int:
    count = 0
    for row in plan.rows:
        if row.status == RowStatus.NEW and row.reference not in excludes:
            count += 1
        elif row.status == RowStatus.CONFLICT_WITH_MANUAL:
            choice = conflicts.get(row.reference, "replace")
            if choice == "replace":
                count += 1
    return count


def _clear_state() -> None:
    for key in [_KEY_FILE_BYTES, _KEY_FILE_NAME, _KEY_PARSED_ROWS, _KEY_PLAN,
                _KEY_FILTER, _KEY_CONFLICTS, _KEY_EXCLUDES]:
        st.session_state.pop(key, None)


# ─── sections ─────────────────────────────────────────────────────────────────

def _render_last_import_card(log_path: Path) -> None:
    entries = _load_import_log(log_path)
    if not entries:
        st.info("No imports yet. Upload a CSV to get started.")
        return
    last = entries[-1]
    ts = str(last.get("timestamp", "?"))[:10]
    fn = str(last.get("filename", "?"))
    n = last.get("applied_count", 0)
    st.success(f"Last import: **{fn}** on {ts} — {n} transactions applied.")


def _render_upload_section(log_path: Path) -> bool:
    """Render the upload + status strip. Returns True if a plan is ready."""
    uploaded = st.file_uploader(
        "Upload Scalable Capital CSV export",
        type=["csv"],
        key="import_workbench_uploader",
        label_visibility="collapsed",
    )

    if uploaded is None:
        _render_last_import_card(log_path)
        _clear_state()
        return False

    file_bytes = uploaded.read()
    file_name = uploaded.name

    # Re-parse only if file changed
    file_changed = (
        st.session_state.get(_KEY_FILE_NAME) != file_name
        or st.session_state.get(_KEY_FILE_BYTES) != file_bytes
    )
    if file_changed:
        import tempfile

        st.session_state[_KEY_FILE_BYTES] = file_bytes
        st.session_state[_KEY_FILE_NAME] = file_name
        st.session_state.pop(_KEY_PARSED_ROWS, None)
        st.session_state.pop(_KEY_PLAN, None)
        st.session_state.pop(_KEY_CONFLICTS, None)
        st.session_state.pop(_KEY_EXCLUDES, None)

        try:
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = Path(tmp.name)
            rows = parse_csv(tmp_path)
            tmp_path.unlink(missing_ok=True)
            st.session_state[_KEY_PARSED_ROWS] = rows
        except Exception as exc:
            st.error(f"Failed to parse CSV: {exc}")
            return False

    parsed_rows: list[ParsedCsvRow] = st.session_state.get(_KEY_PARSED_ROWS, [])

    if _KEY_PLAN not in st.session_state:
        tx_repo = get_repository()
        isin_repo = get_isin_map_repo()
        existing_txs = tx_repo.load_all()
        isin_doc = isin_repo.load()
        new_plan = plan_import(parsed_rows, existing_txs, isin_doc)
        st.session_state[_KEY_PLAN] = new_plan
        if _KEY_CONFLICTS not in st.session_state:
            st.session_state[_KEY_CONFLICTS] = {}
        if _KEY_EXCLUDES not in st.session_state:
            st.session_state[_KEY_EXCLUDES] = set()

    active_plan: ImportPlan = st.session_state[_KEY_PLAN]
    counts = active_plan.count_by_status()

    n_new = counts.get(RowStatus.NEW, 0)
    n_already = counts.get(RowStatus.ALREADY_IMPORTED, 0)
    n_conflicts = counts.get(RowStatus.CONFLICT_WITH_MANUAL, 0)
    n_blocked = sum(
        counts.get(s, 0)
        for s in (RowStatus.UNMAPPED_ISIN, RowStatus.NEEDS_CURRENCY_SUPPORT,
                  RowStatus.OUT_OF_SCOPE_V1, RowStatus.OUTGOING_TRANSFER,
                  RowStatus.CANCELLED_OR_EXPIRED, RowStatus.PARSE_ERROR)
    )

    st.caption(
        f"**{file_name}** — Parsed {len(parsed_rows)} rows · "
        f"{n_already} already imported · {n_new} new · "
        f"{n_conflicts} conflicts · {n_blocked} blocked"
    )

    col1, col2 = st.columns([0.9, 0.1])
    with col2:
        if st.button("Clear", key="iw_clear_btn"):
            _clear_state()
            st.rerun()

    return True


def _render_raw_preview(rows: list[ParsedCsvRow], file_bytes: bytes, file_name: str) -> None:
    st.subheader("Raw CSV — exactly as Scalable exported it")
    raw_data = [
        {
            "Row": r.row_number,
            "Date": r.date.isoformat(),
            "Status": r.status,
            "Reference": r.reference,
            "Description": r.description[:50],
            "Type": r.type,
            "ISIN": r.isin,
            "Shares": str(r.shares) if r.shares is not None else "",
            "Price": str(r.price) if r.price is not None else "",
            "Amount": str(r.amount) if r.amount is not None else "",
            "Fee": str(r.fee) if r.fee is not None else "",
            "Currency": r.currency,
        }
        for r in rows
    ]
    st.dataframe(pd.DataFrame(raw_data), height=350, use_container_width=True)
    md5 = _md5(file_bytes)
    st.caption(
        f"File: **{file_name}** · {len(file_bytes):,} bytes · MD5: `{md5}` · {len(rows)} rows"
    )


def _render_filter_chips(plan: ImportPlan) -> str | None:
    """Render status filter chips. Returns the active filter or None."""
    counts = plan.count_by_status()
    active = st.session_state.get(_KEY_FILTER)

    statuses = [
        (RowStatus.NEW, "new"),
        (RowStatus.ALREADY_IMPORTED, "already imported"),
        (RowStatus.CONFLICT_WITH_MANUAL, "conflicts"),
        (RowStatus.UNMAPPED_ISIN, "unmapped ISIN"),
        (RowStatus.NEEDS_CURRENCY_SUPPORT, "needs currency"),
        (RowStatus.OUT_OF_SCOPE_V1, "out of scope"),
        (RowStatus.OUTGOING_TRANSFER, "outgoing transfer"),
        (RowStatus.CANCELLED_OR_EXPIRED, "cancelled/expired"),
    ]

    cols = st.columns(len(statuses) + 1)
    with cols[0]:
        label = f"All ({len(plan.rows)})"
        all_btn_type: str = "primary" if active is None else "secondary"
        if st.button(label, key="iw_filter_all", type=all_btn_type):  # type: ignore[arg-type]
            st.session_state[_KEY_FILTER] = None
            st.rerun()

    for i, (status, label_text) in enumerate(statuses, 1):
        n = counts.get(status, 0)
        if n == 0:
            continue
        with cols[i]:
            btn_label = f"{label_text} ({n})"
            is_active = active == status
            btn_type = "primary" if is_active else "secondary"
            if st.button(btn_label, key=f"iw_filter_{status}", type=btn_type):  # type: ignore[arg-type]
                st.session_state[_KEY_FILTER] = None if is_active else status
                st.rerun()

    return active


def _render_planned_changes(plan: ImportPlan) -> None:
    st.subheader("Planned changes")

    active_filter = _render_filter_chips(plan)

    rows_to_show = [
        r for r in plan.rows
        if active_filter is None or r.status == active_filter
    ]

    excludes: set[str] = st.session_state.get(_KEY_EXCLUDES, set())
    conflicts: dict[str, str] = st.session_state.get(_KEY_CONFLICTS, {})

    table_data = []
    for r in rows_to_show:
        dot = _STATUS_COLORS.get(r.status, "⬜")
        action_label = ""
        if r.status == RowStatus.NEW:
            action_label = "skip" if r.reference in excludes else "will import"
        elif r.status == RowStatus.CONFLICT_WITH_MANUAL:
            action_label = conflicts.get(r.reference, "replace")
        elif r.status == RowStatus.ALREADY_IMPORTED:
            action_label = "no-op"
        else:
            action_label = r.status.replace("_", " ")

        table_data.append({
            "Status": f"{dot} {r.status.replace('_', ' ')}",
            "Date": r.trade_date.isoformat(),
            "Type": r.csv_type,
            "Ticker": r.proposed_ticker or "—",
            "ISIN": r.isin,
            "Description": r.description[:40],
            "Shares": str(r.shares) if r.shares is not None else "—",
            "Price €": str(r.price) if r.price is not None else "—",
            "Action": action_label,
        })

    st.dataframe(pd.DataFrame(table_data), height=400, use_container_width=True)

    # Per-row controls for new rows (exclude toggles) and conflicts (radio)
    new_rows = [r for r in rows_to_show if r.status == RowStatus.NEW]
    conflict_rows = [r for r in rows_to_show if r.status == RowStatus.CONFLICT_WITH_MANUAL]

    if new_rows:
        with st.expander(f"Exclude rows from import ({len(new_rows)} new rows)", expanded=False):
            for r in new_rows:
                currently_excluded = r.reference in excludes
                label = f"Skip: {r.trade_date} · {r.proposed_ticker} · {r.description[:40]}"
                new_val = st.checkbox(label, value=currently_excluded, key=f"iw_excl_{r.reference}")
                if new_val and r.reference not in excludes:
                    excludes.add(r.reference)
                    st.session_state[_KEY_EXCLUDES] = excludes
                elif not new_val and r.reference in excludes:
                    excludes.discard(r.reference)
                    st.session_state[_KEY_EXCLUDES] = excludes

    if conflict_rows:
        with st.expander(f"Resolve conflicts ({len(conflict_rows)} rows)", expanded=True):
            for r in conflict_rows:
                current_choice = conflicts.get(r.reference, "replace")
                st.markdown(
                    f"**{r.trade_date}** · {r.proposed_ticker} · {r.description[:50]} "
                    f"(conflicts with manual tx `{r.conflict_tx_id}`)"
                )
                choice = st.radio(
                    "Action",
                    options=["replace", "keep", "skip"],
                    index=["replace", "keep", "skip"].index(current_choice),
                    key=f"iw_conflict_{r.reference}",
                    horizontal=True,
                    label_visibility="collapsed",
                )
                if choice != current_choice:
                    conflicts[r.reference] = choice
                    st.session_state[_KEY_CONFLICTS] = conflicts


def _render_isin_mapping_panel(plan: ImportPlan) -> None:
    unmapped_rows = [r for r in plan.rows if r.status == RowStatus.UNMAPPED_ISIN]
    if not unmapped_rows:
        return

    # Deduplicate by ISIN
    seen: set[str] = set()
    unique_unmapped: list[PlannedRow] = []
    for r in unmapped_rows:
        if r.isin not in seen:
            seen.add(r.isin)
            unique_unmapped.append(r)

    count_per_isin: dict[str, int] = {}
    for r in unmapped_rows:
        count_per_isin[r.isin] = count_per_isin.get(r.isin, 0) + 1

    st.subheader(f"ISINs needing mapping ({len(unique_unmapped)})")

    isin_repo = get_isin_map_repo()
    isin_doc = isin_repo.load()
    entries = dict(isin_doc.entries)
    saved_any = False

    for row in unique_unmapped:
        col1, col2, col3 = st.columns([0.3, 0.5, 0.2])
        with col1:
            st.code(row.isin)
            st.caption(f"{count_per_isin[row.isin]} transactions")
        with col2:
            st.write(row.description[:60])
            ticker_input = st.text_input(
                "Ticker",
                key=f"iw_map_{row.isin}",
                placeholder="e.g. SAP.DE",
                label_visibility="collapsed",
            )
        with col3:
            st.write("")
            if st.button("Save", key=f"iw_save_map_{row.isin}") and ticker_input.strip():
                entries[row.isin] = IsinMapping(
                    ticker=ticker_input.strip().upper(),
                    name=row.description,
                    status="mapped",
                    last_seen_in_csv=row.trade_date,
                )
                saved_any = True

    if saved_any:
        from app.domain.isin_map import IsinMapDocument
        isin_repo.save(IsinMapDocument(version=isin_doc.version, entries=entries))
        # Clear plan so it gets re-classified with new mappings
        st.session_state.pop(_KEY_PLAN, None)
        st.rerun()


def _render_apply_bar(
    plan: ImportPlan, portfolio_path: Path, backups_dir: Path, log_path: Path
) -> None:
    conflicts: dict[str, str] = st.session_state.get(_KEY_CONFLICTS, {})
    excludes: set[str] = st.session_state.get(_KEY_EXCLUDES, set())
    n_ready = _count_ready(plan, conflicts, excludes)
    n_conflicts = sum(1 for r in plan.rows if r.status == RowStatus.CONFLICT_WITH_MANUAL)
    n_blocked = sum(
        1 for r in plan.rows
        if r.status in (RowStatus.UNMAPPED_ISIN, RowStatus.NEEDS_CURRENCY_SUPPORT,
                        RowStatus.OUT_OF_SCOPE_V1, RowStatus.OUTGOING_TRANSFER,
                        RowStatus.CANCELLED_OR_EXPIRED, RowStatus.PARSE_ERROR)
    )

    st.divider()
    st.caption(
        f"{n_ready} rows ready to import · {n_conflicts} conflicts · {n_blocked} rows blocked"
    )
    st.caption(f"A backup of `portfolio.json` will be saved to `{backups_dir}/` before applying.")

    col1, col2 = st.columns([0.2, 0.8])
    with col1:
        apply_clicked = st.button(
            f"Apply {n_ready} changes to portfolio",
            disabled=n_ready == 0,
            type="primary",
            key="iw_apply_btn",
        )
    with col2:
        if st.button("Cancel", key="iw_cancel_btn"):
            _clear_state()
            st.rerun()

    if apply_clicked:
        _do_apply(plan, conflicts, excludes, portfolio_path, backups_dir, log_path)


def _do_apply(
    plan: ImportPlan,
    conflicts: dict[str, str],
    excludes: set[str],
    portfolio_path: Path,
    backups_dir: Path,
    log_path: Path,
) -> None:

    tx_repo = get_repository()
    file_bytes: bytes = st.session_state.get(_KEY_FILE_BYTES, b"")
    file_name: str = st.session_state.get(_KEY_FILE_NAME, "unknown.csv")

    # Step 1: write backup
    if portfolio_path.exists():
        bak = _write_backup(portfolio_path, backups_dir)
    else:
        bak = backups_dir / "no-backup-portfolio-did-not-exist.txt"

    to_insert: list[Transaction] = []
    to_delete: list[str] = []

    for row in plan.rows:
        if row.status == RowStatus.NEW:
            if row.reference not in excludes:
                tx = _build_transaction(row)
                if tx is not None:
                    to_insert.append(tx)

        elif row.status == RowStatus.CONFLICT_WITH_MANUAL:
            choice = conflicts.get(row.reference, "replace")
            if choice == "replace" and row.conflict_tx_id is not None:
                to_delete.append(row.conflict_tx_id)
                tx = _build_transaction(row)
                if tx is not None:
                    to_insert.append(tx)

    try:
        all_txs = tx_repo.load_all()
        # Remove conflicting manual transactions
        if to_delete:
            all_txs = [t for t in all_txs if t.id not in to_delete]
        all_txs.extend(to_insert)
        tx_repo.save_all(all_txs)
    except Exception as exc:
        st.error(f"Apply failed: {exc}. Your backup is at `{bak}`.")
        return

    # Append to import log
    _append_import_log(log_path, {
        "timestamp": datetime.now().isoformat(),
        "filename": file_name,
        "md5": _md5(file_bytes),
        "applied_count": len(to_insert),
        "conflict_count": len(to_delete),
    })

    applied = len(to_insert)
    st.success(f"Applied {applied} changes. Backup at `{bak}`.")
    _clear_state()
    st.rerun()


# ─── main render ──────────────────────────────────────────────────────────────

def render() -> None:
    from app.config import get_settings

    settings = get_settings()
    portfolio_path = Path(settings.portfolio_json_path)
    backups_dir = settings.backups_dir
    log_path = settings.import_log_json_path

    st.markdown("Upload your Scalable Capital CSV export to preview and apply transactions.")

    has_plan = _render_upload_section(log_path)
    if not has_plan:
        return

    rows: list[ParsedCsvRow] = st.session_state.get(_KEY_PARSED_ROWS, [])
    file_bytes: bytes = st.session_state.get(_KEY_FILE_BYTES, b"")
    file_name: str = st.session_state.get(_KEY_FILE_NAME, "")
    plan: ImportPlan = st.session_state[_KEY_PLAN]

    st.divider()
    _render_raw_preview(rows, file_bytes, file_name)

    st.divider()
    _render_planned_changes(plan)

    _render_isin_mapping_panel(plan)

    _render_apply_bar(plan, portfolio_path, backups_dir, log_path)
