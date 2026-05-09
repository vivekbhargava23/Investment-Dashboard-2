from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.analytics import herfindahl_index


def test_herfindahl_single_position_is_max_concentration() -> None:
    assert herfindahl_index([Decimal("100")]) == Decimal("10000")


def test_herfindahl_ten_equal_positions() -> None:
    assert herfindahl_index([Decimal("10")] * 10) == Decimal("1000")


def test_herfindahl_two_equal_positions() -> None:
    assert herfindahl_index([Decimal("50"), Decimal("50")]) == Decimal("5000")


def test_herfindahl_empty_raises() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        herfindahl_index([])


def test_herfindahl_negative_weight_raises() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        herfindahl_index([Decimal("50"), Decimal("-10")])


def test_herfindahl_preserves_decimal_precision() -> None:
    result = herfindahl_index(
        [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
    )
    assert result == Decimal("3333.3334")
