"""Unit tests for the sell simulator component helpers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.money import Currency, Money
from app.services.sell_simulator import SellSimulationRequest

_EUR = Currency.EUR


def _request(ticker: str, shares: str = "5", price: str = "120") -> SellSimulationRequest:
    return SellSimulationRequest(
        ticker=ticker,
        shares=Decimal(shares),
        sell_price_native=Money(amount=Decimal(price), currency=_EUR),
        sell_fx_rate_eur=Decimal("1"),
        sell_date=date(2026, 5, 1),
    )


class TestSellSimulationRequest:
    def test_round_trip_fields(self) -> None:
        req = _request("NVDA", "7", "130")
        assert req.ticker == "NVDA"
        assert req.shares == Decimal("7")
        assert req.sell_price_native.amount == Decimal("130")
        assert req.sell_date == date(2026, 5, 1)

    def test_frozen(self) -> None:
        req = _request("NVDA")
        with pytest.raises(Exception):
            req.ticker = "AAPL"  # type: ignore[misc]

    def test_session_state_handoff_serialisable(self) -> None:
        """Request stored in st.session_state must survive a Pydantic round-trip."""
        req = _request("NVDA", "3", "115")
        dumped = req.model_dump()
        restored = SellSimulationRequest.model_validate(dumped)
        assert restored == req

    def test_proceeds_calculation_consistent(self) -> None:
        """Implied EUR proceeds from request fields should match expected value."""
        req = SellSimulationRequest(
            ticker="APD",
            shares=Decimal("10"),
            sell_price_native=Money(amount=Decimal("100"), currency=Currency.USD),
            sell_fx_rate_eur=Decimal("0.9"),
            sell_date=date(2026, 5, 1),
        )
        proceeds = req.sell_price_native.amount * req.sell_fx_rate_eur * req.shares
        assert proceeds == Decimal("900")


