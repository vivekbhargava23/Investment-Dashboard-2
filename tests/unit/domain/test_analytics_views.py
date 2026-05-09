from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.analytics_views import (
    ConcentrationRow,
    ConcentrationView,
    CurrentPositionCard,
    PostTradeWeightPreview,
    RiskBasedResult,
    SizerView,
    WeightBasedResult,
)
from app.domain.money import Currency, Money


def _row(weight: str = "10") -> ConcentrationRow:
    return ConcentrationRow(
        ticker="NVDA",
        name="NVDA",
        weight_pct=Decimal(weight),
        value_eur=Money(amount=Decimal("100"), currency=Currency.EUR),
        currency=Currency.USD,
    )


def test_concentration_models_are_frozen() -> None:
    row = _row()
    view = ConcentrationView(
        top_1_pct=Decimal("10"),
        top_3_pct=Decimal("10"),
        herfindahl=Decimal("100"),
        weights_by_ticker=[("NVDA", Decimal("10"))],
        currency_split=[(Currency.USD, Decimal("100"))],
        rows=[row],
    )

    with pytest.raises(ValidationError):
        row.ticker = "MSFT"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        view.top_1_pct = Decimal("20")  # type: ignore[misc]


def test_concentration_row_rejects_negative_weight() -> None:
    with pytest.raises(ValidationError, match="weight_pct"):
        _row("-1")


def test_concentration_view_enforces_top_3_at_least_top_1() -> None:
    with pytest.raises(ValidationError, match="top_3_pct"):
        ConcentrationView(
            top_1_pct=Decimal("20"),
            top_3_pct=Decimal("10"),
            herfindahl=Decimal("500"),
            weights_by_ticker=[],
            currency_split=[],
            rows=[],
        )


def test_concentration_view_round_trip_preserves_decimal_precision() -> None:
    view = ConcentrationView(
        top_1_pct=Decimal("33.33"),
        top_3_pct=Decimal("66.67"),
        herfindahl=Decimal("3333.3334"),
        weights_by_ticker=[("NVDA", Decimal("33.33"))],
        currency_split=[(Currency.USD, Decimal("1234.5678"))],
        rows=[_row("33.33")],
    )

    restored = ConcentrationView.model_validate_json(view.model_dump_json())

    assert restored.herfindahl == Decimal("3333.3334")
    assert restored.weights_by_ticker[0][1] == Decimal("33.33")


def _current_position_card() -> CurrentPositionCard:
    return CurrentPositionCard(
        ticker="NVDA",
        name="NVDA",
        weight_pct=Decimal("20"),
        market_value_eur=Money(amount=Decimal("20000"), currency=Currency.EUR),
        last_price_native=Money(amount=Decimal("200"), currency=Currency.USD),
        last_price_eur=Money(amount=Decimal("180"), currency=Currency.EUR),
        open_lot_count=2,
    )


def test_sizer_models_are_frozen_and_allow_negative_share_results() -> None:
    current = _current_position_card()
    risk = RiskBasedResult(
        shares=Decimal("-5"),
        trade_value_eur=Money(amount=Decimal("900"), currency=Currency.EUR),
        risk_eur=Money(amount=Decimal("100"), currency=Currency.EUR),
        risk_pct_input=Decimal("1"),
        stop_price_native=Money(amount=Decimal("216"), currency=Currency.USD),
    )
    weight = WeightBasedResult(
        shares=Decimal("-3"),
        delta_eur=Money(amount=Decimal("-540"), currency=Currency.EUR),
        current_weight_pct=Decimal("20"),
        target_weight_pct=Decimal("18"),
    )
    preview = PostTradeWeightPreview(
        current_weight_pct=Decimal("20"),
        new_weight_pct=Decimal("19"),
        bucket="green",
    )
    view = SizerView(
        current=current,
        risk_based=risk,
        weight_based=weight,
        post_trade=preview,
    )

    assert view.risk_based is not None
    assert view.risk_based.shares == Decimal("-5")
    assert view.weight_based is not None
    assert view.weight_based.delta_eur.amount == Decimal("-540.0000")
    with pytest.raises(ValidationError):
        view.degraded_reason = "changed"  # type: ignore[misc]


def test_post_trade_preview_bucket_is_constrained() -> None:
    with pytest.raises(ValidationError, match="bucket"):
        PostTradeWeightPreview(
            current_weight_pct=Decimal("10"),
            new_weight_pct=Decimal("12"),
            bucket="blue",
        )


def test_sizer_view_round_trip_preserves_decimal_precision_and_none_fields() -> None:
    view = SizerView(
        current=_current_position_card(),
        risk_based=None,
        weight_based=None,
        post_trade=None,
        degraded_reason="Selected ticker has no live price.",
    )

    restored = SizerView.model_validate_json(view.model_dump_json())

    assert restored.current.weight_pct == Decimal("20")
    assert restored.risk_based is None
    assert restored.degraded_reason == "Selected ticker has no live price."
