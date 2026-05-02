import pytest
import pandas as pd
from datetime import date
from unittest.mock import MagicMock, patch
from app.core.portfolio import Portfolio
from app.core.position import Position
from app.core.transaction import Transaction
from app.services.history_service import get_portfolio_value_history

@pytest.fixture
def mock_portfolio():
    t1 = Transaction(ticker="AAPL", trade_date=date(2023, 1, 1), trade_type="buy", shares=10, price=150)
    t2 = Transaction(ticker="AAPL", trade_date=date(2023, 1, 10), trade_type="sell", shares=5, price=160)
    pos1 = Position(ticker="AAPL", name="Apple", transactions=[t1, t2])
    
    t3 = Transaction(ticker="SAP.DE", trade_date=date(2023, 1, 5), trade_type="buy", shares=20, price=100)
    pos2 = Position(ticker="SAP.DE", name="SAP", transactions=[t3])
    
    return Portfolio(name="Test", positions=[pos1, pos2])

@patch("app.services.history_service._fetch")
@patch("app.services.history_service.get_fx_rate")
def test_get_portfolio_value_history_vectorized(mock_fx_rate, mock_fetch, mock_portfolio):
    # Setup mock price data
    dates = pd.date_range("2023-01-01", "2023-01-15")
    
    # AAPL prices (USD)
    aapl_prices = pd.Series(150.0, index=dates, name="AAPL")
    aapl_prices.loc["2023-01-10":] = 170.0
    
    # SAP.DE prices (EUR)
    sap_prices = pd.Series(100.0, index=dates, name="SAP.DE")
    sap_prices.loc["2023-01-05":] = 110.0
    
    # FX Rate (USD/EUR) -> units of USD per 1 EUR.
    # If 1 EUR = 1.1 USD, rate = 1.1. 
    # Value in EUR = Value in USD / 1.1
    usd_eur_fx = pd.Series(1.1, index=dates, name="EURUSD=X")
    
    def side_effect(ticker, period, start=None):
        if ticker == "AAPL": return aapl_prices
        if ticker == "SAP.DE": return sap_prices
        if ticker == "EURUSD=X": return usd_eur_fx
        return pd.Series(dtype=float)

    mock_fetch.side_effect = side_effect
    mock_fx_rate.return_value = 1.1

    history = get_portfolio_value_history(mock_portfolio, "MAX")

    assert not history.empty
    assert isinstance(history, pd.Series)
    
    # Check specific dates
    # Jan 1: AAPL 10 shares * 150 / 1.1 = 1363.63
    assert history.loc["2023-01-01"] == pytest.approx(10 * 150 / 1.1)
    
    # Jan 5: AAPL 10 shares * 150 / 1.1 + SAP 20 shares * 110 = 1363.63 + 2200 = 3563.63
    assert history.loc["2023-01-05"] == pytest.approx(10 * 150 / 1.1 + 20 * 110)
    
    # Jan 10: AAPL 5 shares * 170 / 1.1 + SAP 20 shares * 110 = 772.72 + 2200 = 2972.72
    assert history.loc["2023-01-10"] == pytest.approx(5 * 170 / 1.1 + 20 * 110)

@patch("app.services.history_service._fetch")
def test_history_empty_portfolio(mock_fetch):
    portfolio = Portfolio(name="Empty", positions=[])
    history = get_portfolio_value_history(portfolio, "1M")
    assert history.empty
    assert history.name == "Portfolio (€)"
