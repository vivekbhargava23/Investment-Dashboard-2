"""Integration tests for YfinancePriceAdapter.

These tests hit the real yfinance network endpoint and are skipped by default.
Run with: pytest -m integration
"""
from datetime import date
from decimal import Decimal

import pytest

from app.adapters.yfinance_price.adapter import YfinancePriceAdapter
from app.domain.money import Currency


@pytest.mark.integration
def test_real_nvda_current_price() -> None:
    adapter = YfinancePriceAdapter()
    price = adapter.get_current_price("NVDA")
    assert price.currency == Currency.USD
    assert price.amount > 0


@pytest.mark.integration
def test_real_rhm_de_current_price() -> None:
    adapter = YfinancePriceAdapter()
    price = adapter.get_current_price("RHM.DE")
    assert price.currency == Currency.EUR
    assert price.amount > 0


@pytest.mark.integration
def test_real_nvda_historical_close() -> None:
    adapter = YfinancePriceAdapter()
    d = date(2024, 1, 2)
    price = adapter.get_historical_close("NVDA", d)
    assert price.currency == Currency.USD
    # yfinance returns split-adjusted prices; NVDA split-adjusted price on 2024-01-02 ~48
    assert Decimal("40") < price.amount < Decimal("60")


@pytest.mark.integration
def test_real_5631t_current_price_is_jpy() -> None:
    """5631.T (Japan Steel Works) must return a JPY-denominated price."""
    adapter = YfinancePriceAdapter()
    price = adapter.get_current_price("5631.T")
    assert price.currency == Currency.JPY
    assert price.amount > 0
