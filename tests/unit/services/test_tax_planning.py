# ruff: noqa: E501
"""Unit tests for app.services.tax_planning."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.positions import LivePosition, OpenLot, Position
from app.domain.tax.classification import InstrumentKind
from app.domain.tax.engine import compute_tax_year_summary
from app.domain.tax.models import FilingStatus, TaxProfile, TaxYearSummary
from app.services.tax_planning import (
    compute_current_tax_summary,
    compute_per_position_harvest_impact,
    compute_tax_if_full_liquidation,
)

_EUR = Currency.EUR
_USD = Currency.USD
_SINGLE = TaxProfile(filing_status=FilingStatus.SINGLE)
_AS_OF = datetime(2026, 6, 1, 12, 0)


def _m(v: str, ccy: Currency = _EUR) -> Money:
    return Money(amount=Decimal(v), currency=ccy)


def _eur(v: str) -> Money:
    return _m(v, _EUR)


def _buy(ticker: str, d: str, shares: str, price: str, ccy: Currency = _EUR, fx: str = "1") -> Transaction:
    return Transaction(
        ticker=ticker,
        type=TransactionType.BUY,
        trade_date=date.fromisoformat(d),
        shares=Decimal(shares),
        price_native=Money(amount=Decimal(price), currency=ccy),
        fx_rate_eur=Decimal(fx),
    )


def _sell(ticker: str, d: str, shares: str, price: str, ccy: Currency = _EUR, fx: str = "1") -> Transaction:
    return Transaction(
        ticker=ticker,
        type=TransactionType.SELL,
        trade_date=date.fromisoformat(d),
        shares=Decimal(shares),
        price_native=Money(amount=Decimal(price), currency=ccy),
        fx_rate_eur=Decimal(fx),
    )


def _live_pos(
    ticker: str,
    cost_eur: str,
    live_value_eur: str | None,
    shares: str = "10",
    ccy: Currency = _EUR,
) -> LivePosition:
    """Build a LivePosition with cost_per_share derived from cost_eur/shares."""
    trade_date = date(2025, 1, 1)
    n_shares = Decimal(shares)
    cost_per_share = Decimal(cost_eur) / n_shares
    lot = OpenLot(
        source_transaction_id=f"t-{ticker}",
        ticker=ticker,
        trade_date=trade_date,
        remaining_shares=n_shares,
        cost_per_share_native=Money(amount=cost_per_share, currency=ccy),
        fx_rate_eur=Decimal("1"),
    )
    pos = Position(
        ticker=ticker,
        open_shares=n_shares,
        open_lots=(lot,),
        realised_gain_eur_ytd=_eur("0"),
        cost_basis_eur=_eur(cost_eur),
    )
    if live_value_eur is None:
        return LivePosition(
            position=pos,
            live_price_native=None,
            live_value_eur=None,
            unrealised_gain_eur=None,
            unrealised_gain_pct=None,
            current_fx_rate=None,
            staleness_reason="Price unavailable",
        )
    gain_amount = Decimal(live_value_eur) - Decimal(cost_eur)
    gain_pct = gain_amount / Decimal(cost_eur) * Decimal("100") if Decimal(cost_eur) != 0 else Decimal("0")
    live_price = Decimal(live_value_eur) / n_shares
    return LivePosition(
        position=pos,
        live_price_native=Money(amount=live_price, currency=ccy),
        live_value_eur=_eur(live_value_eur),
        unrealised_gain_eur=Money(amount=gain_amount, currency=_EUR),
        unrealised_gain_pct=gain_pct,
        current_fx_rate=Decimal("1"),
        staleness_reason=None,
    )


def _zero_summary(year: int = 2026) -> TaxYearSummary:
    """Tax summary with no gains — full allowance available."""
    return compute_tax_year_summary(
        year=year,
        transactions=[],
        profile=_SINGLE,
    )


# ---------------------------------------------------------------------------
# compute_current_tax_summary
# ---------------------------------------------------------------------------

def test_compute_current_tax_summary_passthrough() -> None:
    """compute_current_tax_summary is a thin wrapper; output matches the engine directly."""
    txs = [
        _buy("NVDA", "2025-01-01", "10", "100", _USD, "0.9"),
        _sell("NVDA", "2026-03-01", "5", "120", _USD, "0.91"),
    ]
    engine_result = compute_tax_year_summary(
        year=2026,
        transactions=txs,
        profile=_SINGLE,
        prior_year_aktien_carryforward_eur=_eur("0"),
        prior_year_general_carryforward_eur=_eur("0"),
        additional_dividend_income_eur=_eur("0"),
        additional_interest_income_eur=_eur("0"),
    )
    service_result = compute_current_tax_summary(
        transactions=txs,
        profile=_SINGLE,
        carryforward_eur_aktien=_eur("0"),
        carryforward_eur_general=_eur("0"),
        additional_dividend_income_eur=_eur("0"),
        additional_interest_income_eur=_eur("0"),
        as_of=datetime(2026, 12, 31),
    )
    assert service_result == engine_result


# ---------------------------------------------------------------------------
# compute_per_position_harvest_impact
# ---------------------------------------------------------------------------

def test_harvest_single_position_fully_sheltered() -> None:
    """€500 unrealised AKTIE gain with €1,000 allowance → incremental tax = €0, sheltered."""
    summary = _zero_summary()
    live_pos = _live_pos("NVDA", cost_eur="1000", live_value_eur="1500")
    report = compute_per_position_harvest_impact(
        transactions=[],
        live_positions={"NVDA": live_pos},
        current_summary=summary,
        profile=_SINGLE,
        carryforward_eur_aktien=_eur("0"),
        carryforward_eur_general=_eur("0"),
        additional_dividend_income_eur=_eur("0"),
        additional_interest_income_eur=_eur("0"),
        as_of=_AS_OF,
    )
    assert "NVDA" in report.impacts
    imp = report.impacts["NVDA"]
    assert imp.is_fully_sheltered is True
    assert imp.incremental_tax_eur.amount == Decimal("0")
    assert imp.total_incremental_eur.amount == Decimal("0")
    assert not report.stale_tickers


def test_harvest_partial_shelter() -> None:
    """€1,500 unrealised AKTIE gain with €1,000 allowance → marginal tax on €500."""
    summary = _zero_summary()
    live_pos = _live_pos("NVDA", cost_eur="500", live_value_eur="2000")
    report = compute_per_position_harvest_impact(
        transactions=[],
        live_positions={"NVDA": live_pos},
        current_summary=summary,
        profile=_SINGLE,
        carryforward_eur_aktien=_eur("0"),
        carryforward_eur_general=_eur("0"),
        additional_dividend_income_eur=_eur("0"),
        additional_interest_income_eur=_eur("0"),
        as_of=_AS_OF,
    )
    imp = report.impacts["NVDA"]
    assert imp.is_fully_sheltered is False
    # AKTIE: 0% Teilfreistellung → taxable = €1,500. Sheltered by €1,000.
    # Net taxable = €500. Abgeltungsteuer = €125. Soli = €6.875.
    assert imp.incremental_tax_eur.amount == pytest.approx(Decimal("125"), abs=Decimal("1"))
    assert imp.incremental_soli_eur.amount == pytest.approx(Decimal("6.875"), abs=Decimal("0.1"))
    assert imp.total_incremental_eur.amount == pytest.approx(Decimal("131.875"), abs=Decimal("1"))


def test_harvest_etf_teilfreistellung_no_allowance() -> None:
    """AKTIENFONDS (30% Teilfreistellung), €1,000 gain, €0 allowance remaining."""
    # Consume the full €1,000 allowance with an existing RHM.DE (EUR AKTIE) sell.
    existing_txs = [
        _buy("RHM.DE", "2025-01-01", "10", "100"),
        _sell("RHM.DE", "2026-01-15", "10", "200"),  # gain = €1,000 → consumes full allowance
    ]
    summary = compute_current_tax_summary(
        transactions=existing_txs,
        profile=_SINGLE,
        carryforward_eur_aktien=_eur("0"),
        carryforward_eur_general=_eur("0"),
        additional_dividend_income_eur=_eur("0"),
        additional_interest_income_eur=_eur("0"),
        as_of=datetime(2026, 12, 31),
    )
    assert summary.sparerpauschbetrag_remaining_eur.amount == Decimal("0")

    live_pos = _live_pos("VUSA.DE", cost_eur="1000", live_value_eur="2000")
    report = compute_per_position_harvest_impact(
        transactions=existing_txs,
        live_positions={"VUSA.DE": live_pos},
        current_summary=summary,
        profile=_SINGLE,
        carryforward_eur_aktien=_eur("0"),
        carryforward_eur_general=_eur("0"),
        additional_dividend_income_eur=_eur("0"),
        additional_interest_income_eur=_eur("0"),
        as_of=_AS_OF,
    )
    imp = report.impacts["VUSA.DE"]
    assert imp.instrument_kind == InstrumentKind.AKTIENFONDS
    # 30% Teilfreistellung → taxable = €700
    assert imp.taxable_gain_after_teilfreistellung_eur.amount == pytest.approx(Decimal("700"), abs=Decimal("1"))
    # All €700 taxable at 25% → €175 + soli €9.625
    assert imp.incremental_tax_eur.amount == pytest.approx(Decimal("175"), abs=Decimal("1"))
    assert imp.incremental_soli_eur.amount == pytest.approx(Decimal("9.625"), abs=Decimal("0.1"))
    assert imp.is_fully_sheltered is False


def test_harvest_stale_position_excluded() -> None:
    """Stale position excluded from impacts; appears in stale_tickers."""
    summary = _zero_summary()
    live_good = _live_pos("NVDA", cost_eur="1000", live_value_eur="1200")
    live_stale = _live_pos("RHM.DE", cost_eur="500", live_value_eur=None)
    report = compute_per_position_harvest_impact(
        transactions=[],
        live_positions={"NVDA": live_good, "RHM.DE": live_stale},
        current_summary=summary,
        profile=_SINGLE,
        carryforward_eur_aktien=_eur("0"),
        carryforward_eur_general=_eur("0"),
        additional_dividend_income_eur=_eur("0"),
        additional_interest_income_eur=_eur("0"),
        as_of=_AS_OF,
    )
    assert "NVDA" in report.impacts
    assert "RHM.DE" not in report.impacts
    assert "RHM.DE" in report.stale_tickers


# ---------------------------------------------------------------------------
# compute_tax_if_full_liquidation
# ---------------------------------------------------------------------------

def test_full_liquidation_three_positions() -> None:
    """Full liquidation: result should equal engine run with all synthetic gains."""
    summary = _zero_summary()
    pos1 = _live_pos("NVDA", cost_eur="1000", live_value_eur="1200")
    pos2 = _live_pos("ETN", cost_eur="500", live_value_eur="700")
    pos3 = _live_pos("VUSA.DE", cost_eur="2000", live_value_eur="2500")
    live_positions = {"NVDA": pos1, "ETN": pos2, "VUSA.DE": pos3}

    liq = compute_tax_if_full_liquidation(
        transactions=[],
        live_positions=live_positions,
        current_summary=summary,
        profile=_SINGLE,
        carryforward_eur_aktien=_eur("0"),
        carryforward_eur_general=_eur("0"),
        additional_dividend_income_eur=_eur("0"),
        additional_interest_income_eur=_eur("0"),
        as_of=_AS_OF,
    )
    # Combined gain: NVDA €200 (AKTIE), ETN €200 (AKTIE), VUSA.DE €500 (AKTIENFONDS 30% TF → €350 taxable)
    # Total AKTIE taxable: €400. General-pot (VUSA.DE goes to general pot): €350.
    # Total taxable = €750. Allowance €1,000 → fully sheltered.
    assert liq.total_tax_owed_eur.amount == Decimal("0")
    assert liq.sparerpauschbetrag_consumed_eur.amount == pytest.approx(Decimal("750"), abs=Decimal("2"))


def test_full_liquidation_all_stale_returns_current_summary() -> None:
    """All stale positions → liquidation summary is the same object as current_summary."""
    summary = _zero_summary()
    stale1 = _live_pos("NVDA", cost_eur="1000", live_value_eur=None)
    stale2 = _live_pos("ETN", cost_eur="500", live_value_eur=None, ccy=_USD)
    result = compute_tax_if_full_liquidation(
        transactions=[],
        live_positions={"NVDA": stale1, "ETN": stale2},
        current_summary=summary,
        profile=_SINGLE,
        carryforward_eur_aktien=_eur("0"),
        carryforward_eur_general=_eur("0"),
        additional_dividend_income_eur=_eur("0"),
        additional_interest_income_eur=_eur("0"),
        as_of=_AS_OF,
    )
    assert result is summary
