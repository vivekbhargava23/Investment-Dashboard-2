"""
app/services/history_service.py

Historical price fetching and portfolio value reconstruction over time.
Vectorised via pandas for performance.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

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


def _fetch_batch(tickers: Sequence[str], period: str, start: date | None = None) -> pd.DataFrame:
    """
    Fetch Close prices for multiple tickers in a single batched call.
    Returns a DataFrame with tickers as columns.
    """
    if not tickers:
        return pd.DataFrame()

    try:
        if period == "MAX":
            if start:
                raw = yf.download(list(tickers), start=str(start), interval="1d", group_by="ticker", auto_adjust=True, threads=True, progress=False)
            else:
                raw = yf.download(list(tickers), period="max", interval="1d", group_by="ticker", auto_adjust=True, threads=True, progress=False)
        else:
            yf_period, interval = _YF_PARAMS.get(period, ("1mo", "1d"))
            raw = yf.download(list(tickers), period=yf_period, interval=interval, group_by="ticker", auto_adjust=True, threads=True, progress=False)

        if raw.empty:
            logger.warning("batch_fetch_empty", tickers=tickers, period=period)
            return pd.DataFrame()

        # Extract 'Close' prices. yf.download with group_by='ticker' returns a MultiIndex (Ticker, PriceType)
        # or a single level index if only one ticker is requested.
        result_df = pd.DataFrame(index=raw.index)
        
        for ticker in tickers:
            try:
                if len(tickers) > 1:
                    s = raw[ticker]["Close"]
                else:
                    s = raw["Close"]
                result_df[ticker] = s
            except KeyError:
                logger.warning("ticker_missing_in_batch", ticker=ticker)
                # Fallback: Fetch individually
                s_fallback = _fetch(ticker, period, start)
                if not s_fallback.empty:
                    result_df[ticker] = s_fallback
        
        return result_df.dropna(how="all")

    except Exception as exc:
        logger.error("batch_fetch_error", error=str(exc))
        # Final fallback: Fetch all individually if batch fails entirely
        result_df = pd.DataFrame()
        for ticker in tickers:
            s = _fetch(ticker, period, start)
            if not s.empty:
                result_df[ticker] = s
        return result_df


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


def _normalise_index(df_or_s: pd.DataFrame | pd.Series, intraday: bool) -> pd.DataFrame | pd.Series:
    """Strip timezone; for daily data also strip the time component."""
    idx = pd.DatetimeIndex(df_or_s.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    if not intraday:
        idx = idx.normalize()          # → midnight timestamps, all dates comparable
    
    if isinstance(df_or_s, pd.DataFrame):
        return pd.DataFrame(df_or_s.values, index=idx, columns=df_or_s.columns)
    return pd.Series(df_or_s.values, index=idx, name=df_or_s.name)


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

    # 1. Determine date range and tickers
    all_txns = [t for pos in portfolio.positions for t in pos.transactions]
    if not all_txns:
        return pd.Series(dtype=float, name="Portfolio (€)")
    
    earliest_txn = min(t.trade_date for t in all_txns)
    start_date = earliest_txn if period == "MAX" else None

    asset_tickers = [pos.ticker for pos in portfolio.positions]
    currencies = {pos.ticker: get_currency(pos.ticker) for pos in portfolio.positions}
    unique_ccys = set(currencies.values()) - {"EUR"}
    fx_tickers = [_FX_TICKERS[ccy] for ccy in unique_ccys]

    # 2. Batch fetch all Asset Prices and FX Rates
    all_to_fetch = list(set(asset_tickers + fx_tickers))
    combined_df = _fetch_batch(all_to_fetch, period, start=start_date)
    
    if combined_df.empty:
        return pd.Series(dtype=float, name="Portfolio (€)")

    combined_df = _normalise_index(combined_df, intraday)
    full_index = combined_df.index
    
    # 3. Build Price Matrix (T x N)
    price_df = combined_df[asset_tickers].ffill()

    # 4. Build Shares Matrix (T x N)
    shares_df = pd.DataFrame(0.0, index=full_index, columns=asset_tickers)
    for pos in portfolio.positions:
        txn_series = pd.Series(0.0, index=full_index)
        for t in pos.transactions:
            ts = pd.Timestamp(t.trade_date)
            impact = t.shares if t.trade_type == "buy" else -t.shares
            idx_after = full_index[full_index >= ts]
            if not idx_after.empty:
                txn_series.loc[idx_after[0]] += impact
        
        shares_df[pos.ticker] = txn_series.cumsum()

    # 5. Build FX Matrix (T x N)
    fx_df = pd.DataFrame(1.0, index=full_index, columns=asset_tickers)
    
    if intraday:
        # For 1D, use live FX rate for the whole series (matches Phase 6 behavior)
        for ticker, ccy in currencies.items():
            if ccy != "EUR":
                fx_df[ticker] = get_fx_rate(ccy) or 1.0
    else:
        for ticker, ccy in currencies.items():
            if ccy != "EUR":
                fx_ticker = _FX_TICKERS[ccy]
                if fx_ticker in combined_df.columns:
                    fx_df[ticker] = combined_df[fx_ticker].ffill().bfill()
                else:
                    # Fallback to live rate if historical FX is totally missing
                    fx_df[ticker] = get_fx_rate(ccy) or 1.0

    # 6. Final Calculation: (Price * Shares / FX).sum(axis=1)
    portfolio_value = (price_df * shares_df / fx_df).sum(axis=1)
    
    return portfolio_value.rename("Portfolio (€)")
