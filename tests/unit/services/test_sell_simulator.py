from datetime import date
from decimal import Decimal

import pytest

from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.positions import LivePosition, OpenLot, Position
from app.domain.tax.models import FilingStatus, TaxProfile
from app.ports.tax_profile_repo import YearlyTaxInputs
from app.services.sell_simulator import (
    SellSimulationRequest,
    simulate_sell,
)

_EUR = Currency.EUR


def _make_buy(ticker: str, shares: str, price: str, fx: str, trade_date: date) -> Transaction:
    return Transaction(
        id=f"buy_{ticker}_{trade_date.isoformat()}_{shares}",
        type=TransactionType.BUY,
        ticker=ticker,
        shares=Decimal(shares),
        price_native=Money(amount=Decimal(price), currency=_EUR),
        fx_rate_eur=Decimal(fx),
        trade_date=trade_date,
    )


@pytest.fixture
def profile():
    return TaxProfile(filing_status=FilingStatus.SINGLE)


@pytest.fixture
def yearly_inputs():
    return YearlyTaxInputs()


@pytest.fixture
def live_positions():
    # Simple live position mapping with 1.0 fx_rate and matching price
    pos = Position(
        ticker="RHM.DE",
        open_shares=Decimal("12"),
        open_lots=(
            OpenLot(
                source_transaction_id="dummy",
                ticker="RHM.DE",
                trade_date=date(2025, 1, 1),
                remaining_shares=Decimal("12"),
                cost_per_share_native=Money(amount=Decimal("100"), currency=_EUR),
                fx_rate_eur=Decimal("1.0"),
            ),
        ),
        realised_gain_eur_ytd=Money.zero(_EUR),
        cost_basis_eur=Money(amount=Decimal("1200"), currency=_EUR),
    )
    return {
        "RHM.DE": LivePosition(
            ticker="RHM.DE",
            position=pos,
            live_price_native=Money(amount=Decimal("120"), currency=_EUR),
            current_fx_rate=Decimal("1.0"),
            is_stale=False,
            live_value_eur=Money(amount=Decimal("1440"), currency=_EUR),
            unrealised_gain_eur=Money(amount=Decimal("240"), currency=_EUR),
            unrealised_gain_pct=Decimal("20.0"),
            staleness_reason=None,
        )
    }


def test_happy_path_partial_sell_nvda(profile, yearly_inputs, live_positions):
    txs = [
        _make_buy("RHM.DE", "12", "100", "1.0", date(2026, 1, 1))
    ]
    
    req = SellSimulationRequest(
        ticker="RHM.DE",
        shares=Decimal("5"),
        sell_price_native=Money(amount=Decimal("120"), currency=_EUR),
        sell_fx_rate_eur=Decimal("1.0"),
        sell_date=date(2026, 6, 1),
    )
    
    sim = simulate_sell(req, txs, profile, yearly_inputs, live_positions)
    
    assert sim.is_valid is True
    assert len(sim.lot_consumption) == 1
    assert sim.lot_consumption[0].shares_consumed == Decimal("5")
    assert sim.total_realised_gain_eur == Money(amount=Decimal("100"), currency=_EUR)
    assert sim.marginal_tax is not None
    # 100 EUR gain, no other income, allowance 1000 -> 0 tax
    assert sim.marginal_tax.marginal_total_tax_owed_eur == Money.zero(_EUR)
    assert sim.position_after is not None
    assert sim.position_after.open_shares_after == Decimal("7")


def test_sell_crossing_two_lots(profile, yearly_inputs, live_positions):
    txs = [
        _make_buy("RHM.DE", "5", "100", "1.0", date(2026, 1, 1)),
        _make_buy("RHM.DE", "5", "110", "1.0", date(2026, 2, 1))
    ]
    
    req = SellSimulationRequest(
        ticker="RHM.DE",
        shares=Decimal("7"),
        sell_price_native=Money(amount=Decimal("130"), currency=_EUR),
        sell_fx_rate_eur=Decimal("1.0"),
        sell_date=date(2026, 6, 1),
    )
    
    sim = simulate_sell(req, txs, profile, yearly_inputs, live_positions)
    
    assert sim.is_valid is True
    assert len(sim.lot_consumption) == 2
    assert sim.lot_consumption[0].shares_consumed == Decimal("5")
    assert sim.lot_consumption[0].realised_gain_eur == Money(amount=Decimal("150"), currency=_EUR)
    
    assert sim.lot_consumption[1].shares_consumed == Decimal("2")
    assert sim.lot_consumption[1].realised_gain_eur == Money(amount=Decimal("40"), currency=_EUR)
    
    assert sim.total_realised_gain_eur == Money(amount=Decimal("190"), currency=_EUR)


def test_over_sell_error(profile, yearly_inputs, live_positions):
    txs = [
        _make_buy("RHM.DE", "5", "100", "1.0", date(2026, 1, 1))
    ]
    
    req = SellSimulationRequest(
        ticker="RHM.DE",
        shares=Decimal("10"),
        sell_price_native=Money(amount=Decimal("120"), currency=_EUR),
        sell_fx_rate_eur=Decimal("1.0"),
        sell_date=date(2026, 6, 1),
    )
    
    sim = simulate_sell(req, txs, profile, yearly_inputs, live_positions)
    
    assert sim.is_valid is False
    assert "10" in sim.validation_error
    assert "5" in sim.validation_error


def test_no_open_position_error(profile, yearly_inputs, live_positions):
    txs = []
    
    req = SellSimulationRequest(
        ticker="RHM.DE",
        shares=Decimal("10"),
        sell_price_native=Money(amount=Decimal("120"), currency=_EUR),
        sell_fx_rate_eur=Decimal("1.0"),
        sell_date=date(2026, 6, 1),
    )
    
    sim = simulate_sell(req, txs, profile, yearly_inputs, live_positions)
    
    assert sim.is_valid is False
    assert "No open position for RHM.DE" in sim.validation_error


def test_pure_deterministic(profile, yearly_inputs, live_positions):
    txs = [
        _make_buy("RHM.DE", "12", "100", "1.0", date(2026, 1, 1))
    ]
    
    req = SellSimulationRequest(
        ticker="RHM.DE",
        shares=Decimal("5"),
        sell_price_native=Money(amount=Decimal("120"), currency=_EUR),
        sell_fx_rate_eur=Decimal("1.0"),
        sell_date=date(2026, 6, 1),
    )
    
    sim1 = simulate_sell(req, txs, profile, yearly_inputs, live_positions)
    sim2 = simulate_sell(req, txs, profile, yearly_inputs, live_positions)
    
    assert sim1 == sim2


def test_marginal_allowance_state_when_sale_exhausts_allowance(profile, yearly_inputs, live_positions):
    # Pre-existing realised gains of €600
    txs = [
        _make_buy("HY9H.F", "10", "100", "1.0", date(2026, 1, 1)),
        Transaction(
            id="sell_aapl",
            type=TransactionType.SELL,
            ticker="HY9H.F",
            shares=Decimal("10"),
            price_native=Money(amount=Decimal("160"), currency=_EUR),
            fx_rate_eur=Decimal("1.0"),
            trade_date=date(2026, 3, 1),
        ),
        _make_buy("RHM.DE", "10", "100", "1.0", date(2026, 1, 1))
    ]
    
    # Request a sell that produces €600 of gain
    req = SellSimulationRequest(
        ticker="RHM.DE",
        shares=Decimal("10"),
        sell_price_native=Money(amount=Decimal("160"), currency=_EUR),
        sell_fx_rate_eur=Decimal("1.0"),
        sell_date=date(2026, 6, 1),
    )
    
    sim = simulate_sell(req, txs, profile, yearly_inputs, live_positions)
    
    assert sim.is_valid is True
    assert sim.total_realised_gain_eur == Money(amount=Decimal("600"), currency=_EUR)
    
    assert sim.marginal_tax is not None
    assert sim.marginal_tax.marginal_allowance_consumed_eur == Money(amount=Decimal("400"), currency=_EUR)
    assert sim.marginal_tax.marginal_taxable_gain_eur == Money(amount=Decimal("200"), currency=_EUR)
    assert sim.marginal_tax.marginal_total_tax_owed_eur == Money(amount=Decimal("52.75"), currency=_EUR)


def test_aktien_vs_general_pot_interaction(profile, yearly_inputs, live_positions):
    # Pre-existing 2026 realised: €500 ETF loss
    # ETF teilfreistellung = 30% -> €350 loss in general pot
    txs = [
        _make_buy("VUSA.DE", "10", "100", "1.0", date(2026, 1, 1)),
        Transaction(
            id="sell_etf",
            type=TransactionType.SELL,
            ticker="VUSA.DE",
            shares=Decimal("10"),
            price_native=Money(amount=Decimal("50"), currency=_EUR),
            fx_rate_eur=Decimal("1.0"),
            trade_date=date(2026, 3, 1),
        ),
        _make_buy("RHM.DE", "10", "100", "1.0", date(2026, 1, 1))
    ]
    
    # Request: sell RHM.DE (AKTIE) with €500 gain
    req = SellSimulationRequest(
        ticker="RHM.DE",
        shares=Decimal("10"),
        sell_price_native=Money(amount=Decimal("150"), currency=_EUR),
        sell_fx_rate_eur=Decimal("1.0"),
        sell_date=date(2026, 6, 1),
    )
    
    sim = simulate_sell(req, txs, profile, yearly_inputs, live_positions)
    
    assert sim.is_valid is True
    assert sim.marginal_tax is not None
    # 500 gain added to aktien pot
    # General pot's 350 loss remains.
    # Allowance (1000) applies to the 500 aktien gain -> 0 taxable.
    assert sim.marginal_tax.marginal_total_tax_owed_eur == Money.zero(_EUR)

