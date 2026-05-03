from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.money import Currency, Money
from app.domain.positions import OpenLot, Position


def test_open_lot_creation_and_cost_basis():
    lot = OpenLot(
        source_transaction_id="tx-1",
        ticker="AAPL",
        trade_date=date(2024, 1, 1),
        remaining_shares=Decimal("5"),
        cost_per_share_native=Money(amount=Decimal("180"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.92"),
    )
    # 5 * 180 * 0.92 = 828
    assert lot.cost_basis_eur == Money(amount=Decimal("828"), currency=Currency.EUR)


def test_position_valid():
    lot1 = OpenLot(
        source_transaction_id="tx-1",
        ticker="SAP.DE",
        trade_date=date(2024, 1, 1),
        remaining_shares=Decimal("10"),
        cost_per_share_native=Money(amount=Decimal("150"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )
    lot2 = OpenLot(
        source_transaction_id="tx-2",
        ticker="SAP.DE",
        trade_date=date(2024, 2, 1),
        remaining_shares=Decimal("5"),
        cost_per_share_native=Money(amount=Decimal("160"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )

    pos = Position(
        ticker="SAP.DE",
        open_shares=Decimal("15"),
        open_lots=(lot1, lot2),
        realised_gain_eur_ytd=Money.zero(Currency.EUR),
        cost_basis_eur=Money(amount=Decimal("2300"), currency=Currency.EUR),
    )
    assert pos.open_shares == Decimal("15")
    # (10 * 150) + (5 * 160) = 1500 + 800 = 2300


def test_position_ticker_mismatch():
    lot1 = OpenLot(
        source_transaction_id="tx-1",
        ticker="SAP.DE",
        trade_date=date(2024, 1, 1),
        remaining_shares=Decimal("10"),
        cost_per_share_native=Money(amount=Decimal("150"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )
    with pytest.raises(ValidationError, match="Lot ticker SAP.DE does not match"):
        Position(
            ticker="AAPL",
            open_shares=Decimal("10"),
            open_lots=(lot1,),
            realised_gain_eur_ytd=Money.zero(Currency.EUR),
            cost_basis_eur=Money(amount=Decimal("1500"), currency=Currency.EUR),
        )


def test_position_shares_mismatch():
    lot1 = OpenLot(
        source_transaction_id="tx-1",
        ticker="SAP.DE",
        trade_date=date(2024, 1, 1),
        remaining_shares=Decimal("10"),
        cost_per_share_native=Money(amount=Decimal("150"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )
    with pytest.raises(ValidationError, match="Position shares .* mismatch sum of lots"):
        Position(
            ticker="SAP.DE",
            open_shares=Decimal("11"),
            open_lots=(lot1,),
            realised_gain_eur_ytd=Money.zero(Currency.EUR),
            cost_basis_eur=Money(amount=Decimal("1500"), currency=Currency.EUR),
        )


def test_position_cost_basis_mismatch():
    lot1 = OpenLot(
        source_transaction_id="tx-1",
        ticker="SAP.DE",
        trade_date=date(2024, 1, 1),
        remaining_shares=Decimal("10"),
        cost_per_share_native=Money(amount=Decimal("150"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )
    with pytest.raises(
        ValidationError, match="Position cost basis .* mismatch sum of lots"
    ):
        Position(
            ticker="SAP.DE",
            open_shares=Decimal("10"),
            open_lots=(lot1,),
            realised_gain_eur_ytd=Money.zero(Currency.EUR),
            cost_basis_eur=Money(amount=Decimal("1501"), currency=Currency.EUR),
        )


def test_models_frozen():
    lot = OpenLot(
        source_transaction_id="tx-1",
        ticker="AAPL",
        trade_date=date(2024, 1, 1),
        remaining_shares=Decimal("5"),
        cost_per_share_native=Money(amount=Decimal("180"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.92"),
    )
    with pytest.raises(ValidationError):
        lot.remaining_shares = Decimal("4")

    pos = Position(
        ticker="AAPL",
        open_shares=Decimal("5"),
        open_lots=(lot,),
        realised_gain_eur_ytd=Money.zero(Currency.EUR),
        cost_basis_eur=lot.cost_basis_eur,
    )
    with pytest.raises(ValidationError):
        pos.open_shares = Decimal("4")
