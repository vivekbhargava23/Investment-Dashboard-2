"""Public entry point for the German capital-gains tax engine."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.domain.fifo import compute_realised_gains
from app.domain.isin_map import IsinMapDocument
from app.domain.models import Transaction
from app.domain.money import Currency, CurrencyMismatchError, Money
from app.domain.tax.models import TaxProfile, TaxYearSummary
from app.domain.tax.pipeline import TaxYearLedger, run_pipeline
from app.domain.tax.rates import RATES_BY_YEAR, UnsupportedTaxYearError

_EUR = Currency.EUR


def compute_tax_year_summary(
    year: int,
    transactions: Sequence[Transaction],
    profile: TaxProfile,
    isin_map: IsinMapDocument = IsinMapDocument(),
    prior_year_aktien_carryforward_eur: Money = Money(
        amount=Decimal("0"), currency=Currency.EUR
    ),
    prior_year_general_carryforward_eur: Money = Money(
        amount=Decimal("0"), currency=Currency.EUR
    ),
    additional_dividend_income_eur: Money = Money(
        amount=Decimal("0"), currency=Currency.EUR
    ),
    additional_interest_income_eur: Money = Money(
        amount=Decimal("0"), currency=Currency.EUR
    ),
) -> TaxYearSummary:
    """
    Compute a fully-resolved tax summary for a single fiscal year.

    Pure function: same inputs → same output. No I/O, no datetime.now().

    Raises:
        UnsupportedTaxYearError: if `year` has no configured rate table.
        CurrencyMismatchError: if any Money parameter is not EUR.
        InstrumentClassificationError: if any RealisedGain's ticker is unclassified.
    """
    if year not in RATES_BY_YEAR:
        raise UnsupportedTaxYearError(
            f"Tax year {year} is not configured. "
            f"Add it to app/domain/tax/rates.py."
        )

    for param_name, money in (
        ("prior_year_aktien_carryforward_eur", prior_year_aktien_carryforward_eur),
        ("prior_year_general_carryforward_eur", prior_year_general_carryforward_eur),
        ("additional_dividend_income_eur", additional_dividend_income_eur),
        ("additional_interest_income_eur", additional_interest_income_eur),
    ):
        if money.currency != _EUR:
            raise CurrencyMismatchError(
                f"{param_name} must be EUR, got {money.currency}"
            )

    rates = RATES_BY_YEAR[year]
    all_gains = compute_realised_gains(list(transactions))
    year_gains = [g for g in all_gains if g.sell_date.year == year]

    ledger = TaxYearLedger(
        year=year,
        rates=rates,
        profile=profile,
        realised_gains=year_gains,
        prior_aktien_carryforward=prior_year_aktien_carryforward_eur,
        prior_general_carryforward=prior_year_general_carryforward_eur,
        additional_dividend_income_eur=additional_dividend_income_eur,
        additional_interest_income_eur=additional_interest_income_eur,
        isin_map=isin_map,
    )
    return run_pipeline(ledger)
