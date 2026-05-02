"""
app/utils/formatting.py

Centralised formatting utilities for all display values.
All UI components import from here — never format inline.

Usage:
    from app.utils.formatting import fmt_currency, fmt_percent, fmt_gain
    fmt_currency(1234.56)        → "€1,234.56"
    fmt_percent(0.0234)          → "+2.34%"
    fmt_gain(266.21, 1.54)       → "+€266.21 (+1.54%)"
    fmt_currency(-500.00)        → "-€500.00"
"""

from datetime import date, datetime


def fmt_currency(
    value: float | None,
    symbol: str = "€",
    decimals: int = 2,
    show_sign: bool = False,
) -> str:
    """
    Format a float as a currency string.

    Args:
        value:      The numeric value to format
        symbol:     Currency symbol prefix (default €)
        decimals:   Decimal places (default 2)
        show_sign:  If True, always show + or - sign

    Returns:
        Formatted string e.g. "€1,234.56" or "+€234.56"

    Examples:
        fmt_currency(1234.56)           → "€1,234.56"
        fmt_currency(-500.00)           → "-€500.00"
        fmt_currency(234.56, show_sign=True) → "+€234.56"
        fmt_currency(None)              → "—"
    """
    if value is None:
        return "—"

    sign = ""
    if show_sign:
        sign = "+" if value >= 0 else "-"
        value = abs(value)
    elif value < 0:
        sign = "-"
        value = abs(value)

    formatted = f"{value:,.{decimals}f}"
    return f"{sign}{symbol}{formatted}"


def fmt_percent(
    value: float | None,
    decimals: int = 2,
    show_sign: bool = True,
) -> str:
    """
    Format a decimal ratio as a display percentage string.

    Always treats value as a decimal ratio (0.15 = 15%).
    Handles gains > 100% correctly (2.36 → "+236.00%").

    Args:
        value:      Decimal ratio e.g. 0.0234 for 2.34%, 2.36 for 236%
        decimals:   Decimal places (default 2)
        show_sign:  If True, prepend + for positive values

    Returns:
        Formatted string e.g. "+2.34%" or "-5.67%"

    Examples:
        fmt_percent(0.0234)     → "+2.34%"
        fmt_percent(-0.0567)    → "-5.67%"
        fmt_percent(2.36)       → "+236.00%"
        fmt_percent(None)       → "—"
    """
    if value is None:
        return "—"

    pct = value * 100
    sign = "+" if show_sign and pct >= 0 else ""
    return f"{sign}{pct:.{decimals}f}%"


def fmt_gain(
    absolute: float | None,
    percent: float | None,
    symbol: str = "€",
) -> str:
    """
    Format an absolute gain/loss with its percentage.

    Args:
        absolute:   Absolute gain/loss in currency
        percent:    Decimal ratio e.g. 0.0154 for 1.54%, 2.36 for 236%
        symbol:     Currency symbol (default €)

    Returns:
        Combined string e.g. "+€266.21 (+1.54%)"

    Examples:
        fmt_gain(266.21, 0.0154)    → "+€266.21 (+1.54%)"
        fmt_gain(-500.00, -0.0567)  → "-€500.00 (-5.67%)"
        fmt_gain(None, None)        → "—"
    """
    if absolute is None or percent is None:
        return "—"

    currency = fmt_currency(absolute, symbol=symbol, show_sign=True)
    pct = fmt_percent(percent, show_sign=True)
    return f"{currency} ({pct})"


def fmt_date(value: date | datetime | str | None) -> str:
    """
    Format a date for display.

    Args:
        value: date, datetime, ISO string, or None

    Returns:
        Formatted string e.g. "26 Apr 2026"

    Examples:
        fmt_date(date(2026, 4, 26))     → "26 Apr 2026"
        fmt_date("2026-04-26")          → "26 Apr 2026"
        fmt_date(None)                  → "—"
    """
    if value is None:
        return "—"

    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            return value

    return value.strftime("%-d %b %Y")


def fmt_shares(value: float | None, decimals: int = 4) -> str:
    """
    Format a share quantity.

    Args:
        value:      Number of shares
        decimals:   Decimal places for fractional shares

    Returns:
        Formatted string e.g. "6.0000" or "—"
    """
    if value is None:
        return "—"

    # Whole numbers show without decimals
    if value == int(value):
        return f"{int(value):,}"

    return f"{value:,.{decimals}f}"


def fmt_ticker(ticker: str) -> str:
    """
    Clean and uppercase a ticker symbol for display.

    Args:
        ticker: Raw ticker string e.g. "nvda" or " NVDA "

    Returns:
        Cleaned uppercase ticker e.g. "NVDA"
    """
    return ticker.strip().upper()


def colour_gain(value: float | None) -> str:
    """
    Return a Streamlit-compatible colour string based on gain/loss.

    Args:
        value: Positive = gain, negative = loss, zero = neutral

    Returns:
        CSS colour string for use in st.markdown delta displays
    """
    if value is None:
        return "normal"
    if value > 0:
        return "normal"   # Streamlit renders green for positive delta
    if value < 0:
        return "inverse"  # Streamlit renders red for negative delta
    return "off"