from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.analytics_views import ConcentrationRow, ConcentrationView
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
