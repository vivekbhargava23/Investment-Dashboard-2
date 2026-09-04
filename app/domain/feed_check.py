from __future__ import annotations

from decimal import Decimal
from statistics import median
from typing import Literal

from pydantic import BaseModel, ConfigDict

SUSPICIOUS_THRESHOLD_PCT = Decimal("15")


class FeedCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    isin: str
    ticker: str | None
    status: Literal["ok", "suspicious", "no_feed", "unchecked"]
    compared: int
    median_deviation_pct: Decimal | None
    avg_trade_price_eur: Decimal | None
    avg_close_eur: Decimal | None
    detail: str


def evaluate_deviations(
    isin: str,
    ticker: str | None,
    pairs: list[tuple[Decimal, Decimal]],
) -> FeedCheck:
    """Evaluate comparable ``(trade_price_eur, close_eur)`` pairs for one ISIN."""
    if ticker is None:
        return FeedCheck(
            isin=isin,
            ticker=None,
            status="unchecked",
            compared=0,
            median_deviation_pct=None,
            avg_trade_price_eur=None,
            avg_close_eur=None,
            detail="No mapped price feed is available for this ISIN.",
        )

    if not pairs:
        return FeedCheck(
            isin=isin,
            ticker=ticker,
            status="no_feed",
            compared=0,
            median_deviation_pct=None,
            avg_trade_price_eur=None,
            avg_close_eur=None,
            detail=f"No comparable historical closes were available for {ticker}.",
        )

    deviations = [abs(trade - close) / close * Decimal("100") for trade, close in pairs]
    if len(deviations) >= 3:
        central_deviation = median(deviations)
        central_label = "median"
    elif len(deviations) == 2:
        central_deviation = sum(deviations) / Decimal("2")
        central_label = "average"
    else:
        central_deviation = deviations[0]
        central_label = "deviation"

    count = Decimal(len(pairs))
    avg_trade = sum(trade for trade, _ in pairs) / count
    avg_close = sum(close for _, close in pairs) / count
    status: Literal["ok", "suspicious"] = (
        "ok" if central_deviation <= SUSPICIOUS_THRESHOLD_PCT else "suspicious"
    )

    return FeedCheck(
        isin=isin,
        ticker=ticker,
        status=status,
        compared=len(pairs),
        median_deviation_pct=central_deviation,
        avg_trade_price_eur=avg_trade,
        avg_close_eur=avg_close,
        detail=(
            f"Your trades averaged €{avg_trade:.2f}, {ticker} closed at "
            f"€{avg_close:.2f} ({central_label} {central_deviation:.1f}% off)."
        ),
    )
