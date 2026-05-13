from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

import plotly.graph_objects as go
import streamlit as st

from app.ports.company_data import CompanyDataError
from app.services.company import get_company, refresh_company_section
from app.ui.components.chart_theme import (
    CHART_STYLE_PRESETS,
    ChartStyle,
    apply_style,
    styled_bar_trace,
    styled_line_trace,
)
from app.ui.components.ticker_searchbox import render_ticker_searchbox
from app.ui.format import format_relative_time
from app.ui.wiring import get_company_provider, get_ticker_resolver

_COMPANY_CACHE_ROOT = Path("data/companies")
_SECTIONS: tuple[Literal["profile", "prices", "financials"], ...] = (
    "profile",
    "prices",
    "financials",
)


def _recent_cached_tickers(cache_root: Path = _COMPANY_CACHE_ROOT) -> list[str]:
    if not cache_root.exists():
        return []

    rows: list[tuple[datetime, str]] = []
    for ticker_dir in cache_root.iterdir():
        profile_path = ticker_dir / "profile.json"
        if not ticker_dir.is_dir() or not profile_path.exists():
            continue
        try:
            envelope = json.loads(profile_path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(envelope["fetched_at"])
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        rows.append((fetched_at, ticker_dir.name.upper()))

    rows.sort(reverse=True)
    return [ticker for _, ticker in rows[:5]]


def _render_recent_tickers() -> str | None:
    tickers = _recent_cached_tickers()
    if not tickers:
        return None

    st.caption("Recent")
    columns = st.columns(len(tickers))
    selected: str | None = None
    for column, ticker in zip(columns, tickers, strict=True):
        with column:
            if st.button(ticker, key=f"company_recent_{ticker}", use_container_width=True):
                selected = ticker
    return selected


def _cache_age_line(data_time: str, profile_age: str, prices_age: str, financials_age: str) -> str:
    return (
        f"Data as of {data_time} · "
        f"Profile {profile_age} · Prices {prices_age} · Financials {financials_age}"
    )


def _format_data_time(dt: datetime | None) -> str:
    if dt is None:
        return "unknown"
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def _render_company_cache_banner(data: object) -> None:
    profile_fetched_at = getattr(data, "profile_fetched_at")
    prices_fetched_at = getattr(data, "prices_fetched_at")
    financials_fetched_at = getattr(data, "financials_fetched_at")
    latest = max(
        (dt for dt in (profile_fetched_at, prices_fetched_at, financials_fetched_at) if dt),
        default=None,
    )
    st.caption(
        _cache_age_line(
            _format_data_time(latest),
            format_relative_time(profile_fetched_at),
            format_relative_time(prices_fetched_at),
            format_relative_time(financials_fetched_at),
        )
    )


def _refresh_all_sections(ticker: str) -> None:
    provider = get_company_provider()
    for section in _SECTIONS:
        refresh_company_section(ticker, section, provider=provider)


def _sample_chart(style: ChartStyle) -> go.Figure:
    quarters = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9", "Q10", "Q11", "Q12"]
    revenue = [91, 95, 102, 107, 112, 118, 126, 132, 141, 148, 157, 166]
    margin = [18, 19, 19, 20, 21, 20, 22, 23, 23, 24, 25, 26]

    fig = go.Figure()
    fig.add_trace(styled_bar_trace(style, 0, x=quarters, y=revenue, name="Revenue"))
    fig.add_trace(
        styled_line_trace(
            style,
            1,
            x=quarters,
            y=margin,
            name="Margin",
            yaxis="y2",
        )
    )
    fig.update_layout(
        height=250,
        yaxis={"title": None},
        yaxis2={
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
            "title": None,
            "tickfont": {"color": style.text_color, "size": style.font_size},
        },
    )
    return apply_style(fig, style)


def _render_chart_style_sampler() -> None:
    st.info(
        "Pick a chart style during PR review. The chosen style will be applied across all "
        "Company Deep Dive tabs. The sampler will be removed in TICKET-027."
    )
    columns = st.columns(3)
    for column, style in zip(columns, CHART_STYLE_PRESETS, strict=True):
        with column:
            st.plotly_chart(_sample_chart(style), use_container_width=True)
            st.markdown(f"**{style.name}**")
            st.caption(style.description)


def render() -> None:
    title_col, refresh_col = st.columns([0.78, 0.22])
    with title_col:
        st.title("Company Deep Dive")

    selected_ticker = st.session_state.get("company_selected_ticker")
    with refresh_col:
        if st.button("🔄 Refresh", key="company_refresh", use_container_width=True):
            if selected_ticker:
                _refresh_all_sections(str(selected_ticker))
                st.rerun()

    match = render_ticker_searchbox(
        "company_ticker",
        get_ticker_resolver(),
        placeholder="Search by ticker or company name...",
    )
    if match is not None:
        selected_ticker = match.symbol.upper()
        st.session_state["company_selected_ticker"] = selected_ticker

    recent_ticker = _render_recent_tickers()
    if recent_ticker is not None:
        selected_ticker = recent_ticker
        st.session_state["company_selected_ticker"] = selected_ticker

    if not selected_ticker:
        st.info("Search for a company to load the deep dive shell.")
        return

    provider = get_company_provider()
    try:
        with st.spinner("Loading company data..."):
            data = get_company(str(selected_ticker), provider=provider)
    except CompanyDataError as exc:
        st.error(str(exc))
        return

    _render_company_cache_banner(data)
    for section, error in data.fetch_errors.items():
        st.warning(f"{section}: {error}")

    tabs = st.tabs(
        [
            "Snapshot",
            "Business",
            "Financials",
            "Valuation",
            "Capital & Owners",
            "Risk & Thesis",
        ]
    )

    with tabs[0]:
        st.write("Snapshot content — TICKET-027")
        _render_chart_style_sampler()
    with tabs[1]:
        st.info(
            "📋 Business tab coming soon — waiting for segment data sources and Panel framework."
        )
        st.write(
            "Will include: revenue by segment, revenue by geography, customer concentration, "
            "moat notes, peer set."
        )
    with tabs[2]:
        st.write("Financials content — TICKET-028")
    with tabs[3]:
        st.write("Valuation content — TICKET-029")
    with tabs[4]:
        st.write("Capital & Ownership content — TICKET-030")
    with tabs[5]:
        st.info("📋 Risk & Thesis tab coming soon — waiting for Panel framework.")
        st.write(
            "Will include: beta, volatility, max drawdown, FX exposure, leverage stress test, "
            "conviction tracker, decision log."
        )
