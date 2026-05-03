import pytest

from app.adapters.yfinance_feed import YfinanceAdapter
from app.domain.money import Currency


@pytest.mark.parametrize(
    "ticker,expected_currency",
    [
        ("NVDA", Currency.USD),
        ("RHM.DE", Currency.EUR),
        ("HY9H.F", Currency.EUR),
        ("MU", Currency.USD),
        ("MTE.DE", Currency.EUR),
        ("BRK.B", Currency.USD),
        ("AAPL.AS", Currency.EUR),
        ("ENI.MI", Currency.EUR),
        ("MC.PA", Currency.EUR),
    ],
)
def test_currency_inference(ticker: str, expected_currency: Currency) -> None:
    adapter = YfinanceAdapter()
    assert adapter._infer_currency(ticker) == expected_currency
