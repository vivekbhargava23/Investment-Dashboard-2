from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.domain.money import Currency, Money
from app.domain.positions import LivePosition, OpenLot, PortfolioSummary, Position


def make_live_position(
    ticker: str,
    value_eur: str,
    currency: Currency,
    *,
    stale: bool = False,
) -> LivePosition:
    value = Decimal(value_eur)
    lot = OpenLot(
        source_transaction_id=f"{ticker}-lot",
        ticker=ticker,
        trade_date=date(2025, 1, 1),
        remaining_shares=value,
        cost_per_share_native=Money(amount=Decimal("1"), currency=currency),
        fx_rate_eur=Decimal("1"),
    )
    position = Position(
        ticker=ticker,
        open_shares=value,
        open_lots=(lot,),
        realised_gain_eur_ytd=Money(amount=Decimal("0"), currency=Currency.EUR),
        cost_basis_eur=Money(amount=value, currency=Currency.EUR),
    )
    if stale:
        return LivePosition(
            position=position,
            live_price_native=None,
            live_value_eur=None,
            unrealised_gain_eur=None,
            unrealised_gain_pct=None,
            current_fx_rate=None,
            staleness_reason="price unavailable",
        )
    return LivePosition(
        position=position,
        live_price_native=Money(amount=Decimal("1"), currency=currency),
        live_value_eur=Money(amount=value, currency=Currency.EUR),
        unrealised_gain_eur=Money(amount=Decimal("0"), currency=Currency.EUR),
        unrealised_gain_pct=Decimal("0"),
        current_fx_rate=Decimal("1"),
        staleness_reason=None,
    )


def make_summary(positions: list[LivePosition]) -> PortfolioSummary:
    total_value = sum(
        (
            position.live_value_eur.amount
            for position in positions
            if position.live_value_eur is not None
        ),
        Decimal("0"),
    )
    total_cost = sum(
        (position.position.cost_basis_eur.amount for position in positions),
        Decimal("0"),
    )
    live_count = sum(1 for position in positions if not position.is_stale)
    return PortfolioSummary(
        total_value_eur=Money(amount=total_value, currency=Currency.EUR),
        total_cost_basis_eur=Money(amount=total_cost, currency=Currency.EUR),
        total_unrealised_gain_eur=Money(amount=Decimal("0"), currency=Currency.EUR),
        total_unrealised_gain_pct=Decimal("0"),
        total_realised_gain_eur_ytd=Money(amount=Decimal("0"), currency=Currency.EUR),
        position_count=len(positions),
        live_position_count=live_count,
        staleness="live" if live_count == len(positions) else "partial",
        as_of=datetime(2026, 5, 9, 12, 0),
    )


def realistic_13_position_portfolio() -> list[LivePosition]:
    # Values total EUR 100,000. Expected weights: 22, 14, 11, 10, 9, 8, 7, 6, 5, 4, 2, 1, 1.
    return [
        make_live_position("NVDA", "22000", Currency.USD),
        make_live_position("RHM.DE", "14000", Currency.EUR),
        make_live_position("MU", "11000", Currency.USD),
        make_live_position("MRVL", "10000", Currency.USD),
        make_live_position("ANET", "9000", Currency.USD),
        make_live_position("AVGO", "8000", Currency.USD),
        make_live_position("ETN", "7000", Currency.USD),
        make_live_position("ASX", "6000", Currency.USD),
        make_live_position("APD", "5000", Currency.USD),
        make_live_position("VUSA.DE", "4000", Currency.EUR),
        make_live_position("SAP.DE", "2000", Currency.EUR),
        make_live_position("SIE.DE", "1000", Currency.EUR),
        make_live_position("5631.T", "1000", Currency.JPY),
    ]
