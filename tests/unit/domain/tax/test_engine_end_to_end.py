"""End-to-end tests for compute_tax_year_summary using deterministic fixtures."""

from __future__ import annotations

import random
from decimal import Decimal

import pytest

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, CurrencyMismatchError, Money
from app.domain.tax.classification import InstrumentClassificationError, InstrumentKind
from app.domain.tax.engine import compute_tax_year_summary
from app.domain.tax.models import FilingStatus, TaxProfile
from app.domain.tax.rates import UnsupportedTaxYearError

_EUR = Currency.EUR
_USD = Currency.USD
_SINGLE = TaxProfile(filing_status=FilingStatus.SINGLE)

_SEED_MAP = IsinMapDocument(entries={
    "ISIN-ETN": IsinMapping(
        ticker="ETN", name="ETN", status="mapped", instrument_kind=InstrumentKind.AKTIE
    ),
    "ISIN-HY9H.F": IsinMapping(
        ticker="HY9H.F", name="HY9H.F", status="mapped", instrument_kind=InstrumentKind.AKTIE
    ),
})


def _m(value: str, currency: Currency = _EUR) -> Money:
    return Money(amount=Decimal(value), currency=currency)


def _tx(
    type_: TransactionType,
    ticker: str,
    date_str: str,
    shares: str,
    price: str,
    currency: Currency,
    fx: str,
) -> Transaction:
    from datetime import date

    return Transaction(
        type=type_,
        ticker=ticker,
        trade_date=date.fromisoformat(date_str),
        shares=Decimal(shares),
        price_native=Money(amount=Decimal(price), currency=currency),
        fx_rate_eur=Decimal(fx),
    )


def _seed_transactions() -> list[Transaction]:
    """
    ETN: buy 5 @ $320 FX 0.93, sell 1 @ $340 FX 0.918, sell 1 @ $355 FX 0.92
    HY9H.F: buy 1 @ €178.50, sell 1 @ €165.00 (2026-01-02)
    """
    return [
        _tx(TransactionType.BUY, "ETN", "2025-01-15", "5", "320.00", _USD, "0.93"),
        _tx(TransactionType.SELL, "ETN", "2026-03-12", "1", "340.00", _USD, "0.918"),
        _tx(TransactionType.SELL, "ETN", "2026-05-01", "1", "355.00", _USD, "0.92"),
        _tx(TransactionType.BUY, "HY9H.F", "2025-03-01", "1", "178.50", _EUR, "1"),
        _tx(TransactionType.SELL, "HY9H.F", "2026-01-02", "1", "165.00", _EUR, "1"),
    ]


def test_seed_2026_gains_total_tax_zero() -> None:
    """
    ETN sell 1: proceeds = 340 × 0.918 = €312.12, cost = 320 × 0.93 = €297.60, gain = €14.52
    ETN sell 2: proceeds = 355 × 0.92 = €326.60, cost = €297.60, gain = €29.00
    HY9H.F sell: proceeds = €165.00, cost = €178.50, loss = -€13.50
    Both are AKTIE → aktien_pot.
    Total gains = €43.52, losses = €13.50 → taxable = €30.02
    Allowance €1,000 covers it entirely → total_tax = €0.00
    """
    txs = _seed_transactions()
    summary = compute_tax_year_summary(2026, txs, _SINGLE, isin_map=_SEED_MAP)

    assert len(summary.realised_gain_impacts) == 3

    aktien_gains_eur = Decimal("43.52")
    aktien_losses_eur = Decimal("13.50")
    taxable = aktien_gains_eur - aktien_losses_eur  # €30.02

    assert abs(
        summary.aktien_pot.current_year_gains_eur.amount - aktien_gains_eur
    ) < Decimal("0.01")
    assert abs(
        summary.aktien_pot.current_year_losses_eur.amount - aktien_losses_eur
    ) < Decimal("0.01")
    assert abs(summary.aktien_pot.taxable_after_offset_eur.amount - taxable) < Decimal("0.01")
    assert abs(summary.sparerpauschbetrag_consumed_eur.amount - taxable) < Decimal("0.01")
    assert abs(
        summary.sparerpauschbetrag_remaining_eur.amount - (Decimal("1000") - taxable)
    ) < Decimal("0.01")

    assert summary.total_tax_owed_eur == Money(
        amount=Decimal("0"), currency=_EUR
    )


def test_empty_year_returns_zero_summary() -> None:
    # No sells in 2025 → all realised gains are zero
    txs = _seed_transactions()
    summary = compute_tax_year_summary(2025, txs, _SINGLE, isin_map=_SEED_MAP)

    assert summary.realised_gain_impacts == ()
    assert summary.total_tax_owed_eur == Money(amount=Decimal("0"), currency=_EUR)
    assert summary.effective_tax_rate_pct is None


def test_unclassified_ticker_raises() -> None:
    txs = [
        _tx(TransactionType.BUY, "ZZZZ", "2025-01-01", "1", "100.00", _USD, "0.90"),
        _tx(TransactionType.SELL, "ZZZZ", "2026-01-15", "1", "120.00", _USD, "0.91"),
    ]
    with pytest.raises(InstrumentClassificationError) as exc_info:
        compute_tax_year_summary(2026, txs, _SINGLE, isin_map=IsinMapDocument())
    assert "ZZZZ" in str(exc_info.value)


def test_unsupported_year_raises() -> None:
    with pytest.raises(UnsupportedTaxYearError) as exc_info:
        compute_tax_year_summary(2099, [], _SINGLE)
    assert "2099" in str(exc_info.value)


def test_determinism_shuffled_inputs() -> None:
    """Same transactions in different order must produce equal TaxYearSummary."""
    txs = _seed_transactions()
    shuffled = txs[:]
    random.seed(42)
    random.shuffle(shuffled)
    s1 = compute_tax_year_summary(2026, txs, _SINGLE, isin_map=_SEED_MAP)
    s2 = compute_tax_year_summary(2026, shuffled, _SINGLE, isin_map=_SEED_MAP)
    assert s1 == s2


def test_non_eur_carryforward_raises() -> None:
    with pytest.raises(CurrencyMismatchError):
        compute_tax_year_summary(
            2026,
            [],
            _SINGLE,
            prior_year_aktien_carryforward_eur=_m("100", _USD),
        )


def test_dividend_income_increases_tax_bill() -> None:
    """Additional dividend income adds to the general pot and affects allowance."""
    summary_no_div = compute_tax_year_summary(2026, [], _SINGLE)
    summary_with_div = compute_tax_year_summary(
        2026,
        [],
        _SINGLE,
        additional_dividend_income_eur=_m("250.00"),
    )
    # €250 < €1000 allowance → still €0 tax, but consumed amount rises
    assert summary_with_div.total_tax_owed_eur == Money(amount=Decimal("0"), currency=_EUR)
    assert (
        summary_with_div.sparerpauschbetrag_consumed_eur.amount
        > summary_no_div.sparerpauschbetrag_consumed_eur.amount
    )
    assert summary_with_div.general_pot.current_year_gains_eur == _m("250.00")

    # Dividend large enough to exceed the allowance
    summary_big_div = compute_tax_year_summary(
        2026,
        [],
        _SINGLE,
        additional_dividend_income_eur=_m("1500.00"),
    )
    # €1500 - €1000 allowance = €500 taxable → tax = €500 × 0.25 × 1.055
    assert summary_big_div.taxable_after_allowance_eur == _m("500.0000")
    expected_tax = Decimal("500.0000") * Decimal("0.25") * Decimal("1.055")
    assert abs(summary_big_div.total_tax_owed_eur.amount - expected_tax) < Decimal("0.01")
