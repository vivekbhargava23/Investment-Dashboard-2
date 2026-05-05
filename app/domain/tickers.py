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
    # .HK (HKD) intentionally omitted — HKD not yet in Currency enum.
    # Add when a HKD-priced transaction is onboarded. See TICKET-008c notes.
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

    # Recognised-but-unsupported suffixes.  Keep this list explicit so future
    # contributors know exactly which suffixes need a Currency enum extension.
    _UNSUPPORTED_SUFFIXES: tuple[str, ...] = (".HK",)
    for suffix in _UNSUPPORTED_SUFFIXES:
        if upper.endswith(suffix.upper()):
            raise UnsupportedTickerError(
                f"Ticker {ticker!r} trades on an exchange whose currency (HKD) is not yet "
                f"supported. Add Currency.HKD and a .HK entry in tickers.py."
            )

    return Currency.USD
