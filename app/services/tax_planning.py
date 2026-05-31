# ruff: noqa: E501
"""Tax-planning service: wrappers over the tax engine for the Tax Dashboard page.

All functions are stateless and dependency-injected. None call datetime.now().
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from app.domain.fifo import compute_realised_gains
from app.domain.isin_map import IsinMapDocument
from app.domain.models import Transaction
from app.domain.money import Currency, Money
from app.domain.positions import LivePosition
from app.domain.realised_gain import RealisedGain
from app.domain.tax.classification import classify_instrument
from app.domain.tax.engine import compute_tax_year_summary
from app.domain.tax.models import (
    HarvestImpact,
    HarvestImpactReport,
    MarginalTaxImpact,
    TaxProfile,
    TaxYearSummary,
)
from app.domain.tax.pipeline import TaxYearLedger, run_pipeline
from app.domain.tax.rates import RATES_BY_YEAR, UnsupportedTaxYearError

_EUR = Currency.EUR


def compute_current_tax_summary(
    transactions: Sequence[Transaction],
    profile: TaxProfile,
    carryforward_eur_aktien: Money,
    carryforward_eur_general: Money,
    additional_dividend_income_eur: Money,
    additional_interest_income_eur: Money,
    as_of: datetime,
    isin_map: IsinMapDocument = IsinMapDocument(),
) -> TaxYearSummary:
    """Thin wrapper over compute_tax_year_summary; validates year and delegates."""
    year = as_of.year
    if year not in RATES_BY_YEAR:
        raise UnsupportedTaxYearError(
            f"Tax year {year} is not configured. Add it to app/domain/tax/rates.py."
        )
    return compute_tax_year_summary(
        year=year,
        transactions=transactions,
        profile=profile,
        isin_map=isin_map,
        prior_year_aktien_carryforward_eur=carryforward_eur_aktien,
        prior_year_general_carryforward_eur=carryforward_eur_general,
        additional_dividend_income_eur=additional_dividend_income_eur,
        additional_interest_income_eur=additional_interest_income_eur,
    )


def _synthesize_sell_gain(live_pos: LivePosition, sell_date: datetime) -> RealisedGain:
    """Build a synthetic RealisedGain for selling the entire position at today's price."""
    assert live_pos.live_value_eur is not None
    proceeds = live_pos.live_value_eur
    cost = live_pos.position.cost_basis_eur
    gain_amount = proceeds.amount - cost.amount
    sell_d = sell_date.date()
    buy_d = sell_d - timedelta(days=365)
    return RealisedGain(
        sell_transaction_id=f"synthetic-{live_pos.ticker}-{uuid.uuid4().hex[:8]}",
        buy_transaction_id=f"synthetic-buy-{live_pos.ticker}",
        ticker=live_pos.ticker,
        shares=live_pos.position.open_shares if live_pos.position.open_shares > 0 else Decimal("1"),
        sell_date=sell_d,
        buy_date=buy_d,
        proceeds_eur=proceeds,
        cost_basis_eur=cost,
        realised_gain_eur=Money(amount=gain_amount, currency=_EUR),
        holding_period_days=365,
    )


def _run_pipeline_with_extra_gains(
    year: int,
    year_gains: list[RealisedGain],
    extra_gains: list[RealisedGain],
    profile: TaxProfile,
    carryforward_eur_aktien: Money,
    carryforward_eur_general: Money,
    additional_dividend_income_eur: Money,
    additional_interest_income_eur: Money,
    isin_map: IsinMapDocument = IsinMapDocument(),
) -> TaxYearSummary:
    rates = RATES_BY_YEAR[year]
    ledger = TaxYearLedger(
        year=year,
        rates=rates,
        profile=profile,
        realised_gains=year_gains + extra_gains,
        prior_aktien_carryforward=carryforward_eur_aktien,
        prior_general_carryforward=carryforward_eur_general,
        additional_dividend_income_eur=additional_dividend_income_eur,
        additional_interest_income_eur=additional_interest_income_eur,
        isin_map=isin_map,
    )
    return run_pipeline(ledger)


def compute_per_position_harvest_impact(
    transactions: Sequence[Transaction],
    live_positions: dict[str, LivePosition],
    current_summary: TaxYearSummary,
    profile: TaxProfile,
    carryforward_eur_aktien: Money,
    carryforward_eur_general: Money,
    additional_dividend_income_eur: Money,
    additional_interest_income_eur: Money,
    as_of: datetime,
    isin_map: IsinMapDocument = IsinMapDocument(),
) -> HarvestImpactReport:
    """Compute the marginal tax impact of selling each non-stale position today.

    For each position, runs the engine with that position's synthetic gain appended
    to the year's existing FIFO gains, then computes the increment over current_summary.
    Stale positions are excluded from impacts and listed in stale_tickers.
    """
    year = as_of.year
    if year not in RATES_BY_YEAR:
        raise UnsupportedTaxYearError(
            f"Tax year {year} is not configured."
        )

    all_gains = compute_realised_gains(list(transactions))
    year_gains = [g for g in all_gains if g.sell_date.year == year]

    impacts: dict[str, HarvestImpact] = {}
    stale_tickers: list[str] = []

    for ticker, live_pos in live_positions.items():
        if live_pos.is_stale:
            stale_tickers.append(ticker)
            continue

        synthetic = _synthesize_sell_gain(live_pos, as_of)
        new_summary = _run_pipeline_with_extra_gains(
            year=year,
            year_gains=year_gains,
            extra_gains=[synthetic],
            profile=profile,
            carryforward_eur_aktien=carryforward_eur_aktien,
            carryforward_eur_general=carryforward_eur_general,
            additional_dividend_income_eur=additional_dividend_income_eur,
            additional_interest_income_eur=additional_interest_income_eur,
            isin_map=isin_map,
        )

        incremental_tax = new_summary.abgeltungsteuer_eur - current_summary.abgeltungsteuer_eur
        incremental_soli = new_summary.solidaritaetszuschlag_eur - current_summary.solidaritaetszuschlag_eur
        total_incremental = Money(
            amount=incremental_tax.amount + incremental_soli.amount,
            currency=_EUR,
        )

        # The synthetic gain's TaxImpact is the last entry in realised_gain_impacts.
        synthetic_impact = new_summary.realised_gain_impacts[-1]

        instrument_kind = classify_instrument(ticker, isin_map)

        impacts[ticker] = HarvestImpact(
            ticker=ticker,
            instrument_kind=instrument_kind,
            unrealised_gain_eur=live_pos.unrealised_gain_eur or Money.zero(_EUR),
            taxable_gain_after_teilfreistellung_eur=synthetic_impact.taxable_gain_after_teilfreistellung_eur,
            incremental_tax_eur=incremental_tax,
            incremental_soli_eur=incremental_soli,
            total_incremental_eur=total_incremental,
            is_fully_sheltered=total_incremental.amount == Decimal("0"),
        )

    return HarvestImpactReport(
        impacts=impacts,
        stale_tickers=tuple(stale_tickers),
    )


_ZERO_EUR = Money(amount=Decimal("0"), currency=_EUR)


def compute_marginal_tax_for_realised_gains(
    current_transactions: Sequence[Transaction],
    proposed_sell: Transaction,
    profile: TaxProfile,
    carryforward_eur_aktien: Money = _ZERO_EUR,
    carryforward_eur_general: Money = _ZERO_EUR,
    additional_dividend_income_eur: Money = _ZERO_EUR,
    additional_interest_income_eur: Money = _ZERO_EUR,
    isin_map: IsinMapDocument = IsinMapDocument(),
) -> MarginalTaxImpact:
    """Compute the marginal tax impact of a single hypothetical sell.

    Runs the tax engine twice — before and after the proposed_sell — and returns
    the deltas. Using the same carryforward for both runs ensures the delta reflects
    only the marginal effect of the proposed sell.
    """
    year = proposed_sell.trade_date.year
    if year not in RATES_BY_YEAR:
        raise UnsupportedTaxYearError(
            f"Tax year {year} is not configured."
        )

    def _run(txs: Sequence[Transaction]) -> TaxYearSummary:
        return _run_pipeline_with_extra_gains(
            year=year,
            year_gains=[g for g in compute_realised_gains(list(txs)) if g.sell_date.year == year],
            extra_gains=[],
            profile=profile,
            carryforward_eur_aktien=carryforward_eur_aktien,
            carryforward_eur_general=carryforward_eur_general,
            additional_dividend_income_eur=additional_dividend_income_eur,
            additional_interest_income_eur=additional_interest_income_eur,
            isin_map=isin_map,
        )

    before = _run(current_transactions)
    after = _run(list(current_transactions) + [proposed_sell])

    def _delta(after_val: Money, before_val: Money) -> Money:
        return Money(amount=after_val.amount - before_val.amount, currency=_EUR)

    return MarginalTaxImpact(
        before_summary=before,
        after_summary=after,
        marginal_taxable_gain_eur=_delta(
            after.total_taxable_after_loss_offset_eur,
            before.total_taxable_after_loss_offset_eur,
        ),
        marginal_allowance_consumed_eur=_delta(
            after.sparerpauschbetrag_consumed_eur,
            before.sparerpauschbetrag_consumed_eur,
        ),
        marginal_aktien_carryforward_change_eur=_delta(
            after.aktien_pot.remaining_carryforward_eur,
            before.aktien_pot.remaining_carryforward_eur,
        ),
        marginal_general_carryforward_change_eur=_delta(
            after.general_pot.remaining_carryforward_eur,
            before.general_pot.remaining_carryforward_eur,
        ),
        marginal_abgeltungsteuer_eur=_delta(after.abgeltungsteuer_eur, before.abgeltungsteuer_eur),
        marginal_solidaritaetszuschlag_eur=_delta(after.solidaritaetszuschlag_eur, before.solidaritaetszuschlag_eur),
        marginal_total_tax_owed_eur=_delta(after.total_tax_owed_eur, before.total_tax_owed_eur),
    )


def compute_tax_if_full_liquidation(
    transactions: Sequence[Transaction],
    live_positions: dict[str, LivePosition],
    current_summary: TaxYearSummary,
    profile: TaxProfile,
    carryforward_eur_aktien: Money,
    carryforward_eur_general: Money,
    additional_dividend_income_eur: Money,
    additional_interest_income_eur: Money,
    as_of: datetime,
    isin_map: IsinMapDocument = IsinMapDocument(),
) -> TaxYearSummary:
    """Tax summary if every non-stale position were sold at today's prices.

    Stale positions are excluded; the caller should surface a staleness warning.
    If all positions are stale, returns current_summary unchanged.
    """
    year = as_of.year
    if year not in RATES_BY_YEAR:
        raise UnsupportedTaxYearError(
            f"Tax year {year} is not configured."
        )

    all_gains = compute_realised_gains(list(transactions))
    year_gains = [g for g in all_gains if g.sell_date.year == year]

    synthetic_gains = [
        _synthesize_sell_gain(pos, as_of)
        for pos in live_positions.values()
        if not pos.is_stale
    ]

    if not synthetic_gains:
        return current_summary

    return _run_pipeline_with_extra_gains(
        year=year,
        year_gains=year_gains,
        extra_gains=synthetic_gains,
        profile=profile,
        carryforward_eur_aktien=carryforward_eur_aktien,
        carryforward_eur_general=carryforward_eur_general,
        additional_dividend_income_eur=additional_dividend_income_eur,
        additional_interest_income_eur=additional_interest_income_eur,
        isin_map=isin_map,
    )
