from datetime import date
from decimal import Decimal

import pytest

from app.adapters.yfinance_feed import YfinanceAdapter
from app.domain.money import Currency


@pytest.mark.integration
def test_real_nvda_current_price() -> None:
    adapter = YfinanceAdapter()
    price = adapter.get_current_price("NVDA")
    assert price.currency == Currency.USD
    assert price.amount > 0


@pytest.mark.integration
def test_real_rhm_de_current_price() -> None:
    adapter = YfinanceAdapter()
    price = adapter.get_current_price("RHM.DE")
    assert price.currency == Currency.EUR
    assert price.amount > 0


@pytest.mark.integration
def test_real_eur_usd_rate() -> None:
    adapter = YfinanceAdapter()
    rate = adapter.get_current_rate(Currency.EUR, Currency.USD)
    assert Decimal("0.5") < rate < Decimal("2.0")


@pytest.mark.integration
def test_real_nvda_historical_close() -> None:
    adapter = YfinanceAdapter()
    d = date(2024, 1, 2)
    price = adapter.get_historical_close("NVDA", d)
    assert price.currency == Currency.USD
    # NVDA split recently, but on 2024-01-02 it was around 481 (pre-split)
    # yfinance usually returns split-adjusted prices.
    # On 2024-01-02, split adjusted price was around 48.1
    assert Decimal("40") < price.amount < Decimal("60")


@pytest.mark.integration
def test_real_5631t_current_price_is_jpy() -> None:
    """5631.T (Japan Steel Works) must return a JPY-denominated price."""
    adapter = YfinanceAdapter()
    price = adapter.get_current_price("5631.T")
    assert price.currency == Currency.JPY
    assert price.amount > 0


@pytest.mark.integration
def test_real_eur_jpy_rate() -> None:
    adapter = YfinanceAdapter()
    rate = adapter.get_current_rate(Currency.EUR, Currency.JPY)
    assert Decimal("100") < rate < Decimal("200")


@pytest.mark.integration
def test_real_jpy_eur_rate_is_reciprocal() -> None:
    adapter = YfinanceAdapter()
    eur_jpy = adapter.get_current_rate(Currency.EUR, Currency.JPY)
    jpy_eur = adapter.get_current_rate(Currency.JPY, Currency.EUR)
    product = eur_jpy * jpy_eur
    assert Decimal("0.99") < product < Decimal("1.01")
