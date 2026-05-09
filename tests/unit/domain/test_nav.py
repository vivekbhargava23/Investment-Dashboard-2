"""Unit tests for app.domain.nav.DailyNavPoint."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.money import Currency, Money
from app.domain.nav import DailyNavPoint

_EUR_ZERO = Money(amount=Decimal("0"), currency=Currency.EUR)
_EUR_100 = Money(amount=Decimal("100"), currency=Currency.EUR)
_EUR_80 = Money(amount=Decimal("80"), currency=Currency.EUR)


def _make_point(**overrides: object) -> DailyNavPoint:
    defaults: dict[str, object] = {
        "snapshot_date": date(2025, 6, 1),
        "nav_eur": _EUR_100,
        "cost_basis_eur": _EUR_80,
        "n_positions": 3,
        "is_reconstructed": True,
    }
    defaults.update(overrides)
    return DailyNavPoint(**defaults)  # type: ignore[arg-type]


class TestDailyNavPointFrozen:
    def test_assignment_raises(self) -> None:
        point = _make_point()
        with pytest.raises(Exception):  # ValidationError or TypeError from frozen model
            point.n_positions = 99  # type: ignore[misc]


class TestDailyNavPointValidators:
    def test_nav_eur_must_be_eur(self) -> None:
        with pytest.raises(Exception):
            _make_point(nav_eur=Money(amount=Decimal("100"), currency=Currency.USD))

    def test_cost_basis_eur_must_be_eur(self) -> None:
        with pytest.raises(Exception):
            _make_point(cost_basis_eur=Money(amount=Decimal("80"), currency=Currency.USD))

    def test_nav_eur_non_negative(self) -> None:
        with pytest.raises(Exception):
            _make_point(nav_eur=Money(amount=Decimal("-1"), currency=Currency.EUR))

    def test_cost_basis_eur_non_negative(self) -> None:
        with pytest.raises(Exception):
            _make_point(cost_basis_eur=Money(amount=Decimal("-0.01"), currency=Currency.EUR))

    def test_n_positions_non_negative(self) -> None:
        with pytest.raises(Exception):
            _make_point(n_positions=-1)

    def test_zero_nav_allowed(self) -> None:
        point = _make_point(nav_eur=_EUR_ZERO, cost_basis_eur=_EUR_ZERO, n_positions=0)
        assert point.nav_eur.amount == Decimal("0")

    def test_n_positions_zero_allowed(self) -> None:
        point = _make_point(n_positions=0)
        assert point.n_positions == 0


class TestDailyNavPointRoundTrip:
    def test_round_trip_preserves_decimal_precision(self) -> None:
        amount = Decimal("12345.6789")
        point = _make_point(
            nav_eur=Money(amount=amount, currency=Currency.EUR),
        )
        raw = point.model_dump(mode="json")
        restored = DailyNavPoint.model_validate(raw)
        # Money normalises to 4 decimal places via its own validator.
        assert restored.nav_eur.amount == point.nav_eur.amount

    def test_round_trip_preserves_date(self) -> None:
        d = date(2024, 12, 31)
        point = _make_point(snapshot_date=d)
        raw = point.model_dump(mode="json")
        restored = DailyNavPoint.model_validate(raw)
        assert restored.snapshot_date == d

    def test_round_trip_preserves_is_reconstructed_false(self) -> None:
        point = _make_point(is_reconstructed=False)
        raw = point.model_dump(mode="json")
        restored = DailyNavPoint.model_validate(raw)
        assert restored.is_reconstructed is False
