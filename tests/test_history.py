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

@patch("app.services.history_service.yf.download")
@patch("app.services.history_service.get_fx_rate")
def test_get_portfolio_value_history_batched(mock_fx_rate, mock_download, mock_portfolio):
    # Setup mock price data
    dates = pd.date_range("2023-01-01", "2023-01-15")
    
    # AAPL prices (USD)
    aapl_prices = pd.Series(150.0, index=dates)
    aapl_prices.loc["2023-01-10":] = 170.0
    
    # SAP.DE prices (EUR)
    sap_prices = pd.Series(100.0, index=dates)
    sap_prices.loc["2023-01-05":] = 110.0
    
    # FX Rate (USD/EUR) -> units of USD per 1 EUR.
    usd_eur_fx = pd.Series(1.1, index=dates)
    
    # Construct MultiIndex DataFrame returned by yf.download(group_by="ticker")
    mock_df = pd.DataFrame(index=dates)
    mock_df[("AAPL", "Close")] = aapl_prices
    mock_df[("SAP.DE", "Close")] = sap_prices
    mock_df[("EURUSD=X", "Close")] = usd_eur_fx
    mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
    
    mock_download.return_value = mock_df
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

@patch("app.services.history_service.yf.download")
def test_history_empty_portfolio(mock_download):
    portfolio = Portfolio(name="Empty", positions=[])
    history = get_portfolio_value_history(portfolio, "1M")
    assert history.empty
    assert history.name == "Portfolio (€)"

@patch("app.services.history_service.yf.download")
@patch("app.services.history_service._fetch")
def test_get_portfolio_value_history_fallback(mock_fetch, mock_download, mock_portfolio):
    # Simulate a missing ticker in batch
    dates = pd.date_range("2023-01-01", "2023-01-05")
    mock_df = pd.DataFrame(index=dates)
    mock_df[("AAPL", "Close")] = 150.0
    mock_df[("EURUSD=X", "Close")] = 1.0
    # SAP.DE is missing!
    mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
    mock_download.return_value = mock_df
    
    # Mock individual fallback fetch for SAP.DE
    mock_fetch.return_value = pd.Series(100.0, index=dates, name="SAP.DE")
    
    history = get_portfolio_value_history(mock_portfolio, "MAX")
    
    # Verify fallback was called for SAP.DE
    called_tickers = [args[0] for args, kwargs in mock_fetch.call_args_list]
    assert "SAP.DE" in called_tickers
    
    # Total = AAPL (10 * 150 / 1.0) + SAP (20 * 100) = 1500 + 2000 = 3500
    assert history.loc["2023-01-05"] == pytest.approx(3500.0)
