"""
app/services/history_service.py

Historical price fetching and portfolio value reconstruction over time.
Vectorised via pandas for performance.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import yfinance as yf

from app.core.portfolio import Portfolio
from app.services.price_service import get_currency, get_fx_rate
from app.utils.logger import get_logger

logger = get_logger(__name__)

PERIODS = ["1D", "1W", "1M", "YTD", "MAX"]

_FX_TICKERS: dict[str, str] = {"USD": "EURUSD=X", "JPY": "EURJPY=X"}

_YF_PARAMS: dict[str, tuple[str, str]] = {
    "1D":  ("1d",  "1h"),
    "1W":  ("5d",  "1d"),
    "1M":  ("1mo", "1d"),
    "YTD": ("ytd", "1d"),
}


def _fetch(ticker: str, period: str, start: date | None = None) -> pd.Series:
    """Fetch Close prices from yfinance. Returns empty Series on any failure."""
    try:
        t = yf.Ticker(ticker)
        if period == "MAX":
            if start:
                raw = t.history(start=str(start), interval="1d", auto_adjust=True)
            else:
                raw = t.history(period="max", interval="1d", auto_adjust=True)
        else:
            yf_period, interval = _YF_PARAMS.get(period, ("1mo", "1d"))
            raw = t.history(period=yf_period, interval=interval, auto_adjust=True)
        if raw.empty:
            logger.warning("history_empty", ticker=ticker, period=period)
            return pd.Series(dtype=float, name=ticker)
        return raw["Close"].dropna().rename(ticker)
    except Exception as exc:
        logger.warning("history_error", ticker=ticker, period=period, error=str(exc))
        return pd.Series(dtype=float, name=ticker)


def _normalise_index(s: pd.Series, intraday: bool) -> pd.Series:
    """Strip timezone; for daily data also strip the time component."""
    idx = pd.DatetimeIndex(s.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    if not intraday:
        idx = idx.normalize()          # → midnight timestamps, all dates comparable
    return pd.Series(s.values, index=idx, name=s.name)


def get_ticker_history(ticker: str, period: str, start: date | None = None) -> pd.Series:
    """
    Return Close price history for a single ticker.

    Args:
        ticker: Any supported symbol (US, Frankfurt, Tokyo).
        period: One of PERIODS.
        start:  Explicit start date used only when period == "MAX".

    Returns:
        pd.Series indexed by timezone-naive Timestamp, empty on failure.
    """
    s = _fetch(ticker, period, start=start)
    return _normalise_index(s, intraday=(period == "1D")) if not s.empty else s


def get_portfolio_value_history(portfolio: Portfolio, period: str) -> pd.Series:
    """
    Reconstruct total portfolio value in EUR over time.
    Vectorised reconstruction: Total(t) = Σ [Shares(ticker, t) * Price(ticker, t) / FX(ticker, t)]
    """
    if not portfolio.positions:
        return pd.Series(dtype=float, name="Portfolio (€)")

    intraday = period == "1D"

    # 1. Determine date range
    all_txns = [t for pos in portfolio.positions for t in pos.transactions]
    if not all_txns:
        return pd.Series(dtype=float, name="Portfolio (€)")
    
    earliest_txn = min(t.trade_date for t in all_txns)
    start_date = earliest_txn if period == "MAX" else None

    # 2. Fetch price and FX histories
    price_histories = {}
    tickers = [pos.ticker for pos in portfolio.positions]
    for ticker in tickers:
        s = _fetch(ticker, period, start=start_date)
        if not s.empty:
            price_histories[ticker] = _normalise_index(s, intraday)
    
    if not price_histories:
        return pd.Series(dtype=float, name="Portfolio (€)")

    # Unified index from all fetched prices
    full_index = pd.DatetimeIndex(sorted(set().union(*[set(s.index) for s in price_histories.values()])))
    
    # 3. Build Price Matrix (T x N)
    price_df = pd.DataFrame(index=full_index)
    for ticker, s in price_histories.items():
        price_df[ticker] = s
    price_df = price_df.ffill()

    # 4. Build Shares Matrix (T x N)
    shares_df = pd.DataFrame(0.0, index=full_index, columns=tickers)
    for pos in portfolio.positions:
        # Group transactions by date to handle multiple same-day trades
        txn_series = pd.Series(0.0, index=full_index)
        for t in pos.transactions:
            ts = pd.Timestamp(t.trade_date)
            impact = t.shares if t.trade_type == "buy" else -t.shares
            # Find the first index >= trade_date
            # For 1D, trade_date (date) might need alignment with intraday timestamps
            idx_after = full_index[full_index >= ts]
            if not idx_after.empty:
                txn_series.loc[idx_after[0]] += impact
        
        shares_df[pos.ticker] = txn_series.cumsum()

    # 5. Build FX Matrix (T x N)
    currencies = {pos.ticker: get_currency(pos.ticker) for pos in portfolio.positions}
    unique_ccys = set(currencies.values()) - {"EUR"}
    
    fx_histories = {}
    for ccy in unique_ccys:
        if intraday:
            fx_histories[ccy] = pd.Series(get_fx_rate(ccy) or 1.0, index=full_index)
        else:
            s = _fetch(_FX_TICKERS[ccy], period, start=start_date)
            if not s.empty:
                fx_histories[ccy] = _normalise_index(s, intraday=False)
            else:
                fx_histories[ccy] = pd.Series(get_fx_rate(ccy) or 1.0, index=full_index)

    fx_df = pd.DataFrame(1.0, index=full_index, columns=tickers)
    for ticker, ccy in currencies.items():
        if ccy != "EUR" and ccy in fx_histories:
            s = fx_histories[ccy]
            # Align FX series to full_index
            fx_aligned = pd.Series(index=full_index, dtype=float)
            fx_aligned.update(s)
            fx_df[ticker] = fx_aligned.ffill().bfill()

    # 6. Final Calculation: (Price * Shares / FX).sum(axis=1)
    # Ensure all shapes match
    portfolio_value = (price_df * shares_df / fx_df).sum(axis=1)
    
    return portfolio_value.rename("Portfolio (€)")
