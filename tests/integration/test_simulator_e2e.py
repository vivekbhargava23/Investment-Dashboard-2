"""End-to-end tests for the sell simulator service (no network, no Streamlit)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.tax.models import FilingStatus, TaxProfile
from app.services.sell_simulator import SellSimulationRequest, simulate_sell

_EUR = Currency.EUR
_USD = Currency.USD
_SINGLE = TaxProfile(filing_status=FilingStatus.SINGLE)


def _eur(v: str) -> Money:
    return Money(amount=Decimal(v), currency=_EUR)


def _buy(ticker: str, d: str, shares: str, price_eur: str) -> Transaction:
    return Transaction(
        ticker=ticker,
        type=TransactionType.BUY,
        trade_date=date.fromisoformat(d),
        shares=Decimal(shares),
        price_native=Money(amount=Decimal(price_eur), currency=_EUR),
        fx_rate_eur=Decimal("1"),
    )


class TestSimulatorE2E:
    def test_valid_sell_has_all_sections(self) -> None:
        txs = [_buy("NVDA", "2025-01-01", "10", "100")]
        req = SellSimulationRequest(
            ticker="NVDA",
            shares=Decimal("5"),
            sell_price_native=_eur("120"),
            sell_fx_rate_eur=Decimal("1"),
            sell_date=date(2026, 5, 1),
        )
        sim = simulate_sell(req, txs, _SINGLE, {})

        assert sim.is_valid
        assert sim.validation_error is None
        assert len(sim.lot_consumption) >= 1
        assert sim.total_realised_gain_eur.amount == Decimal("100")
        assert sim.marginal_tax is not None
        assert sim.position_after is not None
        assert sim.position_after.open_shares_after == Decimal("5")

    def test_invalid_sell_shows_error_no_impact_sections(self) -> None:
        txs = [_buy("NVDA", "2025-01-01", "5", "100")]
        req = SellSimulationRequest(
            ticker="NVDA",
            shares=Decimal("20"),  # over-sell
            sell_price_native=_eur("120"),
            sell_fx_rate_eur=Decimal("1"),
            sell_date=date(2026, 5, 1),
        )
        sim = simulate_sell(req, txs, _SINGLE, {})

        assert not sim.is_valid
        assert sim.validation_error is not None
        assert sim.lot_consumption == ()
        assert sim.marginal_tax is None
        assert sim.position_after is None

    def test_handoff_request_roundtrip(self) -> None:
        """SellSimulationRequest can be stored and restored from session_state."""
        req = SellSimulationRequest(
            ticker="NVDA",
            shares=Decimal("3"),
            sell_price_native=_eur("130"),
            sell_fx_rate_eur=Decimal("1"),
            sell_date=date(2026, 5, 1),
        )
        dumped = req.model_dump()
        restored = SellSimulationRequest.model_validate(dumped)
        assert restored.ticker == "NVDA"
        assert restored.shares == Decimal("3")
        assert restored.sell_date == date(2026, 5, 1)
