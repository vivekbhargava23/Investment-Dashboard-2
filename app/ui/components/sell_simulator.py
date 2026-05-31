# ruff: noqa: E501
"""Embeddable pre-trade sell simulator panel.

Renders a form that previews the impact of a hypothetical sell (FIFO lots,
realised gain, marginal tax, position change) without writing any data.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

import streamlit as st

from app.domain.money import Currency, Money
from app.domain.tax.classification import InstrumentClassificationError
from app.domain.tax.models import TaxProfile
from app.ports.tax_profile_repo import TaxProfileDocument
from app.services.sell_simulator import (
    SellSimulation,
    SellSimulationRequest,
    simulate_sell,
)
from app.services.valuation import get_live_positions_cached
from app.ui.format import format_date, format_eur, gain_class
from app.ui.render import render_html
from app.ui.wiring import (
    get_fx_provider,
    get_isin_map_repo,
    get_price_provider,
    get_repository,
    get_tax_profile_repo,
    get_ticker_resolver,
)


@st.cache_data(ttl=3600, show_spinner=False)
def _build_ticker_labels(tickers: tuple[str, ...]) -> dict[str, str]:
    """Map ticker symbols to 'TICKER — Company Name' display strings.

    Uses resolver.resolve() (yf.Search, ~150ms/ticker) rather than resolver.lookup()
    (yf.Ticker.info, ~800ms/ticker).  Cached at the Streamlit layer for 1 hour so
    the network calls happen at most once per session — all subsequent renders are instant.
    """
    resolver = get_ticker_resolver()
    labels: dict[str, str] = {}
    for t in tickers:
        try:
            matches = resolver.resolve(t, limit=5)
            name = next((m.name for m in matches if m.symbol.upper() == t.upper()), "")
            labels[t] = f"{t} — {name}" if name else t
        except Exception:
            labels[t] = t
    return labels


_EUR = Currency.EUR
_logger = logging.getLogger(__name__)


def _load_tax_context(year: int) -> tuple[TaxProfile, Money, Money, Money, Money]:
    """Load tax profile and carryforward inputs, falling back to zero on error."""
    _ZERO = Money.zero(_EUR)
    try:
        doc: TaxProfileDocument = get_tax_profile_repo().load()
        inputs = doc.inputs_for_year(year)
        return (
            TaxProfile(filing_status=doc.filing_status),
            inputs.carryforward_aktien_eur,
            inputs.carryforward_general_eur,
            inputs.additional_dividend_income_eur,
            inputs.additional_interest_income_eur,
        )
    except Exception:
        from app.domain.tax.models import FilingStatus
        return TaxProfile(filing_status=FilingStatus.SINGLE), _ZERO, _ZERO, _ZERO, _ZERO


def _render_lot_table(sim: SellSimulation) -> None:
    rows = ""
    for row in sim.lot_consumption:
        g_cls = gain_class(row.realised_gain_eur.amount)
        rows += (
            f"<tr>"
            f"<td>#{row.lot_index}</td>"
            f"<td style='color: var(--text3);'>{format_date(row.buy_date)}</td>"
            f"<td class='font-mono text-right'>{row.shares_consumed:g}</td>"
            f"<td class='font-mono text-right'>{format_eur(row.cost_per_share_eur)}</td>"
            f"<td class='font-mono text-right'>{format_eur(row.sell_price_eur)}</td>"
            f"<td class='font-mono text-right {g_cls}'>{format_eur(row.realised_gain_eur, signed=True)}</td>"
            f"</tr>"
        )
    total_cls = gain_class(sim.total_realised_gain_eur.amount)
    render_html(f"""
        <div style="margin-top: 16px; font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 8px;">FIFO Lot Consumption</div>
        <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
            <thead>
                <tr style="border-bottom: 1px solid var(--border); color: var(--text3); text-transform: uppercase; font-size: 10px; letter-spacing: 0.05em;">
                    <th style="padding: 6px 4px; text-align: left;">Lot</th>
                    <th style="padding: 6px 4px; text-align: left;">Buy date</th>
                    <th style="padding: 6px 4px; text-align: right;">Shares</th>
                    <th style="padding: 6px 4px; text-align: right;">Cost/share (€)</th>
                    <th style="padding: 6px 4px; text-align: right;">Sell price (€)</th>
                    <th style="padding: 6px 4px; text-align: right;">Realised gain (€)</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        <div style="margin-top: 8px; font-size: 13px; font-weight: 600; color: var(--text);">
            Total realised gain:
            <span class="{total_cls}" style="font-family: 'DM Mono', monospace;">
                {format_eur(sim.total_realised_gain_eur, signed=True)}
            </span>
        </div>
    """)


def _render_tax_impact(sim: SellSimulation) -> None:
    if sim.marginal_tax is None:
        render_html('<div style="font-size: 12px; color: var(--text3); margin-top: 12px;">Tax impact unavailable.</div>')
        return

    mt = sim.marginal_tax
    after = mt.after_summary
    tax_cls = gain_class(-mt.marginal_total_tax_owed_eur.amount)  # tax owed is bad → negative good
    if mt.marginal_total_tax_owed_eur.amount == 0:
        tax_label = "€0 — tax-free"
        tax_cls = "gain-positive"
    else:
        tax_label = format_eur(mt.marginal_total_tax_owed_eur)
        tax_cls = "gain-negative"

    remaining_after = after.sparerpauschbetrag_remaining_eur
    total_allowance = after.sparerpauschbetrag_total_eur

    render_html(f"""
        <div style="margin-top: 16px; font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 8px;">Tax Impact</div>
        <div class="metric-row cols-3">
            <div class="metric-card">
                <div class="metric-label">Marginal Taxable Gain</div>
                <div class="metric-value sm">{format_eur(mt.marginal_taxable_gain_eur, signed=True)}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">after Teilfreistellung &amp; loss offset</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Allowance Consumed</div>
                <div class="metric-value sm">{format_eur(mt.marginal_allowance_consumed_eur)}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">{format_eur(remaining_after)} of {format_eur(total_allowance)} remaining after</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Tax Owed (Abgeltungsteuer + Soli)</div>
                <div class="metric-value sm {tax_cls}">{tax_label}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">
                    {format_eur(mt.marginal_abgeltungsteuer_eur)} tax + {format_eur(mt.marginal_solidaritaetszuschlag_eur)} Soli
                </div>
            </div>
        </div>
    """)


def _render_position_after(sim: SellSimulation) -> None:
    if sim.position_after is None:
        return
    pa = sim.position_after

    shares_before = sim.request.shares + pa.open_shares_after
    shares_delta = f"−{sim.request.shares:g} shares"

    weight_before_str = f"{pa.weight_pct_before:.1f}%" if pa.weight_pct_before is not None else "—"
    weight_after_str = f"{pa.weight_pct_after:.1f}%" if pa.weight_pct_after is not None else "—"
    weight_delta_str = ""
    if pa.weight_change_pct is not None:
        sign = "+" if pa.weight_change_pct >= 0 else ""
        weight_delta_str = f"{sign}{pa.weight_change_pct:.1f}pp"

    ur_str = format_eur(pa.unrealised_gain_eur_after, signed=True) if pa.unrealised_gain_eur_after is not None else "— (live price unavailable)"

    render_html(f"""
        <div style="margin-top: 16px; font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 8px;">Position After</div>
        <div class="metric-row cols-3">
            <div class="metric-card">
                <div class="metric-label">Open Shares After</div>
                <div class="metric-value sm">{pa.open_shares_after:g}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">{shares_delta} from {shares_before:g}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Cost Basis After (€)</div>
                <div class="metric-value sm">{format_eur(pa.cost_basis_eur_after)}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">unrealised: {ur_str}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Portfolio Weight</div>
                <div class="metric-value sm">{weight_before_str} → {weight_after_str}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">{weight_delta_str}</div>
            </div>
        </div>
    """)


def render_sell_simulator(default_ticker: str | None = None) -> None:
    """Render the embeddable sell simulator panel."""
    live_positions = get_live_positions_cached(
        repo=get_repository(),
        price_provider=get_price_provider(),
        fx_provider=get_fx_provider(),
    )
    transactions = get_repository().load_all()

    open_tickers = sorted(live_positions.keys())
    if not open_tickers:
        st.info("No open positions. Add transactions in Manage Portfolio first.")
        return

    # Build ticker → display label once per session (cached).  Uses yf.Search
    # (~150ms/ticker) so cold-cache first visit is ~2s total; all reruns instant.
    ticker_labels = _build_ticker_labels(tuple(open_tickers))

    # ── Ticker selector ────────────────────────────────────────────────────────
    # Lives OUTSIDE the form so changing it triggers an immediate rerun, which
    # updates the max-shares placeholder, price fields, and stale warning below.
    # Pre-fill from default_ticker (e.g. the ⚡ link on Live Overview/Tax pages).
    if default_ticker and default_ticker in open_tickers:
        st.session_state["sim_ticker_select"] = default_ticker

    ticker = st.selectbox(
        "Position",
        open_tickers,
        key="sim_ticker_select",
        format_func=lambda t: ticker_labels.get(t, t),
    )
    assert ticker is not None  # open_tickers is non-empty (checked above)

    # Position context — all derived from live_positions (no network call).
    live_pos = live_positions.get(ticker or "")
    open_shares = live_pos.position.open_shares if live_pos else Decimal("0")
    is_stale = live_pos is None or live_pos.is_stale

    # Caption shows open shares + live price (no extra network call needed).
    caption_parts: list[str] = [f"{float(open_shares):g} shares open"]
    if not is_stale and live_pos and live_pos.live_price_native:
        caption_parts.append(f"live {live_pos.live_price_native}")
    st.caption(" · ".join(caption_parts))

    if is_stale:
        st.warning(
            f"Live price for {ticker} is unavailable. "
            "Enter the price you expect to execute at."
        )

    # ── Sell parameters form ───────────────────────────────────────────────────
    with st.form("sell_simulator_form"):
        col1, col2 = st.columns(2)
        with col1:
            sell_date = st.date_input(
                "Sell date",
                value=date.today(),
                min_value=date(2000, 1, 1),
                max_value=date.today(),
            )
            shares_f: float | None = st.number_input(
                "Shares to sell",
                min_value=0.0001,
                value=None,
                step=1.0,
                format="%.4f",
                placeholder=f"Max: {float(open_shares):g}",
            )
        with col2:
            use_live = False
            if not is_stale and live_pos and live_pos.live_price_native is not None:
                price_toggle = st.radio("Price source", ["Live", "Manual"], horizontal=True)
                use_live = price_toggle == "Live"

            if use_live and live_pos and live_pos.live_price_native is not None:
                st.caption(f"Live price: {live_pos.live_price_native}")
                manual_price_f: float | None = None
                manual_fx_f = float(live_pos.current_fx_rate or Decimal("1"))
            else:
                currency_str = ""
                if live_pos and live_pos.position.open_lots:
                    currency_str = live_pos.position.open_lots[0].cost_per_share_native.currency.value
                manual_price_f = st.number_input(
                    f"Price per share ({currency_str or 'native'})",
                    min_value=0.0001,
                    step=0.01,
                    format="%.4f",
                )
                default_fx = float(live_pos.current_fx_rate or Decimal("1")) if live_pos else 1.0
                manual_fx_f = st.number_input(
                    "FX rate (EUR per 1 native)",
                    min_value=0.000001,
                    value=default_fx,
                    step=0.000001,
                    format="%.6f",
                )

        submitted = st.form_submit_button("Preview impact →", type="primary")

    if not submitted:
        return

    if shares_f is None or shares_f <= 0:
        st.error("Enter the number of shares to sell.")
        return

    # Resolve price
    if use_live and live_pos and live_pos.live_price_native is not None:
        sell_price = live_pos.live_price_native
        fx_rate = live_pos.current_fx_rate or Decimal("1")
    else:
        if manual_price_f is None or manual_price_f <= 0:
            st.error("Enter a valid sell price.")
            return
        currency = (
            live_pos.position.open_lots[0].cost_per_share_native.currency
            if live_pos and live_pos.position.open_lots
            else _EUR
        )
        sell_price = Money(amount=Decimal(str(manual_price_f)), currency=currency)
        fx_rate = Decimal(str(manual_fx_f))

    request = SellSimulationRequest(
        ticker=ticker,
        shares=Decimal(str(shares_f)),
        sell_price_native=sell_price,
        sell_fx_rate_eur=fx_rate,
        sell_date=sell_date,
    )

    profile, cf_aktien, cf_general, add_div, add_int = _load_tax_context(sell_date.year)
    isin_map = get_isin_map_repo().load()

    try:
        sim = simulate_sell(
            request=request,
            transactions=transactions,
            profile=profile,
            live_positions=live_positions,
            carryforward_eur_aktien=cf_aktien,
            carryforward_eur_general=cf_general,
            additional_dividend_income_eur=add_div,
            additional_interest_income_eur=add_int,
            isin_map=isin_map,
        )
    except InstrumentClassificationError as exc:
        st.warning(
            f"⚠ Tax kind missing: {exc}\n\n"
            "Open the Mappings page to classify this ticker, then retry."
        )
        if st.button("Open Mappings page", key="sim_open_mappings"):
            st.query_params["page"] = "mappings"
        return
    except Exception as exc:
        st.error(f"Simulation error: {exc}")
        return

    if not sim.is_valid:
        st.warning(f"⚠ {sim.validation_error}")
        return

    # Header summary
    proceed_eur = Money(
        amount=(sell_price.amount * fx_rate * request.shares).quantize(Decimal("0.01")),
        currency=_EUR,
    )
    render_html(f"""
        <div style="padding: 10px 14px; background: var(--surface2); border-radius: 6px; margin-bottom: 12px; font-size: 13px;">
            Simulating: SELL <strong>{request.shares:g} {ticker}</strong>
            on {format_date(sell_date)}
            at {format_eur(sell_price)} ·
            implied proceeds <strong>{format_eur(proceed_eur)}</strong>
        </div>
    """)

    _render_lot_table(sim)
    _render_tax_impact(sim)
    _render_position_after(sim)

    st.divider()
    col1, col2 = st.columns([2, 5])
    with col1:
        if st.button("Record this trade →", type="primary", key="sim_record_btn"):
            st.session_state.simulator_handoff = request
            # Set query params — main.py reads these on every rerun and overwrites
            # session_state.current_page, so this is the authoritative navigation signal.
            # Assigning to st.query_params triggers the rerun automatically.
            st.query_params["page"] = "manage"
    with col2:
        st.caption("Opens Manage Portfolio pre-filled with these values for your review.")
