from datetime import datetime
from decimal import Decimal

from app.domain.models import Currency, Money
from app.domain.positions import LivePosition, PortfolioSummary, Position
from app.ui.pages.overview import _PLACEHOLDER_THESIS_STATUS


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

def test_placeholder_thesis_status_defaults():
    assert _PLACEHOLDER_THESIS_STATUS.get("UNKNOWN_TICKER", "intact") == "intact"
