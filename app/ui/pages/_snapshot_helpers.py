from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.domain.company import PriceHistoryPoint, QuarterlyFundamentals


def filter_price_history(
    history: list[PriceHistoryPoint], years: int
) -> list[PriceHistoryPoint]:
    """Return history within the last `years` years from the final data point."""
    if not history:
        return []
    last_date = history[-1].date
    cutoff = last_date - timedelta(days=years * 365)
    return [p for p in history if p.date >= cutoff]


def compute_sma(closes: list[Decimal], period: int) -> list[Decimal | None]:
    """Simple moving average; None for positions before the first full window."""
    result: list[Decimal | None] = []
    for i, _ in enumerate(closes):
        if i < period - 1:
            result.append(None)
        else:
            window = closes[i - period + 1 : i + 1]
            result.append(sum(window, Decimal(0)) / period)
    return result


def compute_revenue_cagr(
    quarters: list[QuarterlyFundamentals],
) -> tuple[Decimal | None, str]:
    """Return (cagr_decimal, label) using up to 12 quarters back.

    Returns (None, '') if insufficient data.
    Uses dates to compute actual year span so gaps in coverage are handled correctly.
    """
    n_all = len(quarters)
    if n_all < 2:
        return None, ""

    # Latest quarter with valid revenue
    valid_all = [q for q in quarters if q.revenue is not None and q.revenue > 0]
    if len(valid_all) < 2:
        return None, ""
    latest = valid_all[-1]

    # Walk up to 12 quarters back from the end and find the earliest with valid revenue
    lookback = min(n_all - 1, 12)
    window = quarters[n_all - lookback - 1 :]
    earliest_valid = [q for q in window if q.revenue is not None and q.revenue > 0]
    if not earliest_valid:
        return None, ""
    earliest = earliest_valid[0]

    if earliest is latest:
        return None, ""

    if earliest.revenue is None or latest.revenue is None or earliest.revenue <= 0:
        return None, ""

    days = (latest.period_end - earliest.period_end).days
    if days <= 0:
        return None, ""

    years = Decimal(str(days)) / Decimal("365.25")
    if years < Decimal("0.5"):
        return None, ""

    try:
        cagr = (latest.revenue / earliest.revenue) ** (Decimal("1") / years) - Decimal("1")
    except Exception:
        return None, ""

    if years >= Decimal("2.9"):
        label = "3Y CAGR"
    elif years >= Decimal("1.9"):
        label = "2Y CAGR"
    else:
        label = f"{round(float(years)):.0f}Y CAGR"

    return cagr, label


def compute_revenue_series(quarters: list[QuarterlyFundamentals]) -> list[Decimal | None]:
    """Last 8 quarters of revenue."""
    recent = quarters[-8:] if len(quarters) >= 8 else quarters
    return [q.revenue for q in recent]


def compute_ebit_margin(quarters: list[QuarterlyFundamentals]) -> Decimal | None:
    """Latest-quarter EBIT margin = operating_income / revenue."""
    if not quarters:
        return None
    latest = quarters[-1]
    if latest.operating_income is None or latest.revenue is None or latest.revenue == 0:
        return None
    return latest.operating_income / latest.revenue


def compute_ebit_margin_series(
    quarters: list[QuarterlyFundamentals],
) -> list[Decimal | None]:
    """Last 8 quarters of EBIT margin (operating_income / revenue)."""
    recent = quarters[-8:] if len(quarters) >= 8 else quarters
    result: list[Decimal | None] = []
    for q in recent:
        if q.operating_income is None or q.revenue is None or q.revenue == 0:
            result.append(None)
        else:
            result.append(q.operating_income / q.revenue)
    return result


def _ttm_ebitda(quarters: list[QuarterlyFundamentals]) -> Decimal | None:
    """Sum of last 4 quarters of EBITDA; annualizes if fewer are available."""
    valid = [q for q in quarters if q.ebitda is not None]
    if not valid:
        return None
    recent = valid[-4:]
    total = sum((q.ebitda for q in recent if q.ebitda is not None), Decimal(0))
    if len(recent) < 4:
        total = total * Decimal("4") / Decimal(str(len(recent)))
    return total


def compute_net_debt_ebitda(quarters: list[QuarterlyFundamentals]) -> Decimal | None:
    """Latest net_debt / TTM EBITDA. Returns None if EBITDA <= 0."""
    if not quarters:
        return None
    latest = quarters[-1]
    if latest.net_debt is None:
        return None
    ttm = _ttm_ebitda(quarters)
    if ttm is None or ttm <= 0:
        return None
    return latest.net_debt / ttm


def compute_net_debt_ebitda_series(
    quarters: list[QuarterlyFundamentals],
) -> list[Decimal | None]:
    """Last 8 quarters of net_debt / EBITDA (using TTM EBITDA from each quarter's context)."""
    recent = quarters[-8:] if len(quarters) >= 8 else quarters
    offset = len(quarters) - len(recent)
    result: list[Decimal | None] = []
    for i, q in enumerate(recent):
        if q.net_debt is None:
            result.append(None)
            continue
        context = quarters[: offset + i + 1]
        ttm = _ttm_ebitda(context)
        if ttm is None or ttm <= 0:
            result.append(None)
        else:
            result.append(q.net_debt / ttm)
    return result


def _ttm_fcf(quarters: list[QuarterlyFundamentals]) -> Decimal | None:
    """Sum of last 4 quarters of free_cash_flow."""
    valid = [q for q in quarters if q.free_cash_flow is not None]
    if not valid:
        return None
    recent = valid[-4:]
    return sum((q.free_cash_flow for q in recent if q.free_cash_flow is not None), Decimal(0))


def compute_fcf_yield(
    quarters: list[QuarterlyFundamentals],
    market_cap_amount: Decimal | None,
) -> Decimal | None:
    """TTM FCF / market_cap. Returns None if either is unavailable."""
    if market_cap_amount is None or market_cap_amount <= 0:
        return None
    ttm = _ttm_fcf(quarters)
    if ttm is None:
        return None
    return ttm / market_cap_amount


def compute_fcf_series(quarters: list[QuarterlyFundamentals]) -> list[Decimal | None]:
    """Last 8 quarters of FCF."""
    recent = quarters[-8:] if len(quarters) >= 8 else quarters
    return [q.free_cash_flow for q in recent]


def compute_historical_pe_range(
    quarters: list[QuarterlyFundamentals],
    price_history: list[PriceHistoryPoint],
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Return (min_pe, current_pe, max_pe) or None if data is insufficient.

    For each quarter-end with ≥4 quarters of TTM EPS, looks up the closest
    price within ±5 days and records the trailing P/E. Returns None if fewer
    than 4 quarters are available or if current TTM EPS is non-positive.
    """
    if len(quarters) < 4 or not price_history:
        return None

    price_by_date: dict[date, Decimal] = {p.date: p.close for p in price_history}

    def closest_price(target: date) -> Decimal | None:
        for offset in range(6):
            for delta in (offset, -offset):
                candidate = target + timedelta(days=delta)
                if candidate in price_by_date:
                    return price_by_date[candidate]
        return None

    historical_pes: list[Decimal] = []
    for i in range(3, len(quarters)):
        window = quarters[i - 3 : i + 1]
        if any(q.eps_diluted is None for q in window):
            continue
        ttm_eps = sum((q.eps_diluted for q in window if q.eps_diluted is not None), Decimal(0))
        if ttm_eps <= 0:
            continue
        price = closest_price(quarters[i].period_end)
        if price is None or price <= 0:
            continue
        pe = price / ttm_eps
        if pe > 0:
            historical_pes.append(pe)

    if not historical_pes:
        return None

    latest_window = quarters[-4:]
    if any(q.eps_diluted is None for q in latest_window):
        return None
    latest_ttm_eps = sum(
        (q.eps_diluted for q in latest_window if q.eps_diluted is not None), Decimal(0)
    )
    if latest_ttm_eps <= 0:
        return None

    latest_price = price_history[-1].close
    if latest_price <= 0:
        return None

    current_pe = latest_price / latest_ttm_eps
    if current_pe <= 0:
        return None

    all_pes = historical_pes + [current_pe]
    return min(all_pes), current_pe, max(all_pes)
