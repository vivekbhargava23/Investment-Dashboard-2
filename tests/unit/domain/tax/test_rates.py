"""Tests for app/domain/tax/rates.py."""

from decimal import Decimal

import pytest

from app.domain.money import Currency, Money
from app.domain.tax.classification import InstrumentKind
from app.domain.tax.rates import RATES_BY_YEAR, TAX_RATES_2025, TAX_RATES_2026


def test_2026_sparerpauschbetrag_single() -> None:
    assert TAX_RATES_2026.sparerpauschbetrag_single == Money(
        amount=Decimal("1000"), currency=Currency.EUR
    )


def test_2026_sparerpauschbetrag_joint() -> None:
    assert TAX_RATES_2026.sparerpauschbetrag_joint == Money(
        amount=Decimal("2000"), currency=Currency.EUR
    )


def test_2025_sparerpauschbetrag_single() -> None:
    assert TAX_RATES_2025.sparerpauschbetrag_single == Money(
        amount=Decimal("1000"), currency=Currency.EUR
    )


def test_2025_sparerpauschbetrag_joint() -> None:
    assert TAX_RATES_2025.sparerpauschbetrag_joint == Money(
        amount=Decimal("2000"), currency=Currency.EUR
    )


def test_soli_rate_is_five_point_five_percent() -> None:
    # 0.055, NOT 5.5, NOT 0.0055. Regression guard.
    assert TAX_RATES_2026.solidaritaetszuschlag_rate == Decimal("0.055")
    assert TAX_RATES_2025.solidaritaetszuschlag_rate == Decimal("0.055")


def test_abgeltungsteuer_rate_is_25_percent() -> None:
    assert TAX_RATES_2026.abgeltungsteuer_rate == Decimal("0.25")


def test_teilfreistellung_aktie_is_zero() -> None:
    assert TAX_RATES_2026.teilfreistellung[InstrumentKind.AKTIE] == Decimal("0.00")


def test_teilfreistellung_aktienfonds_is_30_percent() -> None:
    assert TAX_RATES_2026.teilfreistellung[InstrumentKind.AKTIENFONDS] == Decimal("0.30")


def test_teilfreistellung_mischfonds_is_15_percent() -> None:
    assert TAX_RATES_2026.teilfreistellung[InstrumentKind.MISCHFONDS] == Decimal("0.15")


def test_unknown_year_raises_key_error() -> None:
    with pytest.raises(KeyError):
        _ = RATES_BY_YEAR[2099]


def test_both_known_years_present() -> None:
    assert 2025 in RATES_BY_YEAR
    assert 2026 in RATES_BY_YEAR


def test_dividende_and_zinsen_have_zero_teilfreistellung() -> None:
    tf = TAX_RATES_2026.teilfreistellung
    assert tf[InstrumentKind.DIVIDENDE] == Decimal("0.00")
    assert tf[InstrumentKind.ZINSEN] == Decimal("0.00")
