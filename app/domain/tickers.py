"""Ticker → native currency mapping. Single source of truth (ADR-005, TICKET-008c)."""
from app.domain.money import Currency

# Ordered longest-first so that ".F" does not shadow ".F" vs ".AS" etc.
_SUFFIX_TO_CURRENCY: dict[str, Currency] = {
    ".DE": Currency.EUR,
    ".AS": Currency.EUR,
    ".MI": Currency.EUR,
    ".PA": Currency.EUR,
    ".F": Currency.EUR,
    ".T": Currency.JPY,
}

# Recognised suffixes that map to currencies not yet in the Currency enum.
# These raise UnsupportedTickerError instead of silently defaulting to USD.
# Ordered longest-first to ensure .TWO is checked before .TW.
_UNSUPPORTED_SUFFIXES: dict[str, str] = {
    ".TWO": "TWD",   # Taiwan OTC (TWD)
    ".HK": "HKD",   # Hong Kong (HKD)
    ".KS": "KRW",   # Korea Stock Exchange (KRW)
    ".KQ": "KRW",   # KOSDAQ (KRW)
    ".TW": "TWD",   # Taiwan Stock Exchange (TWD)
    ".BK": "THB",   # Thailand (THB)
}


class UnsupportedTickerError(Exception):
    """Raised when a ticker suffix maps to a currency not yet in the Currency enum."""

    pass


def infer_currency_from_ticker(ticker: str) -> Currency:
    """
    Map a ticker symbol to its native trading currency.

    Rules:
    - Suffix-based for non-US exchanges (.DE → EUR, .T → JPY, etc.)
    - Default to USD for unsuffixed symbols (NVDA, ASX, MU, MRVL, …)

    Raises UnsupportedTickerError if the suffix is recognised but maps to
    a currency not yet supported in the Currency enum (e.g. .HK for HKD).
    """
    upper = ticker.upper()
    for suffix, currency in _SUFFIX_TO_CURRENCY.items():
        if upper.endswith(suffix.upper()):
            return currency

    for suffix, currency_name in _UNSUPPORTED_SUFFIXES.items():
        if upper.endswith(suffix.upper()):
            raise UnsupportedTickerError(
                f"Ticker {ticker!r} trades on an exchange whose currency "
                f"({currency_name}) is not yet supported. "
                f"Add Currency.{currency_name} and a {suffix} entry in tickers.py."
            )

    return Currency.USD
