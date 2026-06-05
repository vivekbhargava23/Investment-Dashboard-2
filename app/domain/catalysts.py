from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CatalystCategory = Literal[
    "earnings", "macro", "product", "regulatory", "dividend", "lockup"
]
Impact = Literal["high", "med", "low"]
Scope = Literal["position", "portfolio"]
DateConfidence = Literal["confirmed", "estimated"]
TimeBand = Literal["this_week", "this_month", "next_3_months", "later"]


class CatalystEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str | None
    date: date
    label: str
    category: CatalystCategory
    impact: Impact
    scope: Scope
    date_confidence: DateConfidence
    source: str = ""
    notes: str = ""


class CatalystsDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: int = 1
    updated: date | None = None
    events: list[CatalystEvent] = Field(default_factory=list)


def upcoming(
    events: list[CatalystEvent],
    *,
    as_of: date,
    within_days: int | None = None,
) -> list[CatalystEvent]:
    """Events on/after ``as_of``, sorted ascending by date.

    Optionally capped to a ``within_days`` horizon (inclusive).
    """
    horizon_end: date | None = None
    if within_days is not None:
        horizon_end = as_of + timedelta(days=within_days)
    kept = [
        e
        for e in events
        if e.date >= as_of and (horizon_end is None or e.date <= horizon_end)
    ]
    return sorted(kept, key=lambda e: e.date)


def for_ticker(events: list[CatalystEvent], ticker: str) -> list[CatalystEvent]:
    """Position events for ``ticker`` plus all portfolio-scope events."""
    return [
        e
        for e in events
        if (e.scope == "position" and e.ticker == ticker) or e.scope == "portfolio"
    ]


def time_band(event: CatalystEvent, *, as_of: date) -> TimeBand:
    """Bucket an event's date relative to ``as_of`` into a timeline band."""
    delta = (event.date - as_of).days
    if delta <= 7:
        return "this_week"
    if delta <= 31:
        return "this_month"
    if delta <= 92:
        return "next_3_months"
    return "later"


_CATEGORY_KEYWORDS: list[tuple[CatalystCategory, tuple[str, ...]]] = [
    ("earnings", ("earnings", "results", "quarterly", "q1", "q2", "q3", "q4")),
    ("macro", ("fomc", "cpi", "ecb", "jobs", "payroll", "jackson hole", "rate decision")),
    ("product", ("keynote", "launch", "gtc", "computex", "wwdc", "conference")),
    (
        "regulatory",
        ("export control", "antitrust", "fda", "tariff", "ruling", "bis"),
    ),
    ("dividend", ("ex-div", "ex div", "dividend")),
    ("lockup", ("lockup", "lock-up", "index", "rebalance")),
]


def categorise(
    label: str, *, hint: CatalystCategory | None = None
) -> CatalystCategory:
    """Assign a category from keyword rules. ``hint`` wins if provided.

    Advisory only — explicit values in the JSON always take precedence.
    """
    if hint is not None:
        return hint
    lowered = label.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "product"


def default_impact(
    category: CatalystCategory, *, is_decision: bool = False
) -> Impact:
    """Default impact for a category. Advisory only; JSON values win."""
    if category == "earnings":
        return "high"
    if category == "regulatory":
        return "high" if is_decision else "med"
    if category == "macro":
        return "med"
    if category == "product":
        return "med" if is_decision else "low"
    return "low"
