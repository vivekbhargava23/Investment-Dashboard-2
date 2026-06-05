"""Unit tests for the pure catalysts domain layer."""

from __future__ import annotations

from datetime import date

from app.domain.catalysts import (
    CatalystEvent,
    CatalystsDocument,
    categorise,
    default_impact,
    for_ticker,
    time_band,
    upcoming,
)

_AS_OF = date(2026, 6, 5)


def _event(
    *,
    ticker: str | None,
    day: date,
    label: str = "evt",
    category: str = "earnings",
    impact: str = "high",
    scope: str = "position",
    confidence: str = "confirmed",
) -> CatalystEvent:
    return CatalystEvent(
        ticker=ticker,
        date=day,
        label=label,
        category=category,  # type: ignore[arg-type]
        impact=impact,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        date_confidence=confidence,  # type: ignore[arg-type]
    )


def test_for_ticker_returns_position_and_portfolio_events() -> None:
    nvda = _event(ticker="NVDA", day=date(2026, 6, 20))
    msft = _event(ticker="MSFT", day=date(2026, 6, 21))
    macro = _event(ticker=None, day=date(2026, 6, 12), scope="portfolio")
    events = [nvda, msft, macro]

    result = for_ticker(events, "NVDA")

    assert nvda in result
    assert macro in result
    assert msft not in result


def test_upcoming_drops_past_and_sorts_ascending() -> None:
    past = _event(ticker="NVDA", day=date(2026, 6, 1))
    soon = _event(ticker="NVDA", day=date(2026, 6, 10))
    later = _event(ticker="NVDA", day=date(2026, 7, 1))
    on_as_of = _event(ticker="NVDA", day=_AS_OF)

    result = upcoming([later, past, soon, on_as_of], as_of=_AS_OF)

    assert result == [on_as_of, soon, later]


def test_upcoming_respects_within_days_horizon() -> None:
    inside = _event(ticker="NVDA", day=date(2026, 6, 10))
    outside = _event(ticker="NVDA", day=date(2026, 7, 30))

    result = upcoming([inside, outside], as_of=_AS_OF, within_days=30)

    assert result == [inside]


def test_time_band_buckets() -> None:
    assert time_band(_event(ticker="X", day=date(2026, 6, 8)), as_of=_AS_OF) == "this_week"
    assert time_band(_event(ticker="X", day=date(2026, 6, 25)), as_of=_AS_OF) == "this_month"
    assert (
        time_band(_event(ticker="X", day=date(2026, 8, 4)), as_of=_AS_OF)
        == "next_3_months"
    )
    assert time_band(_event(ticker="X", day=date(2026, 12, 22)), as_of=_AS_OF) == "later"


def test_categorise_keyword_rules() -> None:
    assert categorise("Q1 FY27 earnings") == "earnings"
    assert categorise("FOMC decision") == "macro"
    assert categorise("Computex keynote") == "product"
    assert categorise("BIS export-control review") == "regulatory"
    assert categorise("Ex-dividend date") == "dividend"
    assert categorise("Lockup expiry") == "lockup"


def test_categorise_hint_wins() -> None:
    assert categorise("anything", hint="macro") == "macro"


def test_default_impact_rules() -> None:
    assert default_impact("earnings") == "high"
    assert default_impact("regulatory", is_decision=True) == "high"
    assert default_impact("regulatory") == "med"
    assert default_impact("macro") == "med"
    assert default_impact("product") == "low"
    assert default_impact("dividend") == "low"
    assert default_impact("lockup") == "low"


def test_document_defaults() -> None:
    doc = CatalystsDocument()
    assert doc.version == 1
    assert doc.updated is None
    assert doc.events == []
