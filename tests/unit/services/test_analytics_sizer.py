from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.domain.money import Currency, Money
from app.domain.positions import LivePosition, OpenLot, PortfolioSummary, Position
from app.services import analytics_concentration, analytics_sizer
from app.services.analytics_sizer import (
    MISSING_PRICE_REASON,
    STALE_PRICE_REASON,
    ZERO_PORTFOLIO_REASON,
    compute_sizer_view,
    to_base_eur,
)


def _live_position(
    ticker: str,
    *,
    shares: Decimal,
    price_native: Decimal,
    currency: Currency,
    fx_rate: Decimal,
    stale_reason: str | None = None,
    missing: bool = False,
    omit_current_fx_rate: bool = False,
) -> LivePosition:
    value_eur = shares * price_native * fx_rate
    lot = OpenLot(
        source_transaction_id=f"{ticker}-lot",
        ticker=ticker,
        trade_date=date(2025, 1, 1),
        remaining_shares=shares,
        cost_per_share_native=Money(amount=price_native, currency=currency),
        fx_rate_eur=fx_rate,
    )
    position = Position(
        ticker=ticker,
        open_shares=shares,
        open_lots=(lot,),
        realised_gain_eur_ytd=Money(amount=Decimal("0"), currency=Currency.EUR),
        cost_basis_eur=Money(amount=value_eur, currency=Currency.EUR),
    )
    if missing:
        return LivePosition(
            position=position,
            live_price_native=None,
            live_value_eur=None,
            unrealised_gain_eur=None,
            unrealised_gain_pct=None,
            current_fx_rate=None,
            staleness_reason=stale_reason or "price unavailable",
        )
    if stale_reason is not None:
        return LivePosition.model_construct(
            position=position,
            live_price_native=Money(amount=price_native, currency=currency),
            live_value_eur=Money(amount=value_eur, currency=Currency.EUR),
            unrealised_gain_eur=Money(amount=Decimal("0"), currency=Currency.EUR),
            unrealised_gain_pct=Decimal("0"),
            current_fx_rate=None if omit_current_fx_rate else fx_rate,
            staleness_reason=stale_reason,
        )
    return LivePosition(
        position=position,
        live_price_native=Money(amount=price_native, currency=currency),
        live_value_eur=Money(amount=value_eur, currency=Currency.EUR),
        unrealised_gain_eur=Money(amount=Decimal("0"), currency=Currency.EUR),
        unrealised_gain_pct=Decimal("0"),
        current_fx_rate=None if omit_current_fx_rate else fx_rate,
        staleness_reason=None,
    )


def _summary(positions: list[LivePosition]) -> PortfolioSummary:
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


def _portfolio() -> list[LivePosition]:
    # Total EUR value = 100,000. AAPL has 100 shares at $200, fx 0.9 = 18,000 EUR.
    return [
        _live_position(
            "AAPL",
            shares=Decimal("100"),
            price_native=Decimal("200"),
            currency=Currency.USD,
            fx_rate=Decimal("0.9"),
        ),
        _live_position(
            "IUSQ.DE",
            shares=Decimal("820"),
            price_native=Decimal("100"),
            currency=Currency.EUR,
            fx_rate=Decimal("1"),
        ),
    ]


def test_compute_sizer_view_happy_path_matches_hand_computed_values() -> None:
    positions = _portfolio()
    view = compute_sizer_view(
        positions=positions,
        summary=_summary(positions),
        selected_ticker="AAPL",
        direction="buy",
        risk_pct=Decimal("1"),
        stop_pct=Decimal("8"),
        target_weight_pct=Decimal("20"),
    )

    assert view.degraded_reason is None
    assert view.current.weight_pct == Decimal("18.00")
    assert view.risk_based is not None
    # (100k * 1%) / (($200 * 0.9) * 8%) = 1000 / 14.4
    assert view.risk_based.shares == Decimal("69.44444444444444444444444444")
    assert view.risk_based.trade_value_eur.amount == Decimal("12500.0000")
    assert view.risk_based.risk_eur.amount == Decimal("1000.0000")
    assert view.risk_based.stop_price_native.amount == Decimal("184.0000")
    assert view.weight_based is not None
    assert view.weight_based.shares == Decimal("11.11111111111111111111111111")
    assert view.weight_based.delta_eur.amount == Decimal("2000.0000")
    assert view.post_trade is not None
    assert view.post_trade.new_weight_pct == Decimal("27.11")
    assert view.post_trade.bucket == "amber"


def test_sell_direction_inverts_risk_shares_and_stop_above_entry() -> None:
    positions = _portfolio()
    view = compute_sizer_view(
        positions=positions,
        summary=_summary(positions),
        selected_ticker="AAPL",
        direction="sell",
        risk_pct=Decimal("1"),
        stop_pct=Decimal("8"),
        target_weight_pct=Decimal("20"),
    )

    assert view.risk_based is not None
    assert view.risk_based.shares == Decimal("-69.44444444444444444444444444")
    assert view.risk_based.stop_price_native.amount == Decimal("216.0000")


def test_stale_ticker_still_computes_with_warning() -> None:
    positions = [
        _live_position(
            "STALE",
            shares=Decimal("100"),
            price_native=Decimal("100"),
            currency=Currency.EUR,
            fx_rate=Decimal("1"),
            stale_reason="stale cached price",
        )
    ]
    view = compute_sizer_view(
        positions=positions,
        summary=_summary(positions),
        selected_ticker="STALE",
        direction="buy",
        risk_pct=Decimal("1"),
        stop_pct=Decimal("8"),
        target_weight_pct=Decimal("20"),
    )

    assert view.degraded_reason == STALE_PRICE_REASON
    assert view.risk_based is not None
    assert view.weight_based is not None


def test_missing_ticker_short_circuits_results() -> None:
    positions = [
        _live_position(
            "MISS",
            shares=Decimal("100"),
            price_native=Decimal("100"),
            currency=Currency.USD,
            fx_rate=Decimal("0.9"),
            missing=True,
        )
    ]
    view = compute_sizer_view(
        positions=positions,
        summary=_summary(positions),
        selected_ticker="MISS",
        direction="buy",
        risk_pct=Decimal("1"),
        stop_pct=Decimal("8"),
        target_weight_pct=Decimal("20"),
    )

    assert view.degraded_reason == MISSING_PRICE_REASON
    assert view.risk_based is None
    assert view.weight_based is None
    assert view.post_trade is None


def test_empty_positions_return_zero_portfolio_degraded_view() -> None:
    view = compute_sizer_view(
        positions=[],
        summary=_summary([]),
        selected_ticker="AAPL",
        direction="buy",
        risk_pct=Decimal("1"),
        stop_pct=Decimal("8"),
        target_weight_pct=Decimal("20"),
    )

    assert view.degraded_reason == ZERO_PORTFOLIO_REASON
    assert view.risk_based is None


def test_missing_ticker_with_nonzero_portfolio_reports_no_live_price() -> None:
    positions = _portfolio() + [
        _live_position(
            "MISS",
            shares=Decimal("100"),
            price_native=Decimal("100"),
            currency=Currency.USD,
            fx_rate=Decimal("0.9"),
            missing=True,
        )
    ]
    view = compute_sizer_view(
        positions=positions,
        summary=_summary(positions),
        selected_ticker="MISS",
        direction="buy",
        risk_pct=Decimal("1"),
        stop_pct=Decimal("8"),
        target_weight_pct=Decimal("20"),
    )

    assert view.degraded_reason == MISSING_PRICE_REASON
    assert view.risk_based is None


def test_eur_native_ticker_uses_fx_rate_one() -> None:
    positions = _portfolio()
    view = compute_sizer_view(
        positions=positions,
        summary=_summary(positions),
        selected_ticker="IUSQ.DE",
        direction="buy",
        risk_pct=Decimal("1"),
        stop_pct=Decimal("10"),
        target_weight_pct=Decimal("80"),
    )

    assert view.current.last_price_native.currency == Currency.EUR
    assert view.current.last_price_eur.amount == Decimal("100.0000")


def test_eur_native_ticker_without_current_fx_rate_still_computes() -> None:
    positions = [
        _live_position(
            "HY9H.F",
            shares=Decimal("10"),
            price_native=Decimal("1065"),
            currency=Currency.EUR,
            fx_rate=Decimal("1"),
            omit_current_fx_rate=True,
        )
    ]
    view = compute_sizer_view(
        positions=positions,
        summary=_summary(positions),
        selected_ticker="HY9H.F",
        direction="buy",
        risk_pct=Decimal("1"),
        stop_pct=Decimal("8"),
        target_weight_pct=Decimal("20"),
    )

    assert view.current.last_price_native.amount == Decimal("1065.0000")
    assert view.current.last_price_eur.amount == Decimal("1065.0000")
    assert view.current.staleness is None
    assert view.degraded_reason is None
    assert view.risk_based is not None
    assert view.weight_based is not None
    assert view.post_trade is not None


def test_jpy_ticker_fx_conversion_keeps_stop_native() -> None:
    positions = [
        _live_position(
            "5631.T",
            shares=Decimal("100"),
            price_native=Decimal("3000"),
            currency=Currency.JPY,
            fx_rate=Decimal("0.0061"),
        )
    ]
    view = compute_sizer_view(
        positions=positions,
        summary=_summary(positions),
        selected_ticker="5631.T",
        direction="buy",
        risk_pct=Decimal("1"),
        stop_pct=Decimal("8"),
        target_weight_pct=Decimal("20"),
    )

    assert view.current.last_price_eur.amount == Decimal("18.3000")
    assert view.risk_based is not None
    assert view.risk_based.stop_price_native.amount == Decimal("2760.0000")
    assert view.risk_based.trade_value_eur.currency == Currency.EUR


@pytest.mark.parametrize(
    ("new_weight", "bucket"),
    [
        (Decimal("18"), "green"),
        (Decimal("25"), "amber"),
        (Decimal("35"), "red"),
        (Decimal("36"), "red"),
    ],
)
def test_bucket_boundaries(new_weight: Decimal, bucket: str) -> None:
    assert analytics_sizer._bucket_for_weight(new_weight) == bucket


def test_constants_are_imported_from_concentration_module() -> None:
    assert (
        analytics_sizer.MAX_POSITION_WEIGHT_PCT
        is analytics_concentration.MAX_POSITION_WEIGHT_PCT
    )
    assert analytics_sizer.BAR_SCALE_MAX_PCT is analytics_concentration.BAR_SCALE_MAX_PCT


def test_to_base_eur_rejects_mismatched_eur_fx_rate() -> None:
    with pytest.raises(AssertionError):
        to_base_eur(Decimal("100"), Currency.EUR, Decimal("1.1"))
