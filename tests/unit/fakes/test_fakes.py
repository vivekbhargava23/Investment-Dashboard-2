from datetime import date
from decimal import Decimal

import pytest

from app.domain.money import Currency, Money
from app.ports.fx_feed import FxProvider, FxRateUnavailableError
from app.ports.price_feed import PriceProvider, TickerNotFoundError
from tests.fakes.fx_feed import FakeFxProvider
from tests.fakes.price_feed import FakePriceProvider


def test_fake_price_provider_returns_constructed_prices() -> None:
    money = Money(amount=Decimal("100"), currency=Currency.USD)
    pp = FakePriceProvider(current_prices={"NVDA": money})

    assert pp.get_current_price("NVDA") == money


def test_fake_price_provider_raises_for_missing_tickers() -> None:
    pp = FakePriceProvider()
    with pytest.raises(TickerNotFoundError):
        pp.get_current_price("NVDA")


def test_fake_price_provider_set_price_mutates() -> None:
    pp = FakePriceProvider()
    money = Money(amount=Decimal("100"), currency=Currency.USD)
    pp.set_price("NVDA", money)

    assert pp.get_current_price("NVDA") == money


def test_fake_price_provider_historical() -> None:
    money = Money(amount=Decimal("90"), currency=Currency.USD)
    today = date(2024, 1, 1)
    pp = FakePriceProvider(historical_prices={("NVDA", today): money})

    assert pp.get_historical_close("NVDA", today) == money


def test_fake_fx_provider_round_trips() -> None:
    rate = Decimal("1.08")
    today = date(2024, 1, 1)
    fp = FakeFxProvider()

    fp.set_rate(Currency.EUR, Currency.USD, rate)
    assert fp.get_current_rate(Currency.EUR, Currency.USD) == rate

    fp.set_historical_rate(Currency.EUR, Currency.USD, today, rate)
    assert fp.get_historical_rate(Currency.EUR, Currency.USD, today) == rate


def test_fake_fx_provider_raises_for_missing() -> None:
    fp = FakeFxProvider()
    with pytest.raises(FxRateUnavailableError):
        fp.get_current_rate(Currency.EUR, Currency.USD)


def test_fakes_satisfy_protocols() -> None:
    # This is a type-checking test, but we can also do a runtime check if needed.
    # Here we just ensure they can be assigned to the Protocol types.
    pp: PriceProvider = FakePriceProvider()
    fp: FxProvider = FakeFxProvider()

    assert pp is not None
    assert fp is not None
