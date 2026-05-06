from datetime import date
from decimal import Decimal

import pytest

from app.domain.fifo import SellExceedsOpenSharesError, simulate_lot_consumption
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.positions import OpenLot


def test_simulate_lot_consumption_single_lot_exact_shares():
    lot = OpenLot(
        source_transaction_id="tx_buy_1",
        ticker="NVDA.DE",
        trade_date=date(2024, 1, 1),
        remaining_shares=Decimal("10"),
        cost_per_share_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0")
    )
    sell_tx = Transaction(
        id="tx_sell_1",
        type=TransactionType.SELL,
        ticker="NVDA.DE",
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("120"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0"),
        trade_date=date(2024, 2, 1)
    )
    
    gains, remaining = simulate_lot_consumption((lot,), Decimal("10"), sell_tx)
    
    assert len(gains) == 1
    assert len(remaining) == 0
    assert gains[0].shares == Decimal("10")


def test_simulate_lot_consumption_single_lot_partial_shares():
    lot = OpenLot(
        source_transaction_id="tx_buy_1",
        ticker="NVDA.DE",
        trade_date=date(2024, 1, 1),
        remaining_shares=Decimal("10"),
        cost_per_share_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0")
    )
    sell_tx = Transaction(
        id="tx_sell_1",
        type=TransactionType.SELL,
        ticker="NVDA.DE",
        shares=Decimal("4"),
        price_native=Money(amount=Decimal("120"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0"),
        trade_date=date(2024, 2, 1)
    )
    
    gains, remaining = simulate_lot_consumption((lot,), Decimal("4"), sell_tx)
    
    assert len(gains) == 1
    assert gains[0].shares == Decimal("4")
    assert len(remaining) == 1
    assert remaining[0].remaining_shares == Decimal("6")


def test_simulate_lot_consumption_multiple_lots_crosses_boundary():
    lot1 = OpenLot(
        source_transaction_id="tx_buy_1",
        ticker="NVDA.DE",
        trade_date=date(2024, 1, 1),
        remaining_shares=Decimal("5"),
        cost_per_share_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0")
    )
    lot2 = OpenLot(
        source_transaction_id="tx_buy_2",
        ticker="NVDA.DE",
        trade_date=date(2024, 1, 15),
        remaining_shares=Decimal("5"),
        cost_per_share_native=Money(amount=Decimal("110"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0")
    )
    sell_tx = Transaction(
        id="tx_sell_1",
        type=TransactionType.SELL,
        ticker="NVDA.DE",
        shares=Decimal("7"),
        price_native=Money(amount=Decimal("120"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0"),
        trade_date=date(2024, 2, 1)
    )
    
    gains, remaining = simulate_lot_consumption((lot1, lot2), Decimal("7"), sell_tx)
    
    assert len(gains) == 2
    assert gains[0].shares == Decimal("5")
    assert gains[0].buy_transaction_id == "tx_buy_1"
    assert gains[1].shares == Decimal("2")
    assert gains[1].buy_transaction_id == "tx_buy_2"
    
    assert len(remaining) == 1
    assert remaining[0].remaining_shares == Decimal("3")
    assert remaining[0].source_transaction_id == "tx_buy_2"


def test_simulate_lot_consumption_over_sell():
    lot = OpenLot(
        source_transaction_id="tx_buy_1",
        ticker="NVDA.DE",
        trade_date=date(2024, 1, 1),
        remaining_shares=Decimal("5"),
        cost_per_share_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0")
    )
    sell_tx = Transaction(
        id="tx_sell_1",
        type=TransactionType.SELL,
        ticker="NVDA.DE",
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("120"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0"),
        trade_date=date(2024, 2, 1)
    )
    
    with pytest.raises(SellExceedsOpenSharesError, match="exceeds open position"):
        simulate_lot_consumption((lot,), Decimal("10"), sell_tx)


def test_simulate_lot_consumption_empty_lots():
    sell_tx = Transaction(
        id="tx_sell_1",
        type=TransactionType.SELL,
        ticker="NVDA.DE",
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("120"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0"),
        trade_date=date(2024, 2, 1)
    )
    
    with pytest.raises(SellExceedsOpenSharesError, match="exceeds open position of 0 shares"):
        simulate_lot_consumption((), Decimal("10"), sell_tx)


def test_simulate_lot_consumption_order_preservation():
    lot1 = OpenLot(
        source_transaction_id="tx_buy_1",
        ticker="NVDA.DE",
        trade_date=date(2024, 1, 1),
        remaining_shares=Decimal("2"),
        cost_per_share_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0")
    )
    lot2 = OpenLot(
        source_transaction_id="tx_buy_2",
        ticker="NVDA.DE",
        trade_date=date(2024, 1, 15),
        remaining_shares=Decimal("3"),
        cost_per_share_native=Money(amount=Decimal("110"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0")
    )
    lot3 = OpenLot(
        source_transaction_id="tx_buy_3",
        ticker="NVDA.DE",
        trade_date=date(2024, 1, 20),
        remaining_shares=Decimal("4"),
        cost_per_share_native=Money(amount=Decimal("115"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0")
    )
    sell_tx = Transaction(
        id="tx_sell_1",
        type=TransactionType.SELL,
        ticker="NVDA.DE",
        shares=Decimal("4"),
        price_native=Money(amount=Decimal("120"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0"),
        trade_date=date(2024, 2, 1)
    )
    
    gains, remaining = simulate_lot_consumption((lot1, lot2, lot3), Decimal("4"), sell_tx)
    
    assert len(gains) == 2
    assert gains[0].shares == Decimal("2")
    assert gains[1].shares == Decimal("2")
    
    assert len(remaining) == 2
    assert remaining[0].remaining_shares == Decimal("1")
    assert remaining[0].source_transaction_id == "tx_buy_2"
    assert remaining[1].remaining_shares == Decimal("4")
    assert remaining[1].source_transaction_id == "tx_buy_3"

