from datetime import date
from decimal import Decimal

from app.domain.money import Money


def format_eur(money: Money, signed: bool = False) -> str:
    """
    German format: "€25.045,38" (period thousands, comma decimal).
    For signed=True, prepend + for positive: "+€4.003,60".
    """
    amount = money.amount
    # Round to 2 decimal places
    amount = amount.quantize(Decimal("0.01"))
    
    is_negative = amount < 0
    abs_amount = abs(amount)
    
    # Format with comma as decimal and dot as thousands
    s = f"{abs_amount:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    
    prefix = ""
    if is_negative:
        prefix = "-"
    elif signed and amount > 0:
        prefix = "+"
        
    return f"{prefix}€{s}"


def format_pct(value: Decimal, signed: bool = False) -> str:
    """
    "19.0%" or "+19.0%". Always one decimal place.
    """
    # Round to 1 decimal place
    val = value.quantize(Decimal("0.1"))
    
    is_negative = val < 0
    abs_val = abs(val)
    
    prefix = ""
    if is_negative:
        prefix = "-"
    elif signed and val > 0:
        prefix = "+"
        
    return f"{prefix}{abs_val:.1f}%"


def format_shares(value: Decimal) -> str:
    """
    "12,5000" (4 dp, comma decimal).
    """
    val = value.quantize(Decimal("0.0001"))
    s = f"{val:.4f}"
    return s.replace(".", ",")


def format_date(value: date) -> str:
    """
    ISO "2026-05-02".
    """
    return value.isoformat()


def gain_class(value: Decimal) -> str:
    """
    Returns CSS class name: "gain-positive" if > 0, "gain-negative" if < 0, "gain-neutral" if == 0.
    """
    if value > 0:
        return "gain-positive"
    if value < 0:
        return "gain-negative"
    return "gain-neutral"
