"""Tests for the public simulate_lot_consumption helper."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.fifo import SellExceedsOpenSharesError, simulate_lot_consumption
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.positions import OpenLot

_EUR = Currency.EUR
_USD = Currency.USD


def _lot(
    tx_id: str,
    trade_date: date,
    shares: str,
    price_usd: str,
    fx: str = "0.9",
) -> OpenLot:
    return OpenLot(
        source_transaction_id=tx_id,
        ticker="NVDA",
        trade_date=trade_date,
        remaining_shares=Decimal(shares),
        cost_per_share_native=Money(amount=Decimal(price_usd), currency=_USD),
        fx_rate_eur=Decimal(fx),
    )


def _sell_tx(shares: str, price: str = "120", fx: str = "0.9") -> Transaction:
    return Transaction(
        type=TransactionType.SELL,
        ticker="NVDA",
        trade_date=date(2026, 5, 1),
        shares=Decimal(shares),
        price_native=Money(amount=Decimal(price), currency=_USD),
        fx_rate_eur=Decimal(fx),
    )


class TestSimulateLotConsumption:
    def test_single_lot_exact_shares(self) -> None:
        lot = _lot("tx1", date(2024, 1, 1), "5", "100")
        gains, remaining = simulate_lot_consumption((lot,), Decimal("5"), _sell_tx("5"))
        assert len(gains) == 1
        assert gains[0].shares == Decimal("5")
        assert remaining == ()

    def test_single_lot_partial_shares(self) -> None:
        lot = _lot("tx1", date(2024, 1, 1), "10", "100")
        gains, remaining = simulate_lot_consumption((lot,), Decimal("3"), _sell_tx("3"))
        assert len(gains) == 1
        assert gains[0].shares == Decimal("3")
        assert len(remaining) == 1
        assert remaining[0].remaining_shares == Decimal("7")

    def test_multiple_lots_crosses_boundary(self) -> None:
        lots = (
            _lot("tx1", date(2024, 1, 1), "5", "100"),
            _lot("tx2", date(2025, 1, 1), "5", "110"),
        )
        gains, remaining = simulate_lot_consumption(lots, Decimal("7"), _sell_tx("7"))
        assert len(gains) == 2
        assert gains[0].buy_transaction_id == "tx1"
        assert gains[0].shares == Decimal("5")
        assert gains[1].buy_transaction_id == "tx2"
        assert gains[1].shares == Decimal("2")
        assert len(remaining) == 1
        assert remaining[0].remaining_shares == Decimal("3")

    def test_over_sell_raises(self) -> None:
        lot = _lot("tx1", date(2024, 1, 1), "5", "100")
        with pytest.raises(SellExceedsOpenSharesError):
            simulate_lot_consumption((lot,), Decimal("10"), _sell_tx("10"))

    def test_empty_lots_raises(self) -> None:
        with pytest.raises(SellExceedsOpenSharesError):
            simulate_lot_consumption((), Decimal("1"), _sell_tx("1"))

    def test_order_preservation(self) -> None:
        lots = (
            _lot("tx1", date(2024, 1, 1), "3", "100"),
            _lot("tx2", date(2025, 1, 1), "3", "110"),
            _lot("tx3", date(2026, 1, 1), "3", "120"),
        )
        gains, remaining = simulate_lot_consumption(lots, Decimal("4"), _sell_tx("4"))
        assert gains[0].buy_transaction_id == "tx1"
        assert gains[1].buy_transaction_id == "tx2"
        # Only tx2 and tx3 have remaining shares
        remaining_ids = {lot.source_transaction_id for lot in remaining}
        assert "tx1" not in remaining_ids

    def test_pure_does_not_mutate_input(self) -> None:
        lot = _lot("tx1", date(2024, 1, 1), "10", "100")
        original = (lot,)
        simulate_lot_consumption(original, Decimal("3"), _sell_tx("3"))
        assert original[0].remaining_shares == Decimal("10")

    def test_realised_gain_calculation(self) -> None:
        # Buy 5 NVDA at $100, FX 0.9 → cost EUR = 5 * 100 * 0.9 = 450
        # Sell 5 NVDA at $120, FX 0.9 → proceeds EUR = 5 * 120 * 0.9 = 540
        # Gain = 540 - 450 = 90
        lot = _lot("tx1", date(2024, 1, 1), "5", "100", fx="0.9")
        sell = _sell_tx("5", price="120", fx="0.9")
        gains, _ = simulate_lot_consumption((lot,), Decimal("5"), sell)
        assert len(gains) == 1
        assert gains[0].realised_gain_eur.amount == Decimal("90")
