import pytest

from app.domain.money import Currency
from app.domain.tickers import infer_currency_from_ticker


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
    assert infer_currency_from_ticker(ticker) == expected_currency
