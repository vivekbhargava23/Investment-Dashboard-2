"""Service for computing the Technicals tab view.

Fetches OHLC history with a buffer large enough to seed SMA(50) and SMA(200),
computes indicators, and slices to the user-selected visible period.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from app.domain import analytics
from app.domain.fifo import compute_positions
from app.domain.market_data import (
    AggregationFreq,
    ChartPeriod,
    OhlcBar,
    aggregate_ohlc_series,
)
from app.domain.money import Currency
from app.domain.tickers import UnsupportedTickerError, infer_currency_from_ticker
from app.ports.market_data import OhlcDataProvider
from app.ports.price_feed import PriceProvider
from app.ports.repository import TransactionRepository

# ── Constants ──────────────────────────────────────────────────────────────────

RECENT_CROSS_WINDOW: Final[int] = 90
RSI_OVERBOUGHT: Final[Decimal] = Decimal(70)
RSI_OVERSOLD: Final[Decimal] = Decimal(30)
SMA_SHORT_PERIOD: Final[int] = 50
SMA_LONG_PERIOD: Final[int] = 200
RSI_PERIOD: Final[int] = 14

# Approximate trading days for each period label (used to slice the visible window)
_PERIOD_TRADING_DAYS: dict[str, int] = {
    "1M": 21,
    "3M": 65,
    "6M": 130,
    "1Y": 252,
    "2Y": 504,
    "5Y": 0,  # 0 = use all available bars
}

# Divisors to convert trading-day counts to coarser bar counts
_FREQ_BAR_DIVISOR: dict[str, int] = {
    "day": 1,
    "week": 5,
    "month": 21,
}

# Fetch the largest period to maximise history available for SMA seeding
_FETCH_PERIOD: Final[ChartPeriod] = ChartPeriod.FIVE_YEAR


# ── Exceptions ─────────────────────────────────────────────────────────────────


class OhlcUnavailable(Exception):
    """Raised when OHLC data cannot be fetched for the given ticker."""


# ── Domain models ──────────────────────────────────────────────────────────────


class TechnicalsSignals(BaseModel):
    model_config = ConfigDict(frozen=True)

    trend_50: Literal["above", "below", "insufficient"]
    trend_200: Literal["above", "below", "insufficient"]
    cross: Literal["golden", "death", "none", "insufficient"]
    cross_days_ago: int | None
    rsi_level: Literal["overbought", "oversold", "neutral", "insufficient"]
    rsi_value: Decimal | None
    live_change_pct: Decimal | None


class TechnicalsView(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    name: str
    currency: Currency
    visible_dates: list[date]
    ohlc: list[OhlcBar]
    sma_50: list[Decimal | None]
    sma_200: list[Decimal | None]
    rsi: list[Decimal] | None
    live_price: Decimal | None
    day_open: Decimal | None
    signals: TechnicalsSignals
    total_history_days: int


# ── Public service function ────────────────────────────────────────────────────


def build_technicals_view(
    *,
    ticker: str,
    period: str,
    repo: TransactionRepository,
    price_feed: PriceProvider,
    ohlc: OhlcDataProvider,
    as_of: date,
    freq: AggregationFreq | None = None,
) -> TechnicalsView:
    """Compute the full technicals view for one owned position.

    Raises:
      ValueError:         ticker has no open shares (not in the live universe).
      OhlcUnavailable:    OHLC fetch failed; reason in args[0].
    """
    # 1. Validate ticker is in live universe (open shares > 0)
    positions = compute_positions(repo.load_all(), as_of)
    if ticker not in positions or positions[ticker].open_shares <= 0:
        raise ValueError(f"Ticker {ticker} not in open positions")

    pos = positions[ticker]
    try:
        currency = infer_currency_from_ticker(ticker)
    except UnsupportedTickerError:
        # Fall back to the lot's recorded currency if ticker inference fails
        currency = (
            pos.open_lots[0].cost_per_share_native.currency
            if pos.open_lots
            else Currency.EUR
        )

    # 2. Fetch OHLC — always use the max period to seed long-window SMAs.
    #    Single symbol, but routed through the batch API so there is one fetch path.
    raw_series = ohlc.get_ohlc_histories([ticker], _FETCH_PERIOD).get(ticker)
    if raw_series is None:
        raise OhlcUnavailable(f"{ticker}: no OHLC data for period {_FETCH_PERIOD.value}")

    series = aggregate_ohlc_series(raw_series, freq) if freq is not None else raw_series

    all_bars = list(series.bars)
    total_history_days = len(all_bars)
    all_closes = [bar.close for bar in all_bars]

    # 3. Compute indicators over the full fetched range
    sma_50_full = analytics.sma(all_closes, SMA_SHORT_PERIOD)
    sma_200_full = analytics.sma(all_closes, SMA_LONG_PERIOD)
    rsi_full = analytics.rsi(all_closes, RSI_PERIOD)  # [] if < RSI_PERIOD+1 bars

    # 4. Determine the visible slice (adjust bar count for coarser frequencies)
    period_days = _PERIOD_TRADING_DAYS.get(period, 130)
    if freq is not None:
        divisor = _FREQ_BAR_DIVISOR.get(freq, 1)
        period_days = period_days // divisor if period_days > 0 else 0
    if period_days == 0 or period_days >= total_history_days:
        slice_start = 0
    else:
        slice_start = total_history_days - period_days

    visible_bars = all_bars[slice_start:]
    visible_dates = [bar.timestamp.date() for bar in visible_bars]
    visible_sma_50 = sma_50_full[slice_start:]
    visible_sma_200 = sma_200_full[slice_start:]

    # 5. RSI for visible window — only keep Decimal values (no None warm-up entries)
    visible_rsi: list[Decimal] | None
    if not rsi_full:
        visible_rsi = None
    else:
        rsi_slice = rsi_full[slice_start:]
        non_none = [v for v in rsi_slice if v is not None]
        visible_rsi = non_none if non_none else None

    # 6. Live price fetch (best-effort; None on failure). Single symbol, but routed
    #    through the batch API so there is one fetch path.
    live_money = price_feed.get_current_prices([ticker]).get(ticker)
    live_price: Decimal | None = live_money.amount if live_money is not None else None

    day_open = visible_bars[-1].open if visible_bars else None

    # 7. Compute signal states
    signals = _compute_signals(
        sma_50_full=sma_50_full,
        sma_200_full=sma_200_full,
        rsi_full=rsi_full,
        visible_sma_50=visible_sma_50,
        visible_sma_200=visible_sma_200,
        visible_closes=[bar.close for bar in visible_bars],
        live_price=live_price,
        day_open=day_open,
    )

    return TechnicalsView(
        ticker=ticker,
        name=ticker,
        currency=currency,
        visible_dates=visible_dates,
        ohlc=visible_bars,
        sma_50=visible_sma_50,
        sma_200=visible_sma_200,
        rsi=visible_rsi,
        live_price=live_price,
        day_open=day_open,
        signals=signals,
        total_history_days=total_history_days,
    )


# ── Internal helpers ───────────────────────────────────────────────────────────


def _compute_signals(
    *,
    sma_50_full: list[Decimal | None],
    sma_200_full: list[Decimal | None],
    rsi_full: list[Decimal | None],
    visible_sma_50: list[Decimal | None],
    visible_sma_200: list[Decimal | None],
    visible_closes: list[Decimal],
    live_price: Decimal | None,
    day_open: Decimal | None,
) -> TechnicalsSignals:
    last_close = visible_closes[-1] if visible_closes else None

    # Trend signals — compare most recent visible close to most recent visible SMA
    trend_50 = _trend_signal(visible_sma_50, last_close)
    trend_200 = _trend_signal(visible_sma_200, last_close)

    # Cross — uses FULL history so seeded values are available
    cross: Literal["golden", "death", "none", "insufficient"]
    cross_days_ago: int | None
    try:
        cross_result, days = analytics.detect_recent_cross(
            sma_50_full,
            sma_200_full,
            lookback=RECENT_CROSS_WINDOW,
        )
        cross = cross_result
        cross_days_ago = days
    except ValueError:
        cross = "insufficient"
        cross_days_ago = None

    # RSI level — last non-None value from rsi_full
    rsi_level: Literal["overbought", "oversold", "neutral", "insufficient"]
    rsi_value: Decimal | None
    if not rsi_full:
        rsi_level = "insufficient"
        rsi_value = None
    else:
        last_rsi = next((v for v in reversed(rsi_full) if v is not None), None)
        if last_rsi is None:
            rsi_level = "insufficient"
            rsi_value = None
        else:
            rsi_value = last_rsi
            if last_rsi > RSI_OVERBOUGHT:
                rsi_level = "overbought"
            elif last_rsi < RSI_OVERSOLD:
                rsi_level = "oversold"
            else:
                rsi_level = "neutral"

    # Live change percent: (live_price - day_open) / day_open
    live_change_pct: Decimal | None
    if live_price is not None and day_open is not None and day_open != Decimal(0):
        live_change_pct = (live_price - day_open) / day_open * Decimal(100)
    else:
        live_change_pct = None

    return TechnicalsSignals(
        trend_50=trend_50,
        trend_200=trend_200,
        cross=cross,
        cross_days_ago=cross_days_ago,
        rsi_level=rsi_level,
        rsi_value=rsi_value,
        live_change_pct=live_change_pct,
    )


def _trend_signal(
    sma_values: list[Decimal | None],
    last_close: Decimal | None,
) -> Literal["above", "below", "insufficient"]:
    if not sma_values or last_close is None:
        return "insufficient"
    last_sma = sma_values[-1]
    if last_sma is None:
        return "insufficient"
    return "above" if last_close > last_sma else "below"
