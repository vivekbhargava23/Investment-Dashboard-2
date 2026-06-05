from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from app.domain.catalysts import CatalystEvent, for_ticker, upcoming
from app.ports.catalysts import CatalystsRepository


def get_portfolio_catalysts(
    held_tickers: Iterable[str],
    *,
    as_of: date,
    repo: CatalystsRepository,
    within_days: int | None = None,
) -> list[CatalystEvent]:
    """Upcoming catalysts for the held set plus all portfolio-wide events.

    Keeps events whose ``ticker`` is in ``held_tickers`` or whose ``scope`` is
    ``portfolio``, filters to ``>= as_of``, and sorts ascending by date.
    """
    held = set(held_tickers)
    doc = repo.load()
    relevant = [
        e
        for e in doc.events
        if e.scope == "portfolio" or (e.ticker is not None and e.ticker in held)
    ]
    return upcoming(relevant, as_of=as_of, within_days=within_days)


def get_position_catalysts(
    ticker: str,
    *,
    as_of: date,
    repo: CatalystsRepository,
) -> list[CatalystEvent]:
    """Upcoming catalysts for a single position (plus portfolio-wide events)."""
    doc = repo.load()
    return upcoming(for_ticker(doc.events, ticker), as_of=as_of)
