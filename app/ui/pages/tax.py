# ruff: noqa: E501
"""Tax Dashboard page — Sparerpauschbetrag tracker, harvest opportunity, tax exposure."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import streamlit as st

from app.domain.money import Currency, Money
from app.domain.positions import LivePosition
from app.domain.tax.classification import InstrumentClassificationError, InstrumentKind
from app.domain.tax.models import (
    FilingStatus,
    HarvestImpact,
    HarvestImpactReport,
    TaxProfile,
    TaxYearSummary,
)
from app.ports.tax_profile_repo import TaxProfileDocument, YearlyTaxInputs
from app.services.tax_planning import (
    compute_current_tax_summary,
    compute_per_position_harvest_impact,
    compute_tax_if_full_liquidation,
)
from app.services.valuation import compute_live_positions
from app.ui.cache_keys import file_mtime_key, transactions_signature
from app.ui.format import format_eur, format_pct, gain_class
from app.ui.render import render_html
from app.ui.wiring import (
    get_fx_provider,
    get_isin_map_repo,
    get_price_provider,
    get_repository,
    get_tax_profile_repo,
)

_EUR = Currency.EUR

_KIND_LABEL: dict[InstrumentKind, str] = {
    InstrumentKind.AKTIE: "Aktie",
    InstrumentKind.AKTIENFONDS: "Aktienfonds (ETF)",
    InstrumentKind.MISCHFONDS: "Mischfonds",
    InstrumentKind.RENTENFONDS: "Rentenfonds",
    InstrumentKind.IMMOBILIENFONDS: "Immobilienfonds",
    InstrumentKind.IMMOBILIENFONDS_AUSLAND: "Immobilienfonds (Ausland)",
    InstrumentKind.SONSTIGE: "Sonstige",
    InstrumentKind.DIVIDENDE: "Dividende",
    InstrumentKind.ZINSEN: "Zinsen",
}


# ---------------------------------------------------------------------------
# Cache key helpers
# ---------------------------------------------------------------------------

def _tax_profile_signature() -> str:
    from app.config import get_settings
    return file_mtime_key(Path(get_settings().tax_profile_json_path))


def _isin_map_signature() -> str:
    from app.config import get_settings
    return file_mtime_key(Path(get_settings().isin_map_json_path))


# ---------------------------------------------------------------------------
# Headroom calculation (testable helper — used in tests/unit/ui/test_tax_page_helpers.py)
# ---------------------------------------------------------------------------

def compute_headroom(summary: TaxYearSummary) -> Money:
    """Total gain the user can realise today before owing any tax."""
    return (
        summary.sparerpauschbetrag_remaining_eur
        + summary.aktien_pot.remaining_carryforward_eur
        + summary.general_pot.remaining_carryforward_eur
    )


def compute_headroom_breakdown(summary: TaxYearSummary) -> tuple[Money, Money, Money]:
    """Return (allowance_remaining, aktien_pot_remaining, general_pot_remaining)."""
    return (
        summary.sparerpauschbetrag_remaining_eur,
        summary.aktien_pot.remaining_carryforward_eur,
        summary.general_pot.remaining_carryforward_eur,
    )


def compute_sequential_harvest_impacts(
    sorted_impacts: list[HarvestImpact],
    headroom: Money,
) -> list[tuple[HarvestImpact, Money, Money]]:
    """Walk positions largest-first; compute per-row tax and remaining headroom.

    Returns list of (impact, tax_if_realised_sequentially, headroom_after).
    The headroom is consumed as we walk: row N's tax assumes rows 0..N-1 already sold.
    This is a UI helper — it re-accounts for the sequential order displayed in the table.
    The `incremental_tax_eur` on each `HarvestImpact` is the true marginal cost from the
    engine (runs independently), not sequentially. For the table we compute sequential
    using the remaining headroom tracker.
    """
    results: list[tuple[HarvestImpact, Money, Money]] = []
    remaining = headroom
    for impact in sorted_impacts:
        gain = impact.unrealised_gain_eur
        if gain.amount <= Decimal("0"):
            continue
        taxable = impact.taxable_gain_after_teilfreistellung_eur
        if taxable.amount <= Decimal("0"):
            sequential_tax = Money.zero(_EUR)
            headroom_after = remaining
        else:
            sheltered = Money(amount=min(remaining.amount, taxable.amount), currency=_EUR)
            remaining = remaining - sheltered
            net_taxable = taxable - sheltered
            # 26.375% total (25% + 5.5% soli on tax)
            sequential_tax_amount = (net_taxable.amount * Decimal("0.26375")).quantize(Decimal("0.01"))
            sequential_tax = Money(amount=sequential_tax_amount, currency=_EUR)
            headroom_after = remaining
        results.append((impact, sequential_tax, headroom_after))
    return results


# ---------------------------------------------------------------------------
# Cached data loading
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def _cached_live_positions(tx_sig: str) -> dict[str, LivePosition]:
    txs = get_repository().load_all()
    return compute_live_positions(txs, get_price_provider(), get_fx_provider())


@st.cache_data(ttl=60, show_spinner=False)
def _cached_tax_summary(tx_sig: str, profile_sig: str, isin_sig: str, year: int) -> TaxYearSummary:
    repo = get_tax_profile_repo()
    doc = repo.load()
    inputs = doc.inputs_for_year(year)
    profile = TaxProfile(filing_status=doc.filing_status)
    txs = get_repository().load_all()
    isin_map = get_isin_map_repo().load()
    as_of = datetime(year, 12, 31)  # compute for full year-to-date
    return compute_current_tax_summary(
        transactions=txs,
        profile=profile,
        carryforward_eur_aktien=inputs.carryforward_aktien_eur,
        carryforward_eur_general=inputs.carryforward_general_eur,
        additional_dividend_income_eur=inputs.additional_dividend_income_eur,
        additional_interest_income_eur=inputs.additional_interest_income_eur,
        as_of=as_of,
        isin_map=isin_map,
    )


@st.cache_data(ttl=60, show_spinner=False)
def _cached_harvest_report(tx_sig: str, profile_sig: str, isin_sig: str, year: int) -> HarvestImpactReport:
    repo = get_tax_profile_repo()
    doc = repo.load()
    inputs = doc.inputs_for_year(year)
    profile = TaxProfile(filing_status=doc.filing_status)
    txs = get_repository().load_all()
    isin_map = get_isin_map_repo().load()
    live_positions = _cached_live_positions(tx_sig)
    summary = _cached_tax_summary(tx_sig, profile_sig, isin_sig, year)
    as_of = datetime.now()
    return compute_per_position_harvest_impact(
        transactions=txs,
        live_positions=live_positions,
        current_summary=summary,
        profile=profile,
        carryforward_eur_aktien=inputs.carryforward_aktien_eur,
        carryforward_eur_general=inputs.carryforward_general_eur,
        additional_dividend_income_eur=inputs.additional_dividend_income_eur,
        additional_interest_income_eur=inputs.additional_interest_income_eur,
        as_of=as_of,
        isin_map=isin_map,
    )


@st.cache_data(ttl=60, show_spinner=False)
def _cached_liquidation_summary(tx_sig: str, profile_sig: str, isin_sig: str, year: int) -> TaxYearSummary:
    repo = get_tax_profile_repo()
    doc = repo.load()
    inputs = doc.inputs_for_year(year)
    profile = TaxProfile(filing_status=doc.filing_status)
    txs = get_repository().load_all()
    isin_map = get_isin_map_repo().load()
    live_positions = _cached_live_positions(tx_sig)
    summary = _cached_tax_summary(tx_sig, profile_sig, isin_sig, year)
    as_of = datetime.now()
    return compute_tax_if_full_liquidation(
        transactions=txs,
        live_positions=live_positions,
        current_summary=summary,
        profile=profile,
        carryforward_eur_aktien=inputs.carryforward_aktien_eur,
        carryforward_eur_general=inputs.carryforward_general_eur,
        additional_dividend_income_eur=inputs.additional_dividend_income_eur,
        additional_interest_income_eur=inputs.additional_interest_income_eur,
        as_of=as_of,
        isin_map=isin_map,
    )


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

def _render_ytd_tiles(summary: TaxYearSummary) -> None:
    gross_gains = sum(
        (i.gross_gain_eur.amount for i in summary.realised_gain_impacts if i.gross_gain_eur.amount > 0),
        Decimal("0"),
    )
    gross_losses = sum(
        (i.gross_gain_eur.amount for i in summary.realised_gain_impacts if i.gross_gain_eur.amount < 0),
        Decimal("0"),
    )
    net_gross = gross_gains + gross_losses
    net_class = gain_class(net_gross)

    consumed = summary.sparerpauschbetrag_consumed_eur
    total_allowance = summary.sparerpauschbetrag_total_eur
    remaining_allowance = summary.sparerpauschbetrag_remaining_eur

    aktien_pot_remaining = summary.aktien_pot.remaining_carryforward_eur
    general_pot_remaining = summary.general_pot.remaining_carryforward_eur
    headroom = compute_headroom(summary)

    both_pots_zero = (
        summary.aktien_pot.prior_year_carryforward_eur.amount == Decimal("0")
        and summary.general_pot.prior_year_carryforward_eur.amount == Decimal("0")
    )
    pot_subtitle = (
        "none yet — set in profile if applicable"
        if both_pots_zero
        else f"aktien {format_eur(aktien_pot_remaining)} · general {format_eur(general_pot_remaining)}"
    )

    allowance_pct = (
        float(consumed.amount / total_allowance.amount * Decimal("100"))
        if total_allowance.amount > 0
        else 0.0
    )
    allowance_pct = min(allowance_pct, 100.0)

    headroom_subtitle = (
        f"{format_eur(remaining_allowance)} allowance "
        f"+ {format_eur(aktien_pot_remaining)} aktien pot "
        f"+ {format_eur(general_pot_remaining)} general pot"
    )

    render_html(f"""
        <div class="metric-row cols-4">
            <div class="metric-card">
                <div class="metric-label">Sparerpauschbetrag</div>
                <div class="metric-value sm">{format_eur(total_allowance)}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">
                    {format_eur(consumed)} used · {format_eur(remaining_allowance)} remaining
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Realised Gains YTD (gross)</div>
                <div class="metric-value sm {net_class}">{format_eur(Money(amount=net_gross, currency=_EUR), signed=True)}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">
                    {format_eur(Money(amount=gross_losses, currency=_EUR), signed=True)} losses · gross {format_eur(Money(amount=gross_gains, currency=_EUR))}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Loss Pot Carried-In</div>
                <div class="metric-value sm">{format_eur(summary.aktien_pot.prior_year_carryforward_eur + summary.general_pot.prior_year_carryforward_eur)}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">{pot_subtitle}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Tax Headroom</div>
                <div class="metric-value sm gain-positive">{format_eur(headroom)}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">{headroom_subtitle}</div>
            </div>
        </div>
    """)

    # Progress bar
    render_html(f"""
        <div class="tax-progress-wrap">
            <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text3); margin-bottom: 4px;">
                <span>Sparerpauschbetrag consumed</span>
                <span class="font-mono">{allowance_pct:.0f}% · {format_eur(consumed)} / {format_eur(total_allowance)}</span>
            </div>
            <div style="width: 100%; height: 8px; background: var(--surface2); border-radius: 4px; overflow: hidden;">
                <div style="width: {allowance_pct:.1f}%; height: 100%; background: var(--green); border-radius: 4px;"></div>
            </div>
        </div>
    """)


def _render_tax_exposure(
    summary: TaxYearSummary,
    liq_summary: TaxYearSummary,
    live_positions: dict[str, LivePosition],
) -> None:
    stale_tickers = [t for t, p in live_positions.items() if p.is_stale]

    net_unrealised = sum(
        (p.unrealised_gain_eur.amount for p in live_positions.values() if not p.is_stale and p.unrealised_gain_eur),
        Decimal("0"),
    )
    total_cost = sum(
        (p.position.cost_basis_eur.amount for p in live_positions.values() if not p.is_stale),
        Decimal("0"),
    )
    ur_pct = (
        format_pct(net_unrealised / total_cost * Decimal("100"), signed=True)
        if total_cost > 0
        else "—"
    )
    ur_class = gain_class(net_unrealised)

    # Sheltered amount = liq_summary shows what would have been consumed from allowance + carryforward
    sheltered_allowance = liq_summary.sparerpauschbetrag_consumed_eur - summary.sparerpauschbetrag_consumed_eur
    sheltered_aktien = liq_summary.aktien_pot.consumed_against_gains_eur - summary.aktien_pot.consumed_against_gains_eur
    sheltered_general = liq_summary.general_pot.consumed_against_gains_eur - summary.general_pot.consumed_against_gains_eur
    sheltered_total_amount = max(
        Decimal("0"),
        sheltered_allowance.amount + sheltered_aktien.amount + sheltered_general.amount,
    )
    sheltered_total = Money(amount=sheltered_total_amount, currency=_EUR)

    taxable_gain = liq_summary.taxable_after_allowance_eur
    tax_owed = liq_summary.total_tax_owed_eur
    tax_class = "gain-positive" if tax_owed.amount == 0 else "gain-negative"
    tax_subtitle = "€0 — tax-free" if tax_owed.amount == 0 else "26.375% Abgeltungsteuer + Soli"
    taxable_subtitle = "fully sheltered ✓" if taxable_gain.amount == 0 else "after Teilfreistellung, offsets, allowance"
    taxable_class = "gain-positive" if taxable_gain.amount == 0 else ""

    render_html("""
        <div style="margin-top: 24px; margin-bottom: 8px; font-size: 13px; font-weight: 600; color: var(--text);">
            Total Tax Exposure
        </div>
        <div style="font-size: 11px; color: var(--text3); margin-bottom: 12px;">
            What would you owe if every position were closed today?
        </div>
    """)

    if stale_tickers:
        render_html(f"""
            <div style="background: var(--amber-bg); border: 1px solid var(--amber); border-radius: 6px; padding: 10px 14px; margin-bottom: 12px; font-size: 12px; color: var(--amber);">
                &#9888; {len(stale_tickers)} position(s) have stale prices and are excluded from tax exposure estimates:
                {", ".join(stale_tickers)}. Refresh from Live Overview when prices return.
            </div>
        """)

    render_html(f"""
        <div class="metric-row cols-4">
            <div class="metric-card">
                <div class="metric-label">Net Unrealised Gain</div>
                <div class="metric-value sm {ur_class}">{format_eur(Money(amount=net_unrealised, currency=_EUR), signed=True)}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">{ur_pct}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Sheltered (Allowance + Loss Pot)</div>
                <div class="metric-value sm">{format_eur(sheltered_total)}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">absorbed if liquidated today</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Taxable Gain</div>
                <div class="metric-value sm {taxable_class}">{format_eur(taxable_gain)}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">{taxable_subtitle}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Tax Owed (if closed today)</div>
                <div class="metric-value sm {tax_class}">{format_eur(tax_owed)}</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 4px;">{tax_subtitle}</div>
            </div>
        </div>
        <div style="font-size: 10px; color: var(--text3); margin-top: 6px;">
            &#9888; Vorabpauschale not included for accumulating ETFs (TICKET-010b)
        </div>
    """)


def _render_harvest_table(
    harvest_report: HarvestImpactReport,
    summary: TaxYearSummary,
) -> None:
    headroom = compute_headroom(summary)
    positive_impacts = sorted(
        [imp for imp in harvest_report.impacts.values() if imp.unrealised_gain_eur.amount > 0],
        key=lambda i: i.unrealised_gain_eur.amount,
        reverse=True,
    )

    render_html(f"""
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-top: 24px; margin-bottom: 4px;">
            <div>
                <div style="font-size: 13px; font-weight: 600; color: var(--text);">Harvest Opportunity</div>
                <div style="font-size: 11px; color: var(--text3); margin-top: 2px;">
                    Positions with unrealised gains — largest first.
                    "Tax if Realised" is computed sequentially: row N assumes rows above it have already been sold.
                </div>
            </div>
            <div class="metric-card" style="min-width: 160px; text-align: right;">
                <div class="metric-label">Tax-free headroom</div>
                <div class="metric-value sm gain-positive">{format_eur(headroom)}</div>
            </div>
        </div>
    """)

    if not positive_impacts:
        render_html('<div style="font-size: 12px; color: var(--text3); padding: 12px 0;">No positions with unrealised gains.</div>')
    else:
        sequential = compute_sequential_harvest_impacts(positive_impacts, headroom)
        rows = ""
        for impact, seq_tax, hdroom_after in sequential:
            tax_class = "gain-positive" if seq_tax.amount == 0 else "gain-negative"
            tax_label = format_eur(seq_tax) if seq_tax.amount > 0 else "€0 — tax-free"
            gain_str = format_eur(impact.unrealised_gain_eur, signed=True)
            g_class = gain_class(impact.unrealised_gain_eur.amount)
            kind_label = _KIND_LABEL.get(impact.instrument_kind, impact.instrument_kind.value)
            sim_link = (
                f'<a href="/?page=simulator&ticker={impact.ticker}" target="_self" '
                f'title="Simulate sell" style="color: var(--text3); text-decoration: none;">⚡</a>'
            )
            rows += (
                f'<tr>'
                f'<td><strong>{impact.ticker}</strong></td>'
                f'<td class="font-mono text-right {g_class}">{gain_str}</td>'
                f'<td class="font-mono text-right {tax_class}">{tax_label}</td>'
                f'<td class="font-mono text-right">{format_eur(hdroom_after)}</td>'
                f'<td style="color: var(--text3);">{kind_label}</td>'
                f'<td class="text-center">{sim_link}</td>'
                f'</tr>'
            )

        render_html(f"""
            <table class="harvest-table" style="width: 100%; border-collapse: collapse; font-size: 13px;">
                <thead>
                    <tr style="border-bottom: 1px solid var(--border); color: var(--text3); text-transform: uppercase; font-size: 10px; letter-spacing: 0.05em;">
                        <th style="padding: 6px 4px; text-align: left;">Ticker</th>
                        <th style="padding: 6px 4px; text-align: right;">Gain (€)</th>
                        <th style="padding: 6px 4px; text-align: right;">Tax if Realised</th>
                        <th style="padding: 6px 4px; text-align: right;">Headroom Left</th>
                        <th style="padding: 6px 4px; text-align: left;">Kind</th>
                        <th style="padding: 6px 4px; text-align: center;">Sim</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        """)

    if harvest_report.stale_tickers:
        render_html(f'<div style="font-size: 11px; color: var(--text3); margin-top: 8px;">Excluded due to stale prices: {", ".join(harvest_report.stale_tickers)}</div>')


def _render_loss_harvest_table(harvest_report: HarvestImpactReport) -> None:
    loss_impacts = sorted(
        [imp for imp in harvest_report.impacts.values() if imp.unrealised_gain_eur.amount < 0],
        key=lambda i: i.unrealised_gain_eur.amount,
    )
    if not loss_impacts:
        return

    render_html('<div style="margin-top: 24px; font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 8px;">Loss Harvesting</div>')

    rows = ""
    for impact in loss_impacts:
        loss = impact.unrealised_gain_eur
        pot = "Aktien-Pot" if impact.instrument_kind == InstrumentKind.AKTIE else "General-Pot"
        rows += (
            f'<tr>'
            f'<td><strong>{impact.ticker}</strong></td>'
            f'<td class="font-mono text-right gain-negative">{format_eur(loss, signed=True)}</td>'
            f'<td style="color: var(--text3);">{pot}</td>'
            f'<td style="color: var(--text3);">{_KIND_LABEL.get(impact.instrument_kind, impact.instrument_kind.value)}</td>'
            f'</tr>'
        )

    render_html(f"""
        <table class="harvest-table" style="width: 100%; border-collapse: collapse; font-size: 13px;">
            <thead>
                <tr style="border-bottom: 1px solid var(--border); color: var(--text3); text-transform: uppercase; font-size: 10px; letter-spacing: 0.05em;">
                    <th style="padding: 6px 4px; text-align: left;">Ticker</th>
                    <th style="padding: 6px 4px; text-align: right;">Loss (€)</th>
                    <th style="padding: 6px 4px; text-align: left;">Pot it feeds</th>
                    <th style="padding: 6px 4px; text-align: left;">Kind</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    """)


def _render_profile_editor(year: int) -> None:
    repo = get_tax_profile_repo()
    doc = repo.load()
    inputs = doc.inputs_for_year(year)
    prev_inputs = doc.inputs_for_year(year - 1)

    with st.expander("Edit Tax Profile", expanded=False):
        st.caption(
            "Enter the carryforward amounts from your last Steuerbescheid. "
            "If you have never received one for this account, leave at €0 — do not guess."
        )

        filing_options = [FilingStatus.SINGLE, FilingStatus.JOINT]
        filing_labels = ["Single (Einzelveranlagung)", "Joint (Zusammenveranlagung)"]
        filing_idx = filing_options.index(doc.filing_status)
        radio_result = st.radio("Filing status", filing_labels, index=filing_idx, horizontal=True)
        new_filing = filing_options[1] if radio_result == filing_labels[1] else filing_options[0]

        st.markdown(f"**{year} carryforward inputs** (from {year - 1} Steuerbescheid)")
        col1, col2 = st.columns(2)
        with col1:
            aktien_in = st.number_input(
                "Aktien-Pot carryforward (€)",
                value=float(inputs.carryforward_aktien_eur.amount),
                min_value=0.0,
                step=1.0,
                help="Verlusttopf Aktien — closing balance from your last Steuerbescheid. Leave at 0 if not applicable.",
                key=f"tax_aktien_{year}",
            )
            dividend_in = st.number_input(
                f"Additional dividend income {year} (€)",
                value=float(inputs.additional_dividend_income_eur.amount),
                min_value=0.0,
                step=1.0,
                help="Dividends received outside Scalable Capital in this account year.",
                key=f"tax_div_{year}",
            )
        with col2:
            general_in = st.number_input(
                "General-Pot carryforward (€)",
                value=float(inputs.carryforward_general_eur.amount),
                min_value=0.0,
                step=1.0,
                help="Verlusttopf Sonstige — closing balance from your last Steuerbescheid. Leave at 0 if not applicable.",
                key=f"tax_general_{year}",
            )
            interest_in = st.number_input(
                f"Additional interest income {year} (€)",
                value=float(inputs.additional_interest_income_eur.amount),
                min_value=0.0,
                step=1.0,
                help="Interest income outside Scalable Capital in this account year.",
                key=f"tax_int_{year}",
            )

        st.markdown(f"**{year - 1} carryforward (prior year record)**")
        col3, col4 = st.columns(2)
        with col3:
            prev_aktien_in = st.number_input(
                f"Aktien-Pot carryforward (€) · {year - 1}",
                value=float(prev_inputs.carryforward_aktien_eur.amount),
                min_value=0.0,
                step=1.0,
                key=f"tax_aktien_{year - 1}",
            )
            prev_dividend_in = st.number_input(
                f"Additional dividend income {year - 1} (€)",
                value=float(prev_inputs.additional_dividend_income_eur.amount),
                min_value=0.0,
                step=1.0,
                key=f"tax_div_{year - 1}",
            )
        with col4:
            prev_general_in = st.number_input(
                f"General-Pot carryforward (€) · {year - 1}",
                value=float(prev_inputs.carryforward_general_eur.amount),
                min_value=0.0,
                step=1.0,
                key=f"tax_general_{year - 1}",
            )
            prev_interest_in = st.number_input(
                f"Additional interest income {year - 1} (€)",
                value=float(prev_inputs.additional_interest_income_eur.amount),
                min_value=0.0,
                step=1.0,
                key=f"tax_int_{year - 1}",
            )

        def _eur(v: float) -> Money:
            return Money(amount=Decimal(str(v)).quantize(Decimal("0.01")), currency=_EUR)

        if st.button("Save tax profile", key="tax_profile_save"):
            new_per_year = dict(doc.per_year)
            new_per_year[year] = YearlyTaxInputs(
                carryforward_aktien_eur=_eur(aktien_in),
                carryforward_general_eur=_eur(general_in),
                additional_dividend_income_eur=_eur(dividend_in),
                additional_interest_income_eur=_eur(interest_in),
            )
            new_per_year[year - 1] = YearlyTaxInputs(
                carryforward_aktien_eur=_eur(prev_aktien_in),
                carryforward_general_eur=_eur(prev_general_in),
                additional_dividend_income_eur=_eur(prev_dividend_in),
                additional_interest_income_eur=_eur(prev_interest_in),
            )
            new_doc = TaxProfileDocument(
                version=1,
                filing_status=new_filing,
                per_year=new_per_year,
            )
            repo.save(new_doc)
            st.cache_data.clear()
            st.session_state["tax_profile_feedback"] = "saved"
            st.rerun()

    if st.session_state.get("tax_profile_feedback") == "saved":
        st.success("Tax profile updated.")
        st.session_state["tax_profile_feedback"] = None


# ---------------------------------------------------------------------------
# Main render entry point
# ---------------------------------------------------------------------------

def _render_classification_warning(exc: InstrumentClassificationError) -> None:
    st.warning(
        f"⚠ Some tickers need a Tax kind before the full summary can be computed: {exc}\n\n"
        "Open the Mappings page to classify them."
    )
    if st.button("Open Mappings page", key="tax_open_mappings"):
        st.query_params["page"] = "mappings"


def render() -> None:
    now = datetime.now()
    year = now.year

    txs = get_repository().load_all()
    tx_sig = transactions_signature(txs)
    profile_sig = _tax_profile_signature()
    isin_sig = _isin_map_signature()

    render_html('<div style="font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 12px;">YTD Tax Summary</div>')

    try:
        summary = _cached_tax_summary(tx_sig, profile_sig, isin_sig, year)
    except InstrumentClassificationError as exc:
        _render_classification_warning(exc)
        return
    except Exception as exc:
        st.error(f"Could not compute tax summary: {exc}")
        return

    live_positions = _cached_live_positions(tx_sig)

    _render_ytd_tiles(summary)

    try:
        liq_summary = _cached_liquidation_summary(tx_sig, profile_sig, isin_sig, year)
    except InstrumentClassificationError as exc:
        _render_classification_warning(exc)
        liq_summary = summary
    except Exception as exc:
        st.warning(f"Could not compute liquidation scenario: {exc}")
        liq_summary = summary

    _render_tax_exposure(summary, liq_summary, live_positions)

    try:
        harvest_report = _cached_harvest_report(tx_sig, profile_sig, isin_sig, year)
    except InstrumentClassificationError as exc:
        _render_classification_warning(exc)
        harvest_report = HarvestImpactReport(impacts={}, stale_tickers=tuple(live_positions.keys()))
    except Exception as exc:
        st.warning(f"Could not compute harvest opportunities: {exc}")
        harvest_report = HarvestImpactReport(impacts={}, stale_tickers=tuple(live_positions.keys()))

    _render_harvest_table(harvest_report, summary)
    _render_loss_harvest_table(harvest_report)
    _render_profile_editor(year)

    stale_count = sum(1 for p in live_positions.values() if p.is_stale)
    status_text = f"● LIVE · {now.strftime('%H:%M')}"
    if stale_count:
        status_text = f"● PARTIAL · {stale_count} of {len(live_positions)} positions stale"

    render_html(f"""
        <div style="margin-top: 16px; font-size: 11px; font-family: 'DM Mono', monospace; color: var(--text3); text-align: right;">
            {status_text}
        </div>
    """)
