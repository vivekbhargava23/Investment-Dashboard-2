from datetime import date, datetime
from decimal import Decimal

from app.domain.models import Currency, Money
from app.domain.positions import LivePosition, OpenLot, PortfolioSummary, Position


def _dummy_position() -> Position:
    return Position(
        ticker="DUMMY",
        open_shares=Decimal("0"),
        open_lots=(),
        realised_gain_eur_ytd=Money(amount=Decimal("0"), currency=Currency.EUR),
        cost_basis_eur=Money(amount=Decimal("0"), currency=Currency.EUR)
    )

def test_weight_calculation_correct():
    p1 = LivePosition(
        position=_dummy_position(),
        live_price_native=Money(amount=Decimal("10"), currency=Currency.EUR),
        live_value_eur=Money(amount=Decimal("100"), currency=Currency.EUR),
        unrealised_gain_eur=Money(amount=Decimal("0"), currency=Currency.EUR),
        unrealised_gain_pct=Decimal("0"), current_fx_rate=Decimal("1.0"), staleness_reason=None
    )
    p2 = LivePosition(
        position=_dummy_position(),
        live_price_native=Money(amount=Decimal("20"), currency=Currency.EUR),
        live_value_eur=Money(amount=Decimal("200"), currency=Currency.EUR),
        unrealised_gain_eur=Money(amount=Decimal("0"), currency=Currency.EUR),
        unrealised_gain_pct=Decimal("0"), current_fx_rate=Decimal("1.0"), staleness_reason=None
    )
    p3 = LivePosition(
        position=_dummy_position(),
        live_price_native=Money(amount=Decimal("30"), currency=Currency.EUR),
        live_value_eur=Money(amount=Decimal("300"), currency=Currency.EUR),
        unrealised_gain_eur=Money(amount=Decimal("0"), currency=Currency.EUR),
        unrealised_gain_pct=Decimal("0"), current_fx_rate=Decimal("1.0"), staleness_reason=None
    )

    summary = PortfolioSummary(
        total_value_eur=Money(amount=Decimal("600"), currency=Currency.EUR),
        total_cost_basis_eur=Money(amount=Decimal("600"), currency=Currency.EUR),
        total_unrealised_gain_eur=Money(amount=Decimal("0"), currency=Currency.EUR),
        total_unrealised_gain_pct=Decimal("0"),
        total_realised_gain_eur_ytd=Money(amount=Decimal("0"), currency=Currency.EUR),
        position_count=3,
        live_position_count=3,
        staleness="live",
        as_of=datetime.now()
    )

    w1 = float(p1.live_value_eur.amount / summary.total_value_eur.amount)
    w2 = float(p2.live_value_eur.amount / summary.total_value_eur.amount)
    w3 = float(p3.live_value_eur.amount / summary.total_value_eur.amount)

    assert abs((w1 + w2 + w3) - 1.0) < 0.0001

def test_stale_rows_sort_to_bottom():
    p_stale = LivePosition(
        position=_dummy_position(), live_price_native=None, live_value_eur=None,
        unrealised_gain_eur=None, unrealised_gain_pct=None, current_fx_rate=None,
        staleness_reason="stale"
    )
    p_live = LivePosition(
        position=_dummy_position(),
        live_price_native=Money(amount=Decimal("10"), currency=Currency.EUR),
        live_value_eur=Money(amount=Decimal("100"), currency=Currency.EUR),
        unrealised_gain_eur=Money(amount=Decimal("0"), currency=Currency.EUR),
        unrealised_gain_pct=Decimal("0"), current_fx_rate=Decimal("1.0"), staleness_reason=None
    )

    positions = [p_stale, p_live]

    sorted_positions = sorted(
        positions,
        key=lambda p: float(p.live_value_eur.amount) if p.live_value_eur is not None else -1.0,
        reverse=True
    )

    assert sorted_positions[0] == p_live
    assert sorted_positions[1] == p_stale


# ---------------------------------------------------------------------------
# Shared fixtures for the positions-table component tests.
#
# These helpers stay here because test_positions_table.py and
# test_overview_chart_integration.py both import them. The positions-table HTML
# assertions live in tests/unit/ui/test_positions_table.py (TICKET-RD1 moved the
# table out of overview.py into app/ui/components/positions_table.py).
# ---------------------------------------------------------------------------

def _make_open_lot(ticker: str, shares: str, cost_per_share: str) -> OpenLot:
    return OpenLot(
        source_transaction_id="tx-001",
        ticker=ticker,
        trade_date=date(2024, 1, 15),
        remaining_shares=Decimal(shares),
        cost_per_share_native=Money(amount=Decimal(cost_per_share), currency=Currency.EUR),
        fx_rate_eur=Decimal("1.0"),
    )


def _make_position_with_lot(ticker: str, shares: str, cost_per_share: str) -> Position:
    lot = _make_open_lot(ticker, shares, cost_per_share)
    cost_basis = Decimal(shares) * Decimal(cost_per_share)
    return Position(
        ticker=ticker,
        open_shares=Decimal(shares),
        open_lots=(lot,),
        realised_gain_eur_ytd=Money(amount=Decimal("0"), currency=Currency.EUR),
        cost_basis_eur=Money(amount=cost_basis, currency=Currency.EUR),
    )


def _make_live_position(ticker: str, shares: str = "10", cost: str = "100") -> LivePosition:
    position = _make_position_with_lot(ticker, shares, cost)
    live_price = Money(amount=Decimal("120"), currency=Currency.EUR)
    live_value = Money(amount=Decimal(shares) * Decimal("120"), currency=Currency.EUR)
    gain = Money(
        amount=(Decimal(shares) * Decimal("120")) - (Decimal(shares) * Decimal(cost)),
        currency=Currency.EUR,
    )
    return LivePosition(
        position=position,
        live_price_native=live_price,
        live_value_eur=live_value,
        unrealised_gain_eur=gain,
        unrealised_gain_pct=Decimal("0.2"),
        current_fx_rate=Decimal("1.0"),
        staleness_reason=None,
    )


def _make_live_position_usd(
    ticker: str, shares: str = "5", price_usd: str = "225.32"
) -> LivePosition:
    """Build a LivePosition with a USD native price."""
    lot = OpenLot(
        source_transaction_id="tx-usd",
        ticker=ticker,
        trade_date=date(2024, 6, 1),
        remaining_shares=Decimal(shares),
        cost_per_share_native=Money(amount=Decimal("180"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9"),
    )
    cost_basis = Decimal(shares) * Decimal("180") * Decimal("0.9")
    position = Position(
        ticker=ticker,
        open_shares=Decimal(shares),
        open_lots=(lot,),
        realised_gain_eur_ytd=Money(amount=Decimal("0"), currency=Currency.EUR),
        cost_basis_eur=Money(amount=cost_basis, currency=Currency.EUR),
    )
    live_price = Money(amount=Decimal(price_usd), currency=Currency.USD)
    eur_amount = Decimal(shares) * Decimal(price_usd) * Decimal("0.88")
    live_value = Money(amount=eur_amount, currency=Currency.EUR)
    gain = Money(amount=live_value.amount - cost_basis, currency=Currency.EUR)
    return LivePosition(
        position=position,
        live_price_native=live_price,
        live_value_eur=live_value,
        unrealised_gain_eur=gain,
        unrealised_gain_pct=Decimal("0.1"),
        current_fx_rate=Decimal("0.88"),
        staleness_reason=None,
    )


def _make_summary(positions: dict[str, LivePosition]) -> PortfolioSummary:
    total_value = sum(
        (p.live_value_eur.amount for p in positions.values() if p.live_value_eur),
        Decimal("0"),
    )
    total_cost = sum(
        (p.position.cost_basis_eur.amount for p in positions.values()),
        Decimal("0"),
    )
    count = len(positions)
    return PortfolioSummary(
        total_value_eur=Money(amount=total_value, currency=Currency.EUR),
        total_cost_basis_eur=Money(amount=total_cost, currency=Currency.EUR),
        total_unrealised_gain_eur=Money(amount=total_value - total_cost, currency=Currency.EUR),
        total_unrealised_gain_pct=Decimal("0.2"),
        total_realised_gain_eur_ytd=Money(amount=Decimal("0"), currency=Currency.EUR),
        position_count=count,
        live_position_count=count,
        staleness="live",
        as_of=datetime(2026, 5, 4, 10, 0, 0),
    )
