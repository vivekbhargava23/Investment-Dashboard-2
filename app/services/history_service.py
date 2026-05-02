"""
app/services/history_service.py

Historical price fetching and portfolio value reconstruction over time.

yfinance is used for all history regardless of ticker exchange — Finnhub's
free tier has no OHLCV history endpoint. FX rates are fetched from yfinance
(EURUSD=X, EURJPY=X) for non-EUR positions.

Period → yfinance mapping
  1D   → period="1d",  interval="1h"   (intraday, current lot composition)
  1W   → period="5d",  interval="1d"
  1M   → period="1mo", interval="1d"
  YTD  → period="ytd", interval="1d"
  MAX  → start=earliest_purchase_date, interval="1d"
"""

from __future__ import annotations

from datetime import date

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

    For each timestamp t in the shared price index:
      value(t) = Σ_pos  active_shares(pos, t) × price(pos, t) / fx_rate(ccy, t)

    active_shares(pos, t) = lots whose purchase_date ≤ t.date()

    For 1D (intraday): uses the full current lot composition and live FX rates.
    For daily periods: uses historical lot composition and historical FX rates,
    falling back to the live rate if history is unavailable.

    Returns:
        pd.Series named "Portfolio (€)", indexed by Timestamp. Empty on failure.
    """
    if not portfolio.positions:
        return pd.Series(dtype=float, name="Portfolio (€)")

    intraday = period == "1D"

    # Earliest purchase date (used for MAX trimming)
    earliest: date | None = None
    if period == "MAX":
        all_dates = [t.trade_date for pos in portfolio.positions for t in pos.transactions]
        earliest = min(all_dates) if all_dates else None

    # Fetch and normalise price histories
    price_map: dict[str, pd.Series] = {}
    for pos in portfolio.positions:
        s = _fetch(pos.ticker, period, start=earliest)
        if not s.empty:
            price_map[pos.ticker] = _normalise_index(s, intraday)

    if not price_map:
        return pd.Series(dtype=float, name="Portfolio (€)")

    # Fetch FX history (or fall back to live rate for 1D)
    currencies_needed = {
        get_currency(pos.ticker)
        for pos in portfolio.positions
        if get_currency(pos.ticker) != "EUR"
    }
    fx_map: dict[str, pd.Series | float] = {}
    for ccy in currencies_needed:
        if intraday:
            fx_map[ccy] = get_fx_rate(ccy) or 1.0
        else:
            s = _fetch(_FX_TICKERS[ccy], period, start=earliest)
            if not s.empty:
                fx_map[ccy] = _normalise_index(s, intraday=False)
            else:
                fx_map[ccy] = get_fx_rate(ccy) or 1.0

    # Build unified timestamp index from all price series
    all_idx = sorted(set().union(*[set(s.index) for s in price_map.values()]))

    totals: dict = {}
    for ts in all_idx:
        ts_date = ts.date() if hasattr(ts, "date") else pd.Timestamp(ts).date()
        total = 0.0
        for pos in portfolio.positions:
            active = sum(
                t.shares if t.trade_type == "buy" else -t.shares
                for t in pos.transactions if t.trade_date <= ts_date
            )
            if active <= 0:
                continue

            ps = price_map.get(pos.ticker)
            if ps is None:
                continue
            available = ps[ps.index <= ts]
            if available.empty:
                continue
            price = float(available.iloc[-1])

            ccy = get_currency(pos.ticker)
            if ccy == "EUR":
                fx = 1.0
            else:
                fx_src = fx_map.get(ccy, 1.0)
                if isinstance(fx_src, (int, float)):
                    fx = float(fx_src)
                else:
                    avail_fx = fx_src[fx_src.index <= ts]
                    fx = float(avail_fx.iloc[-1]) if not avail_fx.empty else 1.0

            if fx > 0:
                total += active * price / fx

        totals[ts] = total

    return pd.Series(totals, name="Portfolio (€)").sort_index()
