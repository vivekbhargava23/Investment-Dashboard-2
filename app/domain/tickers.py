"""Ticker → native currency mapping. Single source of truth (ADR-005, TICKET-008c)."""
from app.domain.money import Currency

# Override map: checked before suffix rules. Use for tickers whose suffix would give
# the wrong currency or whose no-suffix default (USD) needs to be made explicit.
_OVERRIDE_MAP: dict[str, Currency] = {
    "HXSCL": Currency.USD,  # Korean GDR, USD-denominated on US exchanges
    "ASX": Currency.USD,    # Taiwanese ADR, USD-denominated on US exchanges
}

# Ordered longest-first so longer suffixes (e.g. .TWO) shadow shorter ones (e.g. .TW).
_SUFFIX_TO_CURRENCY: dict[str, Currency] = {
    # German regional exchanges and XETRA
    ".DE": Currency.EUR,
    ".SG": Currency.EUR,   # Stuttgart
    ".MU": Currency.EUR,   # Munich
    ".HM": Currency.EUR,   # Hamburg
    ".DU": Currency.EUR,   # Düsseldorf
    ".BE": Currency.EUR,   # Berlin
    ".F": Currency.EUR,    # Frankfurt
    # Other eurozone exchanges
    ".AS": Currency.EUR,   # Amsterdam
    ".MI": Currency.EUR,   # Milan
    ".PA": Currency.EUR,   # Paris
    ".BR": Currency.EUR,   # Brussels
    ".LS": Currency.EUR,   # Lisbon
    ".MC": Currency.EUR,   # Madrid
    ".HE": Currency.EUR,   # Helsinki
    ".VI": Currency.EUR,   # Vienna
    ".IR": Currency.EUR,   # Dublin
    ".LU": Currency.EUR,   # Luxembourg
    # Japan
    ".T": Currency.JPY,
    ".JP": Currency.JPY,
}

# Recognised suffixes that map to currencies not yet in the Currency enum.
# These raise UnsupportedTickerError instead of silently defaulting to USD.
# Ordered longest-first to ensure .TWO is checked before .TW.
_UNSUPPORTED_SUFFIXES: dict[str, str] = {
    ".TWO": "TWD",   # Taiwan OTC
    ".HK": "HKD",   # Hong Kong
    ".KS": "KRW",   # Korea Stock Exchange
    ".KQ": "KRW",   # KOSDAQ
    ".TW": "TWD",   # Taiwan Stock Exchange
    ".BK": "THB",   # Thailand
    ".L": "GBP",    # London Stock Exchange
    ".SW": "CHF",   # SIX Swiss Exchange
    ".VX": "CHF",   # SIX Swiss (alternate suffix)
    ".AX": "AUD",   # Australian Securities Exchange
    ".TO": "CAD",   # Toronto Stock Exchange
    ".V": "CAD",    # TSX Venture Exchange
}


class UnsupportedTickerError(Exception):
    """Raised when a ticker suffix maps to a currency not yet in the Currency enum."""

    pass


def infer_currency_from_ticker(ticker: str) -> Currency:
    """
    Map a ticker symbol to its native trading currency.

    Rules (in order):
    1. Override map — explicit per-ticker exceptions take precedence.
    2. Suffix-based — .DE/.F/etc. → EUR, .T/.JP → JPY, plain symbols → USD.
    3. Unknown suffixes that map to unsupported currencies raise UnsupportedTickerError.
    4. Default: USD (plain symbols with no recognised suffix).

    Raises UnsupportedTickerError if the suffix is recognised but maps to
    a currency not yet supported in the Currency enum (e.g. .HK for HKD).
    """
    upper = ticker.upper()

    if upper in _OVERRIDE_MAP:
        return _OVERRIDE_MAP[upper]

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
