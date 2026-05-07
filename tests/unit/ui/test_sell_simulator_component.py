"""Unit tests for the sell simulator component helpers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.services.sell_simulator import SellSimulationRequest
from app.ui.components import sell_simulator as component

_EUR = Currency.EUR


def _request(ticker: str, shares: str = "5", price: str = "120") -> SellSimulationRequest:
    return SellSimulationRequest(
        ticker=ticker,
        shares=Decimal(shares),
        sell_price_native=Money(amount=Decimal(price), currency=_EUR),
        sell_fx_rate_eur=Decimal("1"),
        sell_date=date(2026, 5, 1),
    )


def _buy(tx_id: str) -> Transaction:
    return Transaction(
        id=tx_id,
        type=TransactionType.BUY,
        ticker="RHM.DE",
        trade_date=date(2026, 1, 1),
        shares=Decimal("1"),
        price_native=Money(amount=Decimal("100"), currency=_EUR),
        fx_rate_eur=Decimal("1"),
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


class TestLivePositionsCache:
    def test_same_transaction_ids_reuse_cached_live_positions(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        component._live_positions_cached.clear()

        class Repo:
            def load_all(self) -> list[Transaction]:
                return [_buy("tx-1")]

        calls = 0

        def fake_compute_live_positions(*args: object) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {"RHM.DE": object()}

        monkeypatch.setattr(component, "get_repository", lambda: Repo())
        monkeypatch.setattr(component, "get_price_provider", lambda: object())
        monkeypatch.setattr(component, "get_fx_provider", lambda: object())
        monkeypatch.setattr(component, "compute_live_positions", fake_compute_live_positions)

        try:
            component._live_positions_cached(("tx-1",))
            component._live_positions_cached(("tx-1",))

            assert calls == 1
        finally:
            component._live_positions_cached.clear()

    def test_changed_transaction_ids_invalidate_live_positions_cache(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        component._live_positions_cached.clear()

        class Repo:
            def load_all(self) -> list[Transaction]:
                return [_buy("tx-2")]

        calls = 0

        def fake_compute_live_positions(*args: object) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {"RHM.DE": object()}

        monkeypatch.setattr(component, "get_repository", lambda: Repo())
        monkeypatch.setattr(component, "get_price_provider", lambda: object())
        monkeypatch.setattr(component, "get_fx_provider", lambda: object())
        monkeypatch.setattr(component, "compute_live_positions", fake_compute_live_positions)

        try:
            component._live_positions_cached(("tx-1",))
            component._live_positions_cached(("tx-2",))

            assert calls == 2
        finally:
            component._live_positions_cached.clear()
