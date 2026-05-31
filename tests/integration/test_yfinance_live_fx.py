"""Integration tests for YfinanceLiveFxAdapter.

These tests hit the real yfinance network endpoint and are skipped by default.
Run with: pytest -m integration
"""
from decimal import Decimal

import pytest

from app.adapters.fx_yfinance.adapter import YfinanceLiveFxAdapter
from app.domain.money import Currency


@pytest.mark.integration
def test_real_eur_usd_rate() -> None:
    adapter = YfinanceLiveFxAdapter()
    rate = adapter.get_current_rate(Currency.EUR, Currency.USD)
    assert Decimal("0.5") < rate < Decimal("2.0")


@pytest.mark.integration
def test_real_eur_jpy_rate() -> None:
    adapter = YfinanceLiveFxAdapter()
    rate = adapter.get_current_rate(Currency.EUR, Currency.JPY)
    assert Decimal("100") < rate < Decimal("200")


@pytest.mark.integration
def test_real_jpy_eur_rate_is_reciprocal() -> None:
    adapter = YfinanceLiveFxAdapter()
    eur_jpy = adapter.get_current_rate(Currency.EUR, Currency.JPY)
    jpy_eur = adapter.get_current_rate(Currency.JPY, Currency.EUR)
    product = eur_jpy * jpy_eur
    assert Decimal("0.99") < product < Decimal("1.01")
