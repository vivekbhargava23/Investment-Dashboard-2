# ruff: noqa: E501
"""Mappings page — ISIN → ticker resolution UI (TICKET-CSV-2)."""
from __future__ import annotations

import logging
import re
from typing import Any

import streamlit as st

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.services.isin_remap import count_transactions_for_isin, rewrite_ticker_for_isin
from app.ui.wiring import get_isin_map_repo, get_repository, get_ticker_resolver

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,29}$")

_STATE_DEFAULTS: dict[str, Any] = {
    "mappings_editing_isin": None,
    "mappings_edit_ticker_value": "",
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


def _save_mapping(isin: str, ticker: str, current_doc: IsinMapDocument) -> tuple[IsinMapDocument, str]:
    """Return (updated_doc, resolved_name_or_warning_note)."""
    existing = current_doc.entries.get(isin)
    updated_entry = IsinMapping(
        ticker=ticker,
        name=existing.name if existing else isin,
        status="mapped",
        last_seen_in_csv=existing.last_seen_in_csv if existing else None,
    )
    new_entries = dict(current_doc.entries)
    new_entries[isin] = updated_entry
    return IsinMapDocument(version=current_doc.version, entries=new_entries), updated_entry.name


def _delete_mapping(isin: str, current_doc: IsinMapDocument) -> IsinMapDocument:
    new_entries = {k: v for k, v in current_doc.entries.items() if k != isin}
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
        col_isin, col_name, col_input, col_btn = st.columns([2, 3, 2, 1])
        with col_isin:
            st.code(isin, language=None)
        with col_name:
            name = mapping.name or "—"
            if len(name) > 40:
                st.markdown(f'<span title="{name}">{name[:38]}…</span>', unsafe_allow_html=True)
            else:
                st.write(name)
        ticker_key = f"mappings_ticker_{isin}"
        with col_input:
            ticker_input = st.text_input(
                "Ticker",
                key=ticker_key,
                placeholder="e.g. NVDA, 5631.T",
                label_visibility="collapsed",
            )
        with col_btn:
            if st.button("Save", key=f"mappings_save_unmapped_{isin}"):
                raw = ticker_input.strip().upper()
                err = _validate_ticker(raw)
                if err:
                    st.session_state.mappings_feedback = ("error", f"{isin}: {err}")
                    st.rerun()
                else:
                    hint, warn = _try_resolve(raw)
                    updated_doc, _ = _save_mapping(isin, raw, doc)
                    get_isin_map_repo().save(updated_doc)
                    if hint:
                        msg = f"Mapped {isin} → {raw} ({hint})."
                    elif warn:
                        msg = f"Mapped {isin} → {raw}. Warning: {warn}"
                    else:
                        msg = f"Mapped {isin} → {raw}."
                    st.session_state.mappings_feedback = ("success", msg)
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

    header = st.columns([2, 3, 1.5, 1.5, 0.8, 0.8])
    for col, label in zip(header, ["ISIN", "Name", "Ticker", "Last seen", "", ""]):
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

        cols = st.columns([2, 3, 1.5, 1.5, 0.8, 0.8])
        cols[0].code(isin, language=None)
        cols[1].write(mapping.name or "—")
        cols[2].write(f"`{mapping.ticker}`")
        cols[3].write(mapping.last_seen_in_csv.isoformat() if mapping.last_seen_in_csv else "—")
        if cols[4].button("Edit", key=f"mappings_edit_{isin}"):
            st.session_state.mappings_editing_isin = isin
            st.session_state.mappings_edit_ticker_value = mapping.ticker or ""
            st.rerun()
        if cols[5].button("Delete", key=f"mappings_delete_{isin}"):
            st.session_state.mappings_confirming_delete_isin = isin
            st.rerun()


def _render_edit_row(isin: str, mapping: Any, doc: IsinMapDocument) -> None:
    cols = st.columns([2, 3, 1.5, 1.5, 0.8, 0.8])
    cols[0].code(isin, language=None)
    cols[1].write(mapping.name or "—")
    with cols[2]:
        new_ticker = st.text_input(
            "New ticker",
            value=st.session_state.mappings_edit_ticker_value,
            key=f"mappings_edit_input_{isin}",
            label_visibility="collapsed",
        )
    cols[3].write(mapping.last_seen_in_csv.isoformat() if mapping.last_seen_in_csv else "—")
    with cols[4]:
        if st.button("Save", key=f"mappings_edit_save_{isin}", type="primary"):
            raw = new_ticker.strip().upper()
            err = _validate_ticker(raw)
            if err:
                st.session_state.mappings_feedback = ("error", f"{isin}: {err}")
                st.rerun()
            else:
                hint, warn = _try_resolve(raw)
                updated_doc, _ = _save_mapping(isin, raw, doc)
                get_isin_map_repo().save(updated_doc)
                n = rewrite_ticker_for_isin(get_repository(), isin, raw)
                st.session_state.mappings_editing_isin = None
                if hint:
                    msg = f"Updated {isin} → {raw} ({hint}). Rewrote {n} transaction(s)."
                elif warn:
                    msg = f"Updated {isin} → {raw}. Warning: {warn}. Rewrote {n} transaction(s)."
                else:
                    msg = f"Updated {isin} → {raw}. Rewrote {n} transaction(s)."
                st.session_state.mappings_feedback = ("success", msg)
                st.rerun()
    with cols[5]:
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

    col_counts, col_refresh = st.columns([5, 1])
    with col_counts:
        st.caption(f"{len(mapped)} mapped · {len(unmapped)} unmapped")
    with col_refresh:
        if st.button("↺ Refresh", key="mappings_refresh"):
            st.rerun()

    if unmapped:
        st.divider()
        _render_unmapped_section(unmapped, doc)

    st.divider()
    _render_mapped_section(mapped, doc)

    st.divider()
    st.info(
        "ISINs are auto-added to this page when you run `tools/import_scalable_csv.py`. "
        "Re-run the importer after mapping new ISINs to pull in their transactions."
    )
