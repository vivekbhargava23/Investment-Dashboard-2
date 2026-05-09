from __future__ import annotations

from decimal import Decimal

from app.domain.money import Currency
from app.services.analytics_concentration import compute_concentration_view
from tests.fixtures.concentration_fixtures import (
    make_live_position,
    make_summary,
    realistic_13_position_portfolio,
)


def test_realistic_13_position_portfolio_kpis_match_hand_computed_values() -> None:
    positions = realistic_13_position_portfolio()
    view = compute_concentration_view(positions, make_summary(positions))

    assert view.weights_by_ticker[0] == ("NVDA", Decimal("22.00"))
    assert view.top_1_pct == Decimal("22.00")
    assert view.top_3_pct == Decimal("47.00")
    assert view.herfindahl == Decimal("1178.00")


def test_single_position_portfolio_is_fully_concentrated() -> None:
    positions = [make_live_position("NVDA", "1000", Currency.USD)]
    view = compute_concentration_view(positions, make_summary(positions))

    assert view.top_1_pct == Decimal("100.00")
    assert view.top_3_pct == Decimal("100.00")
    assert view.herfindahl == Decimal("10000.00")


def test_empty_portfolio_returns_empty_view() -> None:
    view = compute_concentration_view([], make_summary([]))

    assert view.top_1_pct == Decimal("0")
    assert view.top_3_pct == Decimal("0")
    assert view.herfindahl == Decimal("0")
    assert view.weights_by_ticker == []
    assert view.currency_split == []
    assert view.rows == []


def test_currency_split_groups_by_native_currency_descending() -> None:
    positions = [
        make_live_position("A", "1000", Currency.USD),
        make_live_position("B", "1000", Currency.USD),
        make_live_position("C", "1000", Currency.USD),
        make_live_position("D", "500", Currency.EUR),
        make_live_position("E", "500", Currency.EUR),
        make_live_position("F", "200", Currency.JPY),
    ]

    view = compute_concentration_view(positions, make_summary(positions))

    assert view.currency_split == [
        (Currency.USD, Decimal("3000.0000")),
        (Currency.EUR, Decimal("1000.0000")),
        (Currency.JPY, Decimal("200.0000")),
    ]


def test_weights_are_descending_and_normalised() -> None:
    positions = realistic_13_position_portfolio()
    view = compute_concentration_view(positions, make_summary(positions))

    weights = [weight for _, weight in view.weights_by_ticker]
    assert weights == sorted(weights, reverse=True)
    assert sum(weights, Decimal("0")) == Decimal("100.00")


def test_stale_position_stays_in_rows_but_not_weights_or_currency_split() -> None:
    positions = [
        make_live_position("A", "600", Currency.USD),
        make_live_position("B", "400", Currency.EUR),
        make_live_position("STALE", "1000", Currency.JPY, stale=True),
    ]

    view = compute_concentration_view(positions, make_summary(positions))

    assert len(view.rows) == 3
    assert ("STALE", Decimal("0")) not in view.weights_by_ticker
    assert all(currency != Currency.JPY for currency, _ in view.currency_split)
    assert view.rows[-1].ticker == "STALE"
    assert view.rows[-1].staleness_reason == "price unavailable"


def test_identical_weights_sort_by_ticker() -> None:
    positions = [
        make_live_position("B", "100", Currency.EUR),
        make_live_position("A", "100", Currency.EUR),
    ]

    view = compute_concentration_view(positions, make_summary(positions))

    assert view.weights_by_ticker == [
        ("A", Decimal("50.00")),
        ("B", Decimal("50.00")),
    ]


def test_top_3_collapses_when_only_two_positions_exist() -> None:
    positions = [
        make_live_position("A", "600", Currency.EUR),
        make_live_position("B", "400", Currency.EUR),
    ]

    view = compute_concentration_view(positions, make_summary(positions))

    assert view.top_3_pct == Decimal("100.00")
