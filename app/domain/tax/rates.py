"""Year-keyed German capital-gains tax rate constants.

Legal references:
- Abgeltungsteuer 25%: § 32d Abs. 1 EStG
- Solidaritätszuschlag 5.5% of tax: § 4 SolZG
- Sparerpauschbetrag €1,000 / €2,000: § 20 Abs. 9 EStG (as of 2023 reform)
- Teilfreistellung for Investmentfonds: § 20 InvStG
  AKTIENFONDS 30%, MISCHFONDS 15%, IMMOBILIENFONDS 60%, IMMOBILIEN_AUSLAND 80%
- Aktien (direct equity), Rentenfonds, Sonstige: no Teilfreistellung (0%)

Source: https://www.gesetze-im-internet.de/estg/__32d.html
        https://www.gesetze-im-internet.de/invstg_2018/__20.html
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.domain.money import Currency, Money
from app.domain.tax.classification import InstrumentKind


class UnsupportedTaxYearError(Exception):
    """Raised when the requested tax year has no configured rate table."""

    pass


class TaxYearRates(BaseModel):
    """Frozen set of tax rates for a single fiscal year."""

    model_config = ConfigDict(frozen=True)

    sparerpauschbetrag_single: Money
    sparerpauschbetrag_joint: Money
    abgeltungsteuer_rate: Decimal
    solidaritaetszuschlag_rate: Decimal
    teilfreistellung: dict[InstrumentKind, Decimal]


TAX_RATES_2025: TaxYearRates = TaxYearRates(
    sparerpauschbetrag_single=Money(amount=Decimal("1000"), currency=Currency.EUR),
    sparerpauschbetrag_joint=Money(amount=Decimal("2000"), currency=Currency.EUR),
    abgeltungsteuer_rate=Decimal("0.25"),
    solidaritaetszuschlag_rate=Decimal("0.055"),
    teilfreistellung={
        InstrumentKind.AKTIE: Decimal("0.00"),
        InstrumentKind.AKTIENFONDS: Decimal("0.30"),
        InstrumentKind.MISCHFONDS: Decimal("0.15"),
        InstrumentKind.IMMOBILIENFONDS: Decimal("0.60"),
        InstrumentKind.IMMOBILIENFONDS_AUSLAND: Decimal("0.80"),
        InstrumentKind.RENTENFONDS: Decimal("0.00"),
        InstrumentKind.SONSTIGE: Decimal("0.00"),
        InstrumentKind.DIVIDENDE: Decimal("0.00"),
        InstrumentKind.ZINSEN: Decimal("0.00"),
    },
)

TAX_RATES_2026: TaxYearRates = TaxYearRates(
    sparerpauschbetrag_single=Money(amount=Decimal("1000"), currency=Currency.EUR),
    sparerpauschbetrag_joint=Money(amount=Decimal("2000"), currency=Currency.EUR),
    abgeltungsteuer_rate=Decimal("0.25"),
    solidaritaetszuschlag_rate=Decimal("0.055"),
    teilfreistellung={
        InstrumentKind.AKTIE: Decimal("0.00"),
        InstrumentKind.AKTIENFONDS: Decimal("0.30"),
        InstrumentKind.MISCHFONDS: Decimal("0.15"),
        InstrumentKind.IMMOBILIENFONDS: Decimal("0.60"),
        InstrumentKind.IMMOBILIENFONDS_AUSLAND: Decimal("0.80"),
        InstrumentKind.RENTENFONDS: Decimal("0.00"),
        InstrumentKind.SONSTIGE: Decimal("0.00"),
        InstrumentKind.DIVIDENDE: Decimal("0.00"),
        InstrumentKind.ZINSEN: Decimal("0.00"),
    },
)

RATES_BY_YEAR: dict[int, TaxYearRates] = {
    2025: TAX_RATES_2025,
    2026: TAX_RATES_2026,
}
