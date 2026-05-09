from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.sizing import risk_based_shares, weight_based_delta_shares


def test_risk_based_shares_matches_hand_computed_example() -> None:
    # (100k * 1%) / (200 * 8%) = 1000 / 16 = 62.5
    assert risk_based_shares(
        portfolio_value_eur=Decimal("100000"),
        risk_pct=Decimal("1"),
        stop_pct=Decimal("8"),
        price_eur=Decimal("200"),
    ) == Decimal("62.5")


def test_risk_based_shares_preserves_decimal_precision() -> None:
    expected = (Decimal("100000") * Decimal("1.5") / Decimal("100")) / (
        Decimal("123.45") * Decimal("7.5") / Decimal("100")
    )

    assert (
        risk_based_shares(
            portfolio_value_eur=Decimal("100000"),
            risk_pct=Decimal("1.5"),
            stop_pct=Decimal("7.5"),
            price_eur=Decimal("123.45"),
        )
        == expected
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("portfolio_value_eur", Decimal("0")),
        ("portfolio_value_eur", Decimal("-1")),
        ("price_eur", Decimal("0")),
        ("price_eur", Decimal("-100")),
        ("risk_pct", Decimal("0")),
        ("risk_pct", Decimal("101")),
        ("stop_pct", Decimal("0")),
        ("stop_pct", Decimal("101")),
    ],
)
def test_risk_based_shares_rejects_bad_inputs(field: str, value: Decimal) -> None:
    kwargs = {
        "portfolio_value_eur": Decimal("100000"),
        "risk_pct": Decimal("1"),
        "stop_pct": Decimal("8"),
        "price_eur": Decimal("200"),
    }
    kwargs[field] = value

    with pytest.raises(ValueError):
        risk_based_shares(**kwargs)


def test_weight_based_delta_shares_positive_when_target_above_current() -> None:
    assert weight_based_delta_shares(
        target_weight_pct=Decimal("20"),
        current_weight_pct=Decimal("15"),
        portfolio_value_eur=Decimal("100000"),
        price_eur=Decimal("100"),
    ) == Decimal("50")


def test_weight_based_delta_shares_negative_when_target_below_current() -> None:
    assert weight_based_delta_shares(
        target_weight_pct=Decimal("10"),
        current_weight_pct=Decimal("15"),
        portfolio_value_eur=Decimal("100000"),
        price_eur=Decimal("100"),
    ) == Decimal("-50")


def test_weight_based_delta_shares_zero_when_already_at_target() -> None:
    assert weight_based_delta_shares(
        target_weight_pct=Decimal("15"),
        current_weight_pct=Decimal("15"),
        portfolio_value_eur=Decimal("100000"),
        price_eur=Decimal("100"),
    ) == Decimal("0")


def test_weight_based_delta_shares_allows_target_above_100() -> None:
    assert weight_based_delta_shares(
        target_weight_pct=Decimal("150"),
        current_weight_pct=Decimal("50"),
        portfolio_value_eur=Decimal("100000"),
        price_eur=Decimal("100"),
    ) == Decimal("1000")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("portfolio_value_eur", Decimal("0")),
        ("price_eur", Decimal("0")),
        ("target_weight_pct", Decimal("-5")),
        ("current_weight_pct", Decimal("-1")),
    ],
)
def test_weight_based_delta_shares_rejects_bad_inputs(
    field: str,
    value: Decimal,
) -> None:
    kwargs = {
        "target_weight_pct": Decimal("20"),
        "current_weight_pct": Decimal("15"),
        "portfolio_value_eur": Decimal("100000"),
        "price_eur": Decimal("100"),
    }
    kwargs[field] = value

    with pytest.raises(ValueError):
        weight_based_delta_shares(**kwargs)
