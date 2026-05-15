from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

import plotly.graph_objects as go
import streamlit as st

from app.domain.company import CompanyData
from app.ports.company_data import CompanyDataError
from app.services.company import get_company, refresh_company_section
from app.ui.components.chart_theme import (
    DEFAULT_STYLE,
    ChartStyle,
    apply_style,
    get_accent_color,
    styled_line_trace,
)
from app.ui.components.ticker_searchbox import render_ticker_searchbox
from app.ui.format import format_multiple, format_pct, format_relative_time
from app.ui.pages._snapshot_helpers import (
    compute_ebit_margin,
    compute_ebit_margin_series,
    compute_fcf_series,
    compute_fcf_yield,
    compute_historical_pe_range,
    compute_net_debt_ebitda,
    compute_net_debt_ebitda_series,
    compute_revenue_cagr,
    compute_revenue_series,
    compute_sma,
    filter_price_history,
)
from app.ui.render import render_html
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


_PERIOD_YEARS = {"1Y": 1, "3Y": 3, "5Y": 5}


def _render_snapshot_header(data: CompanyData) -> None:
    profile = data.profile
    quote = data.latest_quote

    left, right, star_col = st.columns([0.55, 0.35, 0.10])

    with left:
        if profile is None:
            st.warning("Company data unavailable")
        else:
            render_html(f"<h2 style='margin:0'>{profile.name}</h2>")
            isin_text = f" · ISIN {profile.isin}" if profile.isin else ""
            render_html(
                f"<p style='margin:0;font-size:1rem;font-weight:600'>"
                f"{profile.ticker}{isin_text}</p>"
            )
            parts = [p for p in (profile.sector, profile.industry, profile.country) if p]
            if parts:
                st.caption(" · ".join(parts))

    with right:
        if quote is None:
            st.warning("Price unavailable")
        else:
            currency = quote.price.currency
            price_val = float(quote.price.amount)
            st.metric(
                label=f"{currency}",
                value=f"{price_val:,.2f}",
                delta=format_pct(quote.day_change_pct, signed=True),
            )
            if profile:
                st.caption(f"{profile.country or ''} · {currency}")

    with star_col:
        st.button("⭐", disabled=True, help="Watchlist — coming in TICKET-031", key="snapshot_star")


def _mini_sparkline(values: list[Decimal | None], style: ChartStyle) -> go.Figure:
    """Small inline trend line, no axes, no labels."""
    y = [float(v) if v is not None else None for v in values]
    x = list(range(len(y)))
    fig = go.Figure(
        data=[
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                line={"color": get_accent_color(style, 0), "width": 1.5},
                connectgaps=True,
            )
        ]
    )
    fig.update_layout(
        height=40,
        width=120,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _render_price_chart(data: CompanyData, period_label: str) -> None:
    years = _PERIOD_YEARS.get(period_label, 5)
    history = filter_price_history(data.price_history, years)

    if not history:
        st.warning("Price history unavailable")
        return

    dates = [p.date for p in history]
    closes = [p.close for p in history]

    sma_period = 200 if len(closes) >= 200 else (50 if len(closes) >= 50 else None)
    sma_values = compute_sma(closes, sma_period) if sma_period else None
    sma_label = f"{sma_period}DMA" if sma_period else None

    fig = go.Figure()
    fig.add_trace(
        styled_line_trace(
            DEFAULT_STYLE,
            0,
            x=dates,
            y=[float(c) for c in closes],
            name="Price",
            mode="lines",
        )
    )
    if sma_values and sma_label:
        fig.add_trace(
            styled_line_trace(
                DEFAULT_STYLE,
                1,
                x=dates,
                y=[float(v) if v is not None else None for v in sma_values],
                name=sma_label,
                mode="lines",
                connectgaps=False,
            )
        )
    currency = data.profile.currency if data.profile else "?"
    fig.update_layout(
        height=400,
        showlegend=True,
        legend={"orientation": "h", "y": -0.15},
        yaxis={"title": currency},
    )
    apply_style(fig, DEFAULT_STYLE)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with st.expander("Show data"):
        rows = [
            {"Date": p.date.isoformat(), "Close": float(p.close), "Volume": p.volume}
            for p in history
        ]
        st.dataframe(rows, use_container_width=True)


def _render_kpi_tiles(data: CompanyData) -> None:
    cols = st.columns(4)
    quarters = data.quarterly_fundamentals
    market_cap_amount = (
        data.profile.market_cap.amount
        if (data.profile and data.profile.market_cap)
        else None
    )

    with cols[0]:
        cagr, cagr_label = compute_revenue_cagr(quarters)
        rev_series = compute_revenue_series(quarters)
        if cagr is not None:
            color = "green" if cagr >= 0 else "red"
            render_html(
                f"<b style='font-size:1.3rem;color:{color}'>{format_pct(cagr, signed=True)}</b>"
            )
            st.caption(f"Revenue Growth ({cagr_label})")
        else:
            st.markdown("**N/A**")
            st.caption("Revenue data unavailable")
        spark_vals = [v for v in rev_series if v is not None]
        if len(spark_vals) >= 2:
            st.plotly_chart(
                _mini_sparkline([v for v in rev_series], DEFAULT_STYLE),
                use_container_width=False,
                config={"displayModeBar": False},
            )

    with cols[1]:
        margin = compute_ebit_margin(quarters)
        margin_series = compute_ebit_margin_series(quarters)
        if margin is not None:
            render_html(f"<b style='font-size:1.3rem'>{format_pct(margin)}</b>")
            st.caption("EBIT Margin (latest quarter)")
        else:
            st.markdown("**N/A**")
            st.caption("EBIT data unavailable")
        if any(v is not None for v in margin_series):
            st.plotly_chart(
                _mini_sparkline(margin_series, DEFAULT_STYLE),
                use_container_width=False,
                config={"displayModeBar": False},
            )

    with cols[2]:
        nd_ebitda = compute_net_debt_ebitda(quarters)
        nd_series = compute_net_debt_ebitda_series(quarters)
        if nd_ebitda is not None:
            if nd_ebitda < 2:
                color = "green"
            elif nd_ebitda <= 3:
                color = "orange"
            else:
                color = "red"
            render_html(
                f"<b style='font-size:1.3rem;color:{color}'>{format_multiple(nd_ebitda)}</b>"
            )
            st.caption("Net Debt / EBITDA")
        else:
            st.markdown("**N/A**")
            st.caption("ND/EBITDA unavailable")
        if any(v is not None for v in nd_series):
            st.plotly_chart(
                _mini_sparkline(nd_series, DEFAULT_STYLE),
                use_container_width=False,
                config={"displayModeBar": False},
            )

    with cols[3]:
        fcf_yield_val = compute_fcf_yield(quarters, market_cap_amount)
        fcf_series = compute_fcf_series(quarters)
        if fcf_yield_val is not None:
            render_html(f"<b style='font-size:1.3rem'>{format_pct(fcf_yield_val)}</b>")
            st.caption("FCF Yield (TTM)")
        else:
            st.markdown("**N/A**")
            st.caption("FCF yield unavailable")
        if any(v is not None for v in fcf_series):
            st.plotly_chart(
                _mini_sparkline(fcf_series, DEFAULT_STYLE),
                use_container_width=False,
                config={"displayModeBar": False},
            )


def _render_valuation_band(data: CompanyData) -> None:
    quarters = data.quarterly_fundamentals
    current_pe_from_multiples = (
        data.current_multiples.pe_trailing if data.current_multiples else None
    )

    pe_range = compute_historical_pe_range(quarters, data.price_history)

    if pe_range is None:
        st.caption("Valuation band unavailable — insufficient earnings data")
        return

    min_pe, current_pe, max_pe = pe_range

    if current_pe <= 0:
        st.caption("P/E not meaningful — company is loss-making")
        return

    if current_pe_from_multiples is not None and current_pe_from_multiples <= 0:
        st.caption("P/E not meaningful — company is loss-making")
        return

    display_pe = current_pe_from_multiples if current_pe_from_multiples is not None else current_pe

    pe_range_width = max_pe - min_pe
    if pe_range_width <= 0:
        st.caption("Valuation band unavailable — P/E range is flat")
        return

    n_segments = 20
    fig = go.Figure()

    for i in range(n_segments):
        x0 = float(min_pe) + float(pe_range_width) * i / n_segments
        x1 = float(min_pe) + float(pe_range_width) * (i + 1) / n_segments
        frac = i / n_segments
        r = int(frac * 200)
        g = int((1 - frac) * 160)
        fig.add_shape(
            type="rect",
            xref="x", yref="paper",
            x0=x0, x1=x1, y0=0, y1=1,
            fillcolor=f"rgb({r},{g},60)",
            opacity=0.35,
            line_width=0,
        )

    fig.add_trace(
        go.Scatter(
            x=[float(display_pe)],
            y=[0],
            mode="markers+text",
            marker={"size": 14, "color": "white", "line": {"color": "#333", "width": 2}},
            text=[f"{float(display_pe):.1f}x"],
            textposition="top center",
            hovertemplate=f"Current P/E: {float(display_pe):.1f}x<extra></extra>",
        )
    )

    fig.update_layout(
        height=90,
        margin={"l": 10, "r": 10, "t": 20, "b": 30},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis={
            "range": [float(min_pe) - float(pe_range_width) * 0.05,
                      float(max_pe) + float(pe_range_width) * 0.05],
            "tickvals": [float(min_pe), float(display_pe), float(max_pe)],
            "ticktext": [
                f"{float(min_pe):.1f}x",
                f"{float(display_pe):.1f}x",
                f"{float(max_pe):.1f}x",
            ],
            "showgrid": False,
            "zeroline": False,
            "tickfont": {"size": 10},
        },
        yaxis={"visible": False, "range": [-0.5, 0.5]},
    )
    st.markdown("**Valuation Band — Trailing P/E (5Y range)**")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_next_catalyst(data: CompanyData, today: date) -> None:
    catalyst = data.next_catalyst
    if catalyst is None:
        st.caption("No upcoming catalyst data available")
        return

    days_until = (catalyst.date - today).days
    kind_label = catalyst.kind.replace("_", " ").title()
    detail = f" · {catalyst.detail}" if catalyst.detail else ""
    countdown = f"in {days_until} days" if days_until >= 0 else f"{abs(days_until)} days ago"
    render_html(
        f"<div style='padding:8px 12px;border-left:3px solid #4f6f8f;margin:4px 0'>"
        f"<b>📅 {kind_label}</b>{detail} · {catalyst.date.strftime('%b %d, %Y')} · {countdown}"
        f"</div>"
    )


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
        _render_snapshot_header(data)
        st.divider()

        period_options = list(_PERIOD_YEARS.keys())
        selected_period = st.radio(
            "Period",
            period_options,
            index=period_options.index("5Y"),
            horizontal=True,
            key="snapshot_price_period",
            label_visibility="collapsed",
        )
        _render_price_chart(data, str(selected_period))
        st.divider()

        _render_kpi_tiles(data)
        st.divider()

        _render_valuation_band(data)
        st.divider()

        _render_next_catalyst(data, datetime.now(UTC).date())
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
