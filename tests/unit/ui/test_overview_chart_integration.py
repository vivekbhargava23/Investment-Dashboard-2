from decimal import Decimal

import pytest

from app.domain.market_data import ChartPeriod, OhlcUnavailableError
from app.ui.components._chart_styles import CANDLE_DOWN, CANDLE_UP
from app.ui.pages import overview
from tests.fakes.ohlc import make_ohlc_series


class _Column:
    def __enter__(self) -> "_Column":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_sparkline_failure_renders_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    placeholders: list[str] = []
    rendered: list[str] = []

    def raise_unavailable(ticker: str, period_value: str):
        raise OhlcUnavailableError(ticker, "fixture unavailable")

    def fake_sparkline(series, height: int, width: int) -> None:  # type: ignore[no-untyped-def]
        rendered.append(series.ticker)

    monkeypatch.setattr(overview, "_cached_ohlc_for_overview", raise_unavailable)
    monkeypatch.setattr(overview, "_trend_placeholder", lambda: placeholders.append("—"))
    monkeypatch.setattr(overview, "render_sparkline", fake_sparkline)

    overview._render_trend_cell("NVDA")

    assert placeholders == ["—"]
    assert rendered == []


def test_sparkline_success_renders_one_chart(monkeypatch: pytest.MonkeyPatch) -> None:
    rendered: list[tuple[str, int, int]] = []
    buttons: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_series(ticker: str, period_value: str):
        return make_ohlc_series(ticker=ticker, period=ChartPeriod(period_value))

    def fake_sparkline(series, height: int, width: int) -> None:  # type: ignore[no-untyped-def]
        rendered.append((series.ticker, height, width))

    monkeypatch.setattr(
        overview,
        "_cached_ohlc_for_overview",
        fake_series,
    )
    monkeypatch.setattr(overview, "render_sparkline", fake_sparkline)
    monkeypatch.setattr(overview.st, "columns", lambda spec, gap=None: [_Column(), _Column()])
    monkeypatch.setattr(
        overview.st,
        "button",
        lambda *args, **kwargs: buttons.append((args, kwargs)) and False,
    )

    overview._render_trend_cell("NVDA")

    assert rendered == [("NVDA", 30, 100)]
    assert buttons[0][0][0] == "🔍"


def test_chart_button_sets_selected_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, str | None] = {}
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(overview.st, "session_state", state)
    monkeypatch.setattr(
        overview.st,
        "button",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )

    overview._render_chart_button("NVDA")

    assert state["overview_selected_ticker"] == "NVDA"
    assert calls[0][0][0] == "🔍"
    assert "use_container_width" not in calls[0][1]


def test_chart_button_toggles_selected_ticker_off(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, str | None] = {"overview_selected_ticker": "NVDA"}
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(overview.st, "session_state", state)
    monkeypatch.setattr(
        overview.st,
        "button",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )

    overview._render_chart_button("NVDA")

    assert state["overview_selected_ticker"] is None
    assert calls[0][0][0] == "×"


def test_sell_button_routes_to_simulator(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, str | None] = {}
    query_params: dict[str, str] = {}
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(overview.st, "session_state", state)
    monkeypatch.setattr(overview.st, "query_params", query_params)
    monkeypatch.setattr(
        overview.st,
        "button",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )

    overview._render_sell_button("NVDA")

    assert state["simulator_default_ticker"] == "NVDA"
    assert query_params["page"] == "simulator"
    assert calls[0][0][0] == "📉"
    assert "use_container_width" not in calls[0][1]


def test_mini_chart_color_uses_period_change() -> None:
    positive = make_ohlc_series()
    negative = positive.model_copy(
        update={
            "bars": (
                positive.bars[0],
                positive.bars[1].model_copy(update={"close": Decimal("90")}),
            )
        }
    )

    assert overview._mini_chart_color(positive) == CANDLE_UP
    assert overview._mini_chart_color(negative) == CANDLE_DOWN
