"""
app/services/price_service.py

Unified price service: routes each ticker to the correct client,
injects live prices into a Portfolio, and converts values to EUR.

Routing rule:
  - No dot in ticker  → US-listed  → Finnhub  (price in USD)
  - Dot in ticker     → Non-US     → yfinance (price in local currency)

FX rates (EUR/USD and EUR/JPY) are fetched from yfinance and cached.
All monetary values can be converted to EUR via convert_to_eur().
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.lot import OpenLot, dispose_fifo
from app.core.portfolio import Portfolio
from app.services import finnhub_client, yfinance_client
from app.utils.logger import get_logger

logger = get_logger(__name__)

# yfinance FX pair tickers: rate = units of quote currency per 1 EUR
_FX_PAIRS: dict[str, str] = {
    "USD": "EURUSD=X",
    "JPY": "EURJPY=X",
}

_CURRENCY_SUFFIX: dict[str, str] = {
    ".DE": "EUR",
    ".F":  "EUR",
    ".T":  "JPY",
}


def _is_us_ticker(ticker: str) -> bool:
    """US tickers carry no exchange suffix — no dot in the symbol."""
    return "." not in ticker


def get_currency(ticker: str) -> str:
    """Return the native currency for a ticker: USD, EUR, or JPY."""
    for suffix, ccy in _CURRENCY_SUFFIX.items():
        if ticker.endswith(suffix):
            return ccy
    return "USD"


def get_fx_rate(currency: str) -> float | None:
    """
    Return the EUR-based FX rate for a currency.

    The rate is defined as units of `currency` per 1 EUR.
    Example: EUR/USD = 1.17 means 1 EUR = 1.17 USD.

    EUR always returns 1.0. Returns None if the fetch fails.
    """
    if currency == "EUR":
        return 1.0
    pair = _FX_PAIRS.get(currency)
    if pair is None:
        logger.warning("fx_pair_unknown", currency=currency)
        return None
    rate = yfinance_client.get_price(pair)
    if rate is None:
        logger.warning("fx_rate_unavailable", currency=currency, pair=pair)
    return rate


def convert_to_eur(value: float, currency: str) -> float | None:
    """
    Convert a monetary value to EUR.

    Uses the live EUR/<currency> rate. Returns None if the FX rate
    is unavailable.

    Args:
        value:    Amount in the source currency.
        currency: Source currency code: "EUR", "USD", or "JPY".

    Returns:
        Equivalent value in EUR, or None if conversion is not possible.

    Examples:
        convert_to_eur(100.0, "EUR")  → 100.0
        convert_to_eur(117.0, "USD")  → ~100.0  (at EUR/USD 1.17)
        convert_to_eur(186.6, "JPY")  → ~1.0    (at EUR/JPY 186.6)
    """
    if currency == "EUR":
        return value
    rate = get_fx_rate(currency)
    if rate is None or rate == 0:
        return None
    return value / rate


def get_price(ticker: str) -> float | None:
    """
    Return the current price for any ticker, routed to the correct client.

    Args:
        ticker: Any supported ticker symbol.

    Returns:
        Price in the exchange's native currency, or None on failure.
    """
    ticker = ticker.strip().upper()
    if _is_us_ticker(ticker):
        return finnhub_client.get_price(ticker)
    return yfinance_client.get_price(ticker)


def inject_prices(portfolio: Portfolio) -> Portfolio:
    """
    Return a new Portfolio with live prices injected into every position.

    Positions whose price fetch fails keep live_price=None.
    Check portfolio.fully_priced to know whether all prices are available.

    Args:
        portfolio: Portfolio with positions, any live_price state.

    Returns:
        New Portfolio instance — original is not mutated.
    """
    priced = []
    for pos in portfolio.positions:
        price = get_price(pos.ticker)
        if price is not None:
            priced.append(pos.with_price(price))
        else:
            logger.warning("price_missing", ticker=pos.ticker)
            priced.append(pos)

    return portfolio.model_copy(update={"positions": priced})


def portfolio_eur_totals(
    portfolio: Portfolio,
) -> tuple[float, float, float] | None:
    """
    Return (total_value_eur, total_cost_eur, total_gain_eur) for the portfolio.

    Converts every position's current value and cost basis to EUR using live
    FX rates. Returns None if any position lacks a live price or if any FX
    rate is unavailable.

    Args:
        portfolio: Fully priced portfolio (all positions have live_price set).

    Returns:
        Three-tuple of EUR floats, or None if conversion is incomplete.
    """
    total_value = 0.0
    total_cost = 0.0

    for pos in portfolio.positions:
        if not pos.has_live_price:
            return None

        ccy = get_currency(pos.ticker)

        value_eur = convert_to_eur(pos.current_value, ccy)  # type: ignore[arg-type]
        cost_eur = convert_to_eur(pos.total_cost_basis, ccy)

        if value_eur is None or cost_eur is None:
            return None

        total_value += value_eur
        total_cost += cost_eur

    return total_value, total_cost, total_value - total_cost


def lookup_name(ticker: str) -> str | None:
    """
    Return the company name for any ticker.

    Uses yfinance for all tickers — it works for both exchange-suffixed symbols
    (RHM.DE, HY9H.F) and plain US symbols (NVDA, MU). This is intentionally
    separate from get_price(), which routes US tickers through Finnhub for
    better real-time data. Name lookups are infrequent and yfinance is fine.

    Args:
        ticker: Any supported ticker symbol.

    Returns:
        Company long name, or None if yfinance cannot identify the ticker.
    """
    return yfinance_client.get_name(ticker.strip().upper())


def clear_all_caches() -> None:
    """Evict all cached prices from both clients. Forces fresh fetches."""
    finnhub_client.clear_cache()
    yfinance_client.clear_cache()


@dataclass
class FifoPreview:
    """EUR-converted outcome of a prospective FIFO sell — for UI preview and recording."""
    proceeds_eur: float
    cost_eur: float
    gain_eur: float
    lots_consumed: int
    realised_gain_eur: float
    remaining_lots: list[OpenLot]


def fifo_sell_preview(
    open_lots: list[OpenLot],
    shares: float,
    sell_price: float,
    ticker: str,
) -> FifoPreview:
    """
    Run a FIFO disposal and return EUR-converted preview numbers.

    Calls dispose_fifo (core) then converts proceeds, cost, and gain to EUR
    via live FX rates. Raises ValueError (from dispose_fifo) if shares
    exceed what is held, and returns None fields where FX is unavailable.

    Args:
        open_lots:  Buy-only lots for the position (position.open_lots).
        shares:     Shares to sell.
        sell_price: Sale price per share in the ticker's native currency.
        ticker:     Ticker symbol — used to determine native currency.

    Returns:
        FifoPreview with EUR-converted totals.

    Raises:
        ValueError: If shares_to_sell exceeds total open shares.
    """
    result = dispose_fifo(open_lots, shares, sell_price)
    ccy = get_currency(ticker)
    proceeds_eur = convert_to_eur(result.total_proceeds, ccy) or 0.0
    cost_eur = convert_to_eur(result.total_cost_basis, ccy) or 0.0
    gain_eur = convert_to_eur(result.total_gain, ccy) or 0.0
    return FifoPreview(
        proceeds_eur=proceeds_eur,
        cost_eur=cost_eur,
        gain_eur=gain_eur,
        lots_consumed=len(result.disposals),
        realised_gain_eur=gain_eur,
        remaining_lots=result.remaining_lots,
    )
