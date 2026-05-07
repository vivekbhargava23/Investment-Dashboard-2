from decimal import Decimal
from typing import Any

import pytest

from app.domain.market_data import ChartPeriod, OhlcUnavailableError
from app.domain.money import Currency, Money
from app.ports.ticker_resolver import TickerMatch
from app.ui.pages import research
from tests.fakes.ohlc import make_ohlc_series


class _Column:
    def __enter__(self) -> "_Column":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _match() -> TickerMatch:
    return TickerMatch(
        symbol="APD",
        name="Air Products and Chemicals",
        exchange="NYSE",
        currency=Currency.USD,
        recent_price=Money(amount=Decimal("250"), currency=Currency.USD),
    )


@pytest.fixture(autouse=True)
def patch_streamlit(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {
        "markdown": [],
        "caption": [],
        "info": [],
        "warning": [],
        "metric": [],
        "button": [],
        "radio": [],
    }
    def fake_columns(spec):  # type: ignore[no-untyped-def]
        count = spec if isinstance(spec, int) else len(spec)
        return [_Column() for _ in range(count)]

    monkeypatch.setattr(research.st, "columns", fake_columns)
    monkeypatch.setattr(research.st, "markdown", lambda text: calls["markdown"].append(text))
    monkeypatch.setattr(research.st, "caption", lambda text: calls["caption"].append(text))
    monkeypatch.setattr(research.st, "info", lambda text: calls["info"].append(text))
    monkeypatch.setattr(research.st, "warning", lambda text: calls["warning"].append(text))
    monkeypatch.setattr(
        research.st,
        "metric",
        lambda *args, **kwargs: calls["metric"].append((args, kwargs)),
    )
    monkeypatch.setattr(
        research.st,
        "button",
        lambda *args, **kwargs: calls["button"].append((args, kwargs)) or False,
    )

    def fake_radio(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["radio"].append((args, kwargs))
        return ChartPeriod.SIX_MONTH

    monkeypatch.setattr(research.st, "radio", fake_radio)
    monkeypatch.setattr(research.st, "session_state", {})
    monkeypatch.setattr(research.st, "rerun", lambda: None)
    monkeypatch.setattr(research, "get_ticker_resolver", lambda: object())
    monkeypatch.setattr(research, "_portfolio_matches", lambda: ())
    return calls


def test_empty_state_renders_when_match_is_none(
    monkeypatch: pytest.MonkeyPatch,
    patch_streamlit: dict[str, list[Any]],
) -> None:
    monkeypatch.setattr(research, "render_ticker_searchbox", lambda **kwargs: None)

    research.render()

    assert patch_streamlit["info"] == ["Type a ticker symbol or company name above to begin."]


def test_header_and_chart_render_when_match_is_set(
    monkeypatch: pytest.MonkeyPatch,
    patch_streamlit: dict[str, list[Any]],
) -> None:
    rendered: list[str] = []
    monkeypatch.setattr(research, "render_ticker_searchbox", lambda **kwargs: _match())

    def fake_series(ticker: str, period_value: str):
        return make_ohlc_series(ticker=ticker, period=ChartPeriod(period_value))

    def fake_candlestick(series, height: int) -> None:  # type: ignore[no-untyped-def]
        rendered.append(series.ticker)

    monkeypatch.setattr(
        research,
        "_cached_research_series",
        fake_series,
    )
    monkeypatch.setattr(research, "render_candlestick", fake_candlestick)

    research.render()

    assert any("APD — Air Products and Chemicals" in item for item in patch_streamlit["markdown"])
    assert rendered == ["APD"]


def test_chart_unavailable_renders_warning(
    monkeypatch: pytest.MonkeyPatch,
    patch_streamlit: dict[str, list[Any]],
) -> None:
    monkeypatch.setattr(research, "render_ticker_searchbox", lambda **kwargs: _match())

    def raise_unavailable(ticker: str, period_value: str):
        raise OhlcUnavailableError(ticker, "fixture unavailable")

    monkeypatch.setattr(research, "_cached_research_series", raise_unavailable)

    research.render()

    assert patch_streamlit["warning"] == ["Chart unavailable: fixture unavailable"]


def test_period_selector_default_is_six_month(
    monkeypatch: pytest.MonkeyPatch,
    patch_streamlit: dict[str, list[Any]],
) -> None:
    monkeypatch.setattr(research, "render_ticker_searchbox", lambda **kwargs: None)

    research.render()

    _, kwargs = patch_streamlit["radio"][0]
    assert kwargs["index"] == list(ChartPeriod).index(ChartPeriod.SIX_MONTH)
