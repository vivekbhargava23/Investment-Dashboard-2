import pytest

from app.domain.money import Currency
from app.domain.tickers import UnsupportedTickerError, infer_currency_from_ticker


def test_us_tickers_return_usd():
    for ticker in ("NVDA", "AAPL", "MSFT", "MRVL", "ASX", "MU", "ETN", "APD", "AVGO", "ANET"):
        assert infer_currency_from_ticker(ticker) == Currency.USD, ticker


def test_de_suffix_returns_eur():
    assert infer_currency_from_ticker("SAP.DE") == Currency.EUR
    assert infer_currency_from_ticker("RHM.DE") == Currency.EUR
    assert infer_currency_from_ticker("VUSA.DE") == Currency.EUR


def test_f_suffix_returns_eur():
    assert infer_currency_from_ticker("HY9H.F") == Currency.EUR


def test_mi_suffix_returns_eur():
    assert infer_currency_from_ticker("ENI.MI") == Currency.EUR


def test_pa_suffix_returns_eur():
    assert infer_currency_from_ticker("AI.PA") == Currency.EUR


def test_as_suffix_returns_eur():
    assert infer_currency_from_ticker("ASML.AS") == Currency.EUR


def test_t_suffix_returns_jpy():
    assert infer_currency_from_ticker("5631.T") == Currency.JPY
    assert infer_currency_from_ticker("7203.T") == Currency.JPY


def test_hk_suffix_raises_unsupported():
    with pytest.raises(UnsupportedTickerError, match="HKD"):
        infer_currency_from_ticker("0700.HK")


def test_ks_suffix_raises_unsupported():
    with pytest.raises(UnsupportedTickerError, match="KRW"):
        infer_currency_from_ticker("000660.KS")


def test_kq_suffix_raises_unsupported():
    with pytest.raises(UnsupportedTickerError, match="KRW"):
        infer_currency_from_ticker("035720.KQ")


def test_tw_suffix_raises_unsupported():
    with pytest.raises(UnsupportedTickerError, match="TWD"):
        infer_currency_from_ticker("2330.TW")


def test_two_suffix_raises_unsupported():
    with pytest.raises(UnsupportedTickerError, match="TWD"):
        infer_currency_from_ticker("6770.TWO")


def test_bk_suffix_raises_unsupported():
    with pytest.raises(UnsupportedTickerError, match="THB"):
        infer_currency_from_ticker("BCH.BK")


def test_suffix_matching_is_case_insensitive():
    assert infer_currency_from_ticker("sap.de") == Currency.EUR
    assert infer_currency_from_ticker("5631.t") == Currency.JPY


def test_empty_ticker_returns_usd():
    assert infer_currency_from_ticker("") == Currency.USD
