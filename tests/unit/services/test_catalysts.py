"""Unit tests for the catalysts service."""

from __future__ import annotations

from datetime import date

from app.domain.catalysts import CatalystEvent, CatalystsDocument
from app.services.catalysts import get_portfolio_catalysts, get_position_catalysts

_AS_OF = date(2026, 6, 5)


class _FakeRepo:
    def __init__(self, doc: CatalystsDocument) -> None:
        self._doc = doc

    def load(self) -> CatalystsDocument:
        return self._doc

    def save(self, doc: CatalystsDocument) -> None:  # pragma: no cover - unused
        self._doc = doc


def _event(
    *,
    ticker: str | None,
    day: date,
    scope: str = "position",
) -> CatalystEvent:
    return CatalystEvent(
        ticker=ticker,
        date=day,
        label="evt",
        category="earnings",
        impact="high",
        scope=scope,  # type: ignore[arg-type]
        date_confidence="confirmed",
        source="src",
    )


def test_get_portfolio_catalysts_includes_held_and_macro_excludes_others() -> None:
    nvda = _event(ticker="NVDA", day=date(2026, 6, 20))
    msft = _event(ticker="MSFT", day=date(2026, 6, 21))
    macro = _event(ticker=None, day=date(2026, 6, 12), scope="portfolio")
    repo = _FakeRepo(CatalystsDocument(events=[nvda, msft, macro]))

    result = get_portfolio_catalysts(["NVDA"], as_of=_AS_OF, repo=repo)

    assert result == [macro, nvda]
    assert msft not in result


def test_get_portfolio_catalysts_filters_past_and_honours_horizon() -> None:
    past = _event(ticker="NVDA", day=date(2026, 5, 1))
    soon = _event(ticker="NVDA", day=date(2026, 6, 10))
    far = _event(ticker="NVDA", day=date(2026, 9, 1))
    repo = _FakeRepo(CatalystsDocument(events=[past, soon, far]))

    result = get_portfolio_catalysts(
        ["NVDA"], as_of=_AS_OF, repo=repo, within_days=30
    )

    assert result == [soon]


def test_get_position_catalysts_includes_portfolio_events() -> None:
    nvda = _event(ticker="NVDA", day=date(2026, 6, 20))
    macro = _event(ticker=None, day=date(2026, 6, 12), scope="portfolio")
    other = _event(ticker="MSFT", day=date(2026, 6, 21))
    repo = _FakeRepo(CatalystsDocument(events=[nvda, macro, other]))

    result = get_position_catalysts("NVDA", as_of=_AS_OF, repo=repo)

    assert result == [macro, nvda]
