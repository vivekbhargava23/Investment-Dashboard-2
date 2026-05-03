import inspect
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.services.valuation import (
    clear_caches,
    compute_live_positions,
    compute_portfolio_summary,
)
from tests.fakes.fx_feed import FakeFxProvider
from tests.fakes.price_feed import FakePriceProvider


@pytest.fixture
def eur_buy() -> Transaction:
    return Transaction(
        id="t1",
        ticker="RHM.DE",
        type=TransactionType.BUY,
        trade_date=date(2024, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
        fee_native=Money(amount=Decimal("0"), currency=Currency.EUR),
        tax_native=Money(amount=Decimal("0"), currency=Currency.EUR),
    )


@pytest.fixture
def usd_buy() -> Transaction:
    # 10 shares at $100 each. Cost $1000.
    # FX rate 0.9 EUR per 1 USD -> Cost €900.
    return Transaction(
        id="t2",
        ticker="NVDA",
        type=TransactionType.BUY,
        trade_date=date(2024, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("100"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9"),
        fee_native=Money(amount=Decimal("0"), currency=Currency.USD),
        tax_native=Money(amount=Decimal("0"), currency=Currency.USD),
    )


def test_compute_live_positions_eur_happy_path(eur_buy: Transaction) -> None:
    pp = FakePriceProvider(
        current_prices={"RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR)}
    )
    fp = FakeFxProvider()

    res = compute_live_positions([eur_buy], pp, fp)

    assert "RHM.DE" in res
    lp = res["RHM.DE"]
    assert lp.ticker == "RHM.DE"
    assert lp.live_price_native == Money(amount=Decimal("110"), currency=Currency.EUR)
    assert lp.live_value_eur == Money(amount=Decimal("1100"), currency=Currency.EUR)
    assert lp.unrealised_gain_eur == Money(amount=Decimal("100"), currency=Currency.EUR)
    assert lp.unrealised_gain_pct == Decimal("10")
    assert not lp.is_stale


def test_compute_live_positions_usd_happy_path(usd_buy: Transaction) -> None:
    # Current price $110.
    # Current FX: 1.1 USD per 1 EUR -> 1 USD = 1/1.1 EUR = 0.909091 EUR.
    # Value in EUR = 10 * 110 * (1/1.1) = 1100 / 1.1 = 1000 EUR.
    # Cost basis was €900.
    # Gain = €100.
    pp = FakePriceProvider(
        current_prices={"NVDA": Money(amount=Decimal("110"), currency=Currency.USD)}
    )
    fp = FakeFxProvider(current_rates={(Currency.EUR, Currency.USD): Decimal("1.1")})

    res = compute_live_positions([usd_buy], pp, fp)

    assert "NVDA" in res
    lp = res["NVDA"]
    assert lp.live_value_eur == Money(amount=Decimal("1000"), currency=Currency.EUR)
    assert lp.unrealised_gain_eur == Money(amount=Decimal("100"), currency=Currency.EUR)
    assert not lp.is_stale


def test_compute_live_positions_mixed_all_live(eur_buy: Transaction, usd_buy: Transaction) -> None:
    pp = FakePriceProvider(
        current_prices={
            "RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR),
            "NVDA": Money(amount=Decimal("110"), currency=Currency.USD),
        }
    )
    fp = FakeFxProvider(current_rates={(Currency.EUR, Currency.USD): Decimal("1.1")})

    res = compute_live_positions([eur_buy, usd_buy], pp, fp)
    assert len(res) == 2
    assert all(not lp.is_stale for lp in res.values())


def test_compute_live_positions_empty() -> None:
    pp = FakePriceProvider()
    fp = FakeFxProvider()
    res = compute_live_positions([], pp, fp)
    assert res == {}


def test_per_ticker_failure_isolation(eur_buy: Transaction) -> None:
    # Two transactions, one price missing
    t2 = Transaction(
        id="t2",
        ticker="MISSING",
        type=TransactionType.BUY,
        trade_date=date(2024, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
        fee_native=Money(amount=Decimal("0"), currency=Currency.EUR),
        tax_native=Money(amount=Decimal("0"), currency=Currency.EUR),
    )

    pp = FakePriceProvider(
        current_prices={"RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR)}
        # "MISSING" is missing
    )
    fp = FakeFxProvider()

    res = compute_live_positions([eur_buy, t2], pp, fp)

    assert res["RHM.DE"].is_stale is False
    assert res["MISSING"].is_stale is True
    assert res["MISSING"].staleness_reason == "Price not in fake"


def test_fx_failure_marks_usd_stale(eur_buy: Transaction, usd_buy: Transaction) -> None:
    pp = FakePriceProvider(
        current_prices={
            "RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR),
            "NVDA": Money(amount=Decimal("110"), currency=Currency.USD),
        }
    )
    fp = FakeFxProvider()  # Missing FX rate

    res = compute_live_positions([eur_buy, usd_buy], pp, fp)

    assert res["RHM.DE"].is_stale is False
    assert res["NVDA"].is_stale is True
    assert res["NVDA"].staleness_reason == "FX rate USD/EUR unavailable"


def test_portfolio_summary_aggregates_live_only(eur_buy: Transaction) -> None:
    # 2 live, 1 stale
    t2 = eur_buy.model_copy(update={"id": "t2", "ticker": "LIVE2"})
    t_stale = eur_buy.model_copy(update={"id": "t3", "ticker": "STALE"})

    pp = FakePriceProvider(
        current_prices={
            "RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR),
            "LIVE2": Money(amount=Decimal("110"), currency=Currency.EUR),
        }
    )
    fp = FakeFxProvider()

    res = compute_live_positions([eur_buy, t2, t_stale], pp, fp)
    lp1 = res["RHM.DE"]
    lp2 = res["LIVE2"]
    lp_stale = res["STALE"]

    summary = compute_portfolio_summary(res, datetime.now())

    assert summary.position_count == 3
    assert summary.live_position_count == 2
    assert summary.staleness == "partial"
    # Value should only be from lp1 + lp2
    assert summary.total_value_eur.amount == lp1.live_value_eur.amount + lp2.live_value_eur.amount
    # Cost basis should be from all three
    assert summary.total_cost_basis_eur.amount == (
        lp1.position.cost_basis_eur.amount
        + lp2.position.cost_basis_eur.amount
        + lp_stale.position.cost_basis_eur.amount
    )


def test_service_has_no_state(eur_buy: Transaction) -> None:
    # Verify that calling twice results in twice as many provider calls (no internal caching)
    pp = FakePriceProvider(
        current_prices={"RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR)}
    )
    fp = FakeFxProvider()

    # Wrap get_current_price to count calls
    original_method = pp.get_current_price
    pp.get_current_price = MagicMock(side_effect=original_method)  # type: ignore

    compute_live_positions([eur_buy], pp, fp)
    compute_live_positions([eur_buy], pp, fp)

    assert pp.get_current_price.call_count == 2


def test_service_no_module_state() -> None:
    import app.services.valuation as valuation

    allowed_names = [
        "Sequence",
        "datetime",
        "Decimal",
        "Literal",
        "compute_positions",
        "Transaction",
        "Currency",
        "Money",
        "LivePosition",
        "PortfolioSummary",
        "FxProvider",
        "FxRateUnavailableError",
        "PriceProvider",
        "PriceUnavailableError",
    ]
    for name, obj in inspect.getmembers(valuation):
        if name.startswith("__"):
            continue
        if inspect.isfunction(obj) or inspect.ismodule(obj) or inspect.isclass(obj):
            continue
        # Allow type hint imports and standard imports
        if name in allowed_names:
            continue

        pytest.fail(
            f"Module app.services.valuation has unexpected member: {name} of type {type(obj)}"
        )


def test_clear_caches() -> None:
    pp = MagicMock(spec=FakePriceProvider)
    fp = MagicMock(spec=FakeFxProvider)

    clear_caches(pp, fp)

    pp.clear_cache.assert_called_once()
    fp.clear_cache.assert_called_once()
