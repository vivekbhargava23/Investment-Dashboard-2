# ruff: noqa: E501
"""Mappings page — ISIN → ticker resolution UI (TICKET-CSV-2)."""
from __future__ import annotations

import html
import logging
import re
from typing import Any

import streamlit as st

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.tax.classification import InstrumentKind
from app.ports.ticker_resolver import TickerMatch
from app.services.isin_remap import count_transactions_for_isin, rewrite_ticker_for_isin
from app.ui.components.isin_mapper import KIND_LABEL, KIND_OPTIONS, suggest_kind
from app.ui.components.ticker_searchbox import render_ticker_searchbox
from app.ui.wiring import (
    get_isin_map_repo,
    get_repository,
    get_ticker_resolver,
)

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,29}$")

_STATE_DEFAULTS: dict[str, Any] = {
    "mappings_editing_isin": None,
    "mappings_confirming_delete_isin": None,
    "mappings_feedback": None,
}


def _init_state(state: Any) -> None:
    for key, default in _STATE_DEFAULTS.items():
        if key not in state:
            state[key] = default


def _validate_ticker(ticker: str) -> str | None:
    """Return an error message, or None if valid."""
    t = ticker.strip()
    if not t:
        return "Ticker cannot be empty."
    if not _TICKER_RE.match(t):
        return "Ticker must be uppercase letters, digits, dot, or dash (e.g. NVDA, VUAA.DE, 5631.T)."
    return None


def _save_mapping(isin: str, ticker: str, kind: InstrumentKind | None, current_doc: IsinMapDocument) -> tuple[IsinMapDocument, str]:
    """Return (updated_doc, resolved_name_or_warning_note)."""
    existing = current_doc.entries.get(isin)
    updated_entry = IsinMapping(
        ticker=ticker,
        name=existing.name if existing else isin,
        status="mapped",
        last_seen_in_csv=existing.last_seen_in_csv if existing else None,
        instrument_kind=kind,
    )
    new_entries = dict(current_doc.entries)
    new_entries[isin] = updated_entry
    return IsinMapDocument(version=current_doc.version, entries=new_entries), updated_entry.name


def _delete_mapping(isin: str, current_doc: IsinMapDocument) -> IsinMapDocument:
    new_entries = {k: v for k, v in current_doc.entries.items() if k != isin}
    return IsinMapDocument(version=current_doc.version, entries=new_entries)


def _ignore_isin(isin: str, current_doc: IsinMapDocument) -> IsinMapDocument:
    new_entries = dict(current_doc.entries)
    mapping = new_entries[isin]
    # instrument_kind is kept on the entry; it will be cleared if the user later restores
    new_entries[isin] = mapping.model_copy(update={"status": "ignored"})
    return IsinMapDocument(version=current_doc.version, entries=new_entries)


def _restore_isin(isin: str, current_doc: IsinMapDocument) -> IsinMapDocument:
    new_entries = dict(current_doc.entries)
    mapping = new_entries[isin]
    new_entries[isin] = mapping.model_copy(update={"status": "unmapped", "instrument_kind": None})
    return IsinMapDocument(version=current_doc.version, entries=new_entries)


def _try_resolve(ticker: str) -> tuple[str | None, str | None]:
    """Return (display_hint, warning). display_hint is None on failure."""
    resolver = get_ticker_resolver()
    try:
        match = resolver.lookup(ticker)
        if match:
            return f"{match.name} · {match.exchange} · {match.currency.value}", None
        return None, "Ticker not recognized by yfinance — saved anyway, but live prices may not work."
    except Exception:
        logging.warning("Ticker resolver error for %s", ticker, exc_info=True)
        return None, "Resolver offline — saved anyway, but live prices may not work."


# ---------------------------------------------------------------------------
# Unmapped section
# ---------------------------------------------------------------------------

def _render_unmapped_section(
    unmapped: dict[str, Any],
    doc: IsinMapDocument,
) -> None:
    st.subheader("Unmapped ISINs")
    st.caption("These ISINs were seen in your CSV but have no ticker assigned. Transactions for these ISINs were skipped.")

    for isin, mapping in unmapped.items():
        col_isin, col_name, col_ticker, col_kind, col_btn, col_ignore = st.columns([2, 2, 2, 2, 0.7, 0.7])
        with col_isin:
            st.code(isin, language=None)
        with col_name:
            name = mapping.name or "—"
            if len(name) > 40:
                # Data-derived name → escape before HTML interpolation (title attr + text).
                full_safe = html.escape(name)
                truncated_safe = html.escape(name[:38])
                st.markdown(f'<span title="{full_safe}">{truncated_safe}…</span>', unsafe_allow_html=True)
            else:
                st.write(name)
        with col_ticker:
            selected_match: TickerMatch | None = render_ticker_searchbox(
                key=f"mappings_searchbox_unmapped_{isin}",
                resolver=get_ticker_resolver(),
                placeholder=f"Search for {mapping.name or 'this security'}…",
            )
        with col_kind:
            suggested = suggest_kind(selected_match.symbol) if selected_match else None
            kind_options_with_none: list[InstrumentKind | None] = [None] + KIND_OPTIONS
            kind_index = kind_options_with_none.index(suggested) if suggested else 0
            selected_kind = st.selectbox(
                "Tax kind",
                options=kind_options_with_none,
                index=kind_index,
                format_func=lambda k: "— pick a kind —" if k is None else KIND_LABEL.get(k, str(k)),
                key=f"mappings_kind_unmapped_{isin}",
                label_visibility="collapsed",
            )
        with col_btn:
            save_disabled = selected_match is None or selected_kind is None
            if st.button("Save", key=f"mappings_save_unmapped_{isin}", disabled=save_disabled):
                if selected_match is None:
                    st.session_state.mappings_feedback = ("error", f"{isin}: Pick a ticker from the search results before saving.")
                    st.rerun()
                elif selected_kind is None:
                    st.session_state.mappings_feedback = ("error", f"{isin}: Pick a Tax kind before saving.")
                    st.rerun()
                else:
                    raw = selected_match.symbol
                    err = _validate_ticker(raw)
                    if err:
                        st.session_state.mappings_feedback = ("error", f"{isin}: {err}")
                        st.rerun()
                    else:
                        hint, warn = _try_resolve(raw)
                        updated_doc, _ = _save_mapping(isin, raw, selected_kind, doc)
                        get_isin_map_repo().save(updated_doc)
                        if hint:
                            msg = f"Mapped {isin} → {raw} ({hint}), Tax kind: {KIND_LABEL.get(selected_kind, selected_kind)}."
                        elif warn:
                            msg = f"Mapped {isin} → {raw}. Warning: {warn}. Tax kind: {KIND_LABEL.get(selected_kind, selected_kind)}."
                        else:
                            msg = f"Mapped {isin} → {raw}, Tax kind: {KIND_LABEL.get(selected_kind, selected_kind)}."
                        st.session_state.mappings_feedback = ("success", msg)
                        st.rerun()
        with col_ignore:
            if st.button("Ignore", key=f"mappings_ignore_unmapped_{isin}"):
                updated_doc = _ignore_isin(isin, doc)
                get_isin_map_repo().save(updated_doc)
                st.session_state.mappings_feedback = ("success", f"Ignored {isin} ({mapping.name}). Future CSV rows for this ISIN will be skipped silently.")
                st.rerun()


# ---------------------------------------------------------------------------
# Ignored section
# ---------------------------------------------------------------------------

def _render_ignored_section(
    ignored: dict[str, Any],
    doc: IsinMapDocument,
) -> None:
    with st.expander("Ignored ISINs", expanded=False):
        st.caption("These ISINs were intentionally ignored. CSV rows for them are skipped silently. Click Restore to move one back to Unmapped.")
        for isin, mapping in ignored.items():
            col_isin, col_name, col_last_seen, col_btn = st.columns([2, 3, 2, 1])
            with col_isin:
                st.code(isin, language=None)
            with col_name:
                st.write(mapping.name or "—")
            with col_last_seen:
                st.write(mapping.last_seen_in_csv.isoformat() if mapping.last_seen_in_csv else "—")
            with col_btn:
                if st.button("Restore", key=f"mappings_restore_ignored_{isin}"):
                    updated_doc = _restore_isin(isin, doc)
                    get_isin_map_repo().save(updated_doc)
                    st.session_state.mappings_feedback = ("success", f"Restored {isin} ({mapping.name}) to Unmapped.")
                    st.rerun()


# ---------------------------------------------------------------------------
# Mapped section
# ---------------------------------------------------------------------------

def _render_mapped_section(
    mapped: dict[str, Any],
    doc: IsinMapDocument,
) -> None:
    st.subheader("Mapped ISINs")
    if not mapped:
        st.info("No mapped ISINs yet.")
        return

    header = st.columns([2, 2.5, 1.2, 1.2, 1.2, 0.7, 0.7])
    for col, label in zip(header, ["ISIN", "Name", "Ticker", "Tax kind", "Last seen", "", ""]):
        col.markdown(f"**{label}**")

    editing_isin = st.session_state.mappings_editing_isin
    confirming_isin = st.session_state.mappings_confirming_delete_isin

    for isin, mapping in mapped.items():
        if isin == confirming_isin:
            _render_delete_confirmation(isin, mapping, doc)
            continue

        if isin == editing_isin:
            _render_edit_row(isin, mapping, doc)
            continue

        cols = st.columns([2, 2.5, 1.2, 1.2, 1.2, 0.7, 0.7])
        cols[0].code(isin, language=None)
        cols[1].write(mapping.name or "—")
        cols[2].write(f"`{mapping.ticker}`")
        if mapping.instrument_kind is not None:
            cols[3].write(KIND_LABEL.get(mapping.instrument_kind, mapping.instrument_kind.value))
        else:
            cols[3].markdown("⚠ **unset**")
        cols[4].write(mapping.last_seen_in_csv.isoformat() if mapping.last_seen_in_csv else "—")
        if cols[5].button("Edit", key=f"mappings_edit_{isin}"):
            st.session_state.mappings_editing_isin = isin
            st.rerun()
        if cols[6].button("Delete", key=f"mappings_delete_{isin}"):
            st.session_state.mappings_confirming_delete_isin = isin
            st.rerun()


def _render_edit_row(isin: str, mapping: Any, doc: IsinMapDocument) -> None:
    cols = st.columns([2, 2.5, 1.2, 1.2, 1.2, 0.7, 0.7])
    cols[0].code(isin, language=None)
    cols[1].write(mapping.name or "—")
    with cols[2]:
        default_match: TickerMatch | None = None
        if mapping.ticker:
            try:
                default_match = get_ticker_resolver().lookup(mapping.ticker)
            except Exception:
                default_match = None
        selected_match: TickerMatch | None = render_ticker_searchbox(
            key=f"mappings_edit_searchbox_{isin}",
            resolver=get_ticker_resolver(),
            placeholder="Search by ticker or name…",
            default_match=default_match,
        )
    with cols[3]:
        suggested = suggest_kind(selected_match.symbol) if selected_match and selected_match.symbol != (mapping.ticker or "") else mapping.instrument_kind
        kind_options_with_none: list[InstrumentKind | None] = [None] + KIND_OPTIONS
        kind_index = kind_options_with_none.index(suggested) if suggested in kind_options_with_none else 0
        selected_kind = st.selectbox(
            "Tax kind",
            options=kind_options_with_none,
            index=kind_index,
            format_func=lambda k: "— pick a kind —" if k is None else KIND_LABEL.get(k, str(k)),
            key=f"mappings_edit_kind_{isin}",
            label_visibility="collapsed",
        )
    cols[4].write(mapping.last_seen_in_csv.isoformat() if mapping.last_seen_in_csv else "—")
    with cols[5]:
        save_disabled = selected_match is None or selected_kind is None
        if st.button("Save", key=f"mappings_edit_save_{isin}", type="primary", disabled=save_disabled):
            if selected_match is None:
                st.session_state.mappings_feedback = ("error", f"{isin}: Pick a ticker from the search results before saving.")
                st.rerun()
            elif selected_kind is None:
                st.session_state.mappings_feedback = ("error", f"{isin}: Pick a Tax kind before saving.")
                st.rerun()
            else:
                raw = selected_match.symbol
                err = _validate_ticker(raw)
                if err:
                    st.session_state.mappings_feedback = ("error", f"{isin}: {err}")
                    st.rerun()
                else:
                    hint, warn = _try_resolve(raw)
                    updated_doc, _ = _save_mapping(isin, raw, selected_kind, doc)
                    get_isin_map_repo().save(updated_doc)
                    n = rewrite_ticker_for_isin(get_repository(), isin, raw)
                    st.session_state.mappings_editing_isin = None
                    if hint:
                        msg = f"Updated {isin} → {raw} ({hint}), Tax kind: {KIND_LABEL.get(selected_kind, selected_kind)}. Rewrote {n} transaction(s)."
                    elif warn:
                        msg = f"Updated {isin} → {raw}. Warning: {warn}. Tax kind: {KIND_LABEL.get(selected_kind, selected_kind)}. Rewrote {n} transaction(s)."
                    else:
                        msg = f"Updated {isin} → {raw}, Tax kind: {KIND_LABEL.get(selected_kind, selected_kind)}. Rewrote {n} transaction(s)."
                    st.session_state.mappings_feedback = ("success", msg)
                    st.rerun()
    with cols[6]:
        if st.button("Cancel", key=f"mappings_edit_cancel_{isin}"):
            st.session_state.mappings_editing_isin = None
            st.rerun()


def _render_delete_confirmation(isin: str, mapping: Any, doc: IsinMapDocument) -> None:
    cols = st.columns([5, 0.8, 0.8])
    with cols[0]:
        st.warning(f"Delete mapping for {isin} ({mapping.name}, ticker: {mapping.ticker})?")
    with cols[1]:
        if st.button("Yes", key=f"mappings_confirm_delete_{isin}", type="primary"):
            n = count_transactions_for_isin(get_repository(), isin)
            if n > 0:
                st.session_state.mappings_confirming_delete_isin = None
                st.session_state.mappings_feedback = (
                    "error",
                    f"Cannot delete {isin}: {n} transaction(s) still reference it. "
                    "Delete those transactions first or remap to a different ticker.",
                )
                st.rerun()
            updated_doc = _delete_mapping(isin, doc)
            get_isin_map_repo().save(updated_doc)
            st.session_state.mappings_confirming_delete_isin = None
            st.session_state.mappings_feedback = ("success", f"Deleted mapping for {isin}.")
            st.rerun()
    with cols[2]:
        if st.button("Cancel", key=f"mappings_cancel_delete_{isin}"):
            st.session_state.mappings_confirming_delete_isin = None
            st.rerun()


# ---------------------------------------------------------------------------
# Page entry point
# ---------------------------------------------------------------------------

def render() -> None:
    _init_state(st.session_state)

    st.title("ISIN Mappings")

    feedback = st.session_state.mappings_feedback
    if feedback:
        level, msg = feedback
        if level == "success":
            st.success(msg)
        elif level == "warning":
            st.warning(msg)
        else:
            st.error(msg)
        st.session_state.mappings_feedback = None

    try:
        doc = get_isin_map_repo().load()
    except Exception as exc:
        st.error(f"Could not load isin_map.json: {exc}")
        return

    unmapped = {isin: m for isin, m in doc.entries.items() if m.status == "unmapped"}
    mapped = {isin: m for isin, m in doc.entries.items() if m.status == "mapped"}
    ignored = {isin: m for isin, m in doc.entries.items() if m.status == "ignored"}

    col_counts, col_refresh = st.columns([5, 1])
    with col_counts:
        unclassified = sum(1 for m in mapped.values() if m.instrument_kind is None)
        caption = f"{len(mapped)} mapped · {len(unmapped)} unmapped"
        if ignored:
            caption += f" · {len(ignored)} ignored"
        if unclassified:
            caption += f" · ⚠ {unclassified} missing Tax kind"
        st.caption(caption)
    with col_refresh:
        if st.button("↺ Refresh", key="mappings_refresh"):
            st.rerun()

    if unmapped:
        st.divider()
        _render_unmapped_section(unmapped, doc)

    if ignored:
        st.divider()
        _render_ignored_section(ignored, doc)

    st.divider()
    _render_mapped_section(mapped, doc)
