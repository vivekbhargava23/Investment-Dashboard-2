from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import streamlit as st

from app.domain.models import Transaction
from app.domain.money import Currency, Money
from app.domain.positions import LivePosition
from app.domain.tax.models import TaxProfile
from app.ports.tax_profile_repo import YearlyTaxInputs
from app.services.sell_simulator import (
    SellSimulationRequest,
    simulate_sell,
)
from app.ui.format import format_date, format_eur, format_pct
from app.ui.render import render_html

_EUR = Currency.EUR


def _render_simulation_result(sim) -> None:
    if not sim.is_valid:
        st.error(f"Simulation failed: {sim.validation_error}")
        return

    st.markdown("### Simulated Impact")

    # 1. Lot Consumption Table
    rows = []
    for lot in sim.lot_consumption:
        rows.append(
            f"<tr>"
            f"<td style='padding: 8px 4px;'>Lot {lot.lot_index}</td>"
            f"<td style='padding: 8px 4px;'>{format_date(lot.buy_date)}</td>"
            f"<td style='padding: 8px 4px; text-align: right;'>{lot.shares_consumed:g}</td>"
            f"<td style='padding: 8px 4px; text-align: right;'>{format_eur(lot.cost_per_share_eur, signed=False)}</td>"
            f"<td style='padding: 8px 4px; text-align: right;'>{format_eur(lot.realised_gain_eur)}</td>"
            f"</tr>"
        )

    table_html = f"""
    <table class="lot-consumption-table" style="width: 100%; border-collapse: collapse; margin-bottom: 16px;">
        <thead>
            <tr style="border-bottom: 1px solid var(--border); color: var(--text3); font-size: 11px; text-transform: uppercase;">
                <th style="padding: 4px 8px; text-align: left;">Lot</th>
                <th style="padding: 4px 8px; text-align: left;">Buy Date</th>
                <th style="padding: 4px 8px; text-align: right;">Shares</th>
                <th style="padding: 4px 8px; text-align: right;">Cost/Sh (€)</th>
                <th style="padding: 4px 8px; text-align: right;">Gain (€)</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows)}
            <tr style="border-top: 1px solid var(--border); font-weight: bold;">
                <td colspan="4" style="padding: 8px;">Total FIFO Realised Gain</td>
                <td style="padding: 8px; text-align: right;">{format_eur(sim.total_realised_gain_eur)}</td>
            </tr>
        </tbody>
    </table>
    """
    render_html(table_html)

    # 2. Side-by-side impacts
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Tax Impact")
        if sim.marginal_tax is None:
            st.info("Tax impact unavailable.")
        else:
            tax = sim.marginal_tax
            st.markdown(f"""
            - **Taxable after allowance**: {format_eur(tax.marginal_taxable_gain_eur)}
            - **Allowance consumed**: {format_eur(tax.marginal_allowance_consumed_eur)}
            - **Aktien pot change**: {format_eur(tax.marginal_aktien_carryforward_change_eur)}
            - **General pot change**: {format_eur(tax.marginal_general_carryforward_change_eur)}
            - **Total Tax Owed**: **{format_eur(tax.marginal_total_tax_owed_eur)}**
            """)

    with col2:
        st.markdown("#### Portfolio Impact")
        if sim.position_after is None:
            st.info("Portfolio impact unavailable.")
        else:
            pos = sim.position_after
            gain_str = format_eur(pos.unrealised_gain_eur_after) if pos.unrealised_gain_eur_after else "—"
            w_before = f"{pos.weight_pct_before:.1f}%" if pos.weight_pct_before is not None else "—"
            w_after = f"{pos.weight_pct_after:.1f}%" if pos.weight_pct_after is not None else "—"
            w_change = f" ({format_pct(pos.weight_change_pct, signed=True)})" if pos.weight_change_pct is not None else ""
            
            st.markdown(f"""
            - **Shares remaining**: {pos.open_shares_after:g}
            - **Remaining cost basis**: {format_eur(pos.cost_basis_eur_after)}
            - **Remaining unrealised gain**: {gain_str}
            - **Portfolio weight**: {w_before} → {w_after}{w_change}
            """)


def render_sell_simulator(
    transactions: Sequence[Transaction],
    live_positions: dict[str, LivePosition],
    profile: TaxProfile,
    yearly_inputs: YearlyTaxInputs,
    default_ticker: str | None = None,
) -> None:
    """Render the Sell Simulator component."""
    
    open_tickers = [t for t, lp in live_positions.items() if lp.position.open_shares > 0]
    
    if not open_tickers:
        st.info("No open positions available to simulate.")
        return

    # default index
    idx = 0
    if default_ticker and default_ticker in open_tickers:
        idx = open_tickers.index(default_ticker)

    with st.form("sell_simulator_form"):
        col1, col2 = st.columns(2)
        with col1:
            ticker = st.selectbox("Ticker to Sell", options=open_tickers, index=idx)
        with col2:
            st.markdown("<div style='height: 32px;'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("Simulate →", type="primary")

        live_pos = live_positions.get(ticker)
        max_shares = float(live_pos.position.open_shares) if live_pos else 0.0

        col3, col4 = st.columns(2)
        with col3:
            shares_to_sell = st.number_input(
                "Shares", min_value=0.0001, max_value=max_shares, value=min(1.0, max_shares), step=1.0, format="%.4f"
            )
        with col4:
            sell_date = st.date_input("Hypothetical Sell Date", value=date.today())
        
        # Price section
        st.markdown("##### Price Source")
        
        live_price_val = 0.0
        live_fx_val = 1.0
        ccy = _EUR
        stale_reason = None
        
        if live_pos:
            if live_pos.is_stale:
                stale_reason = live_pos.staleness_reason
            elif live_pos.live_price_native:
                live_price_val = float(live_pos.live_price_native.amount)
                ccy = live_pos.live_price_native.currency
                live_fx_val = float(live_pos.current_fx_rate)

        source_options = ["Live Price", "Manual Entry"]
        if stale_reason:
            st.warning(f"Live price unavailable ({stale_reason}). You must use Manual Entry.")
            source_options = ["Manual Entry"]

        st.radio("Source", options=source_options, horizontal=True)
        
        col5, col6 = st.columns(2)
        with col5:
            sell_price_f = st.number_input(
                f"Sell Price ({ccy.value})", min_value=0.0, value=live_price_val, format="%.4f", step=0.01,
                help="Price per share in native currency."
            )
        with col6:
            sell_fx_f = st.number_input(
                "FX Rate (EUR per 1 native)", min_value=0.000001, value=live_fx_val, format="%.6f", step=0.000001
            )

    if submitted:
        if shares_to_sell <= 0:
            st.error("Shares must be greater than 0.")
            return
            
        if sell_price_f <= 0:
            st.error("Price must be greater than 0.")
            return

        req = SellSimulationRequest(
            ticker=ticker,
            shares=Decimal(str(shares_to_sell)),
            sell_price_native=Money(amount=Decimal(str(sell_price_f)), currency=ccy),
            sell_fx_rate_eur=Decimal(str(sell_fx_f)),
            sell_date=sell_date,
        )

        sim = simulate_sell(
            request=req,
            transactions=transactions,
            profile=profile,
            yearly_inputs=yearly_inputs,
            live_positions=live_positions,
        )

        _render_simulation_result(sim)
