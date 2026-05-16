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


# ─── override map ────────────────────────────────────────────────────────────

def test_hxscl_returns_usd_via_override():
    assert infer_currency_from_ticker("HXSCL") == Currency.USD


def test_asx_returns_usd_via_override():
    assert infer_currency_from_ticker("ASX") == Currency.USD


def test_override_is_case_insensitive():
    assert infer_currency_from_ticker("hxscl") == Currency.USD
    assert infer_currency_from_ticker("Hxscl") == Currency.USD


# ─── additional EUR suffixes ──────────────────────────────────────────────────

def test_sg_suffix_returns_eur():
    assert infer_currency_from_ticker("SAP.SG") == Currency.EUR


def test_mu_suffix_returns_eur():
    assert infer_currency_from_ticker("SAP.MU") == Currency.EUR


def test_hm_suffix_returns_eur():
    assert infer_currency_from_ticker("SAP.HM") == Currency.EUR


def test_du_suffix_returns_eur():
    assert infer_currency_from_ticker("SAP.DU") == Currency.EUR


def test_be_suffix_returns_eur():
    assert infer_currency_from_ticker("SAP.BE") == Currency.EUR


def test_br_suffix_returns_eur():
    assert infer_currency_from_ticker("UCB.BR") == Currency.EUR


def test_ls_suffix_returns_eur():
    assert infer_currency_from_ticker("EDP.LS") == Currency.EUR


def test_mc_suffix_returns_eur():
    assert infer_currency_from_ticker("ITX.MC") == Currency.EUR


def test_he_suffix_returns_eur():
    assert infer_currency_from_ticker("NESTE.HE") == Currency.EUR


def test_vi_suffix_returns_eur():
    assert infer_currency_from_ticker("OMV.VI") == Currency.EUR


def test_ir_suffix_returns_eur():
    assert infer_currency_from_ticker("CRH.IR") == Currency.EUR


def test_lu_suffix_returns_eur():
    assert infer_currency_from_ticker("APAM.LU") == Currency.EUR


# ─── additional JPY suffix ────────────────────────────────────────────────────

def test_jp_suffix_returns_jpy():
    assert infer_currency_from_ticker("7203.JP") == Currency.JPY


# ─── new unsupported suffixes ─────────────────────────────────────────────────

def test_l_suffix_raises_unsupported():
    with pytest.raises(UnsupportedTickerError, match="GBP"):
        infer_currency_from_ticker("HSBA.L")


def test_sw_suffix_raises_unsupported():
    with pytest.raises(UnsupportedTickerError, match="CHF"):
        infer_currency_from_ticker("NESN.SW")


def test_vx_suffix_raises_unsupported():
    with pytest.raises(UnsupportedTickerError, match="CHF"):
        infer_currency_from_ticker("NESN.VX")


def test_ax_suffix_raises_unsupported():
    with pytest.raises(UnsupportedTickerError, match="AUD"):
        infer_currency_from_ticker("BHP.AX")


def test_to_suffix_raises_unsupported():
    with pytest.raises(UnsupportedTickerError, match="CAD"):
        infer_currency_from_ticker("RY.TO")


def test_v_suffix_raises_unsupported():
    with pytest.raises(UnsupportedTickerError, match="CAD"):
        infer_currency_from_ticker("ACB.V")
