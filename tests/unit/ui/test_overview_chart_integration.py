import pytest

from app.domain.market_data import ChartPeriod, OhlcUnavailableError
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
    rendered: list[str] = []
    monkeypatch.setattr(overview, "render_html", lambda html: rendered.append(html))

    overview._render_sell_button("NVDA")

    assert "/?page=simulator&ticker=NVDA" in rendered[0]
    assert "⚡" in rendered[0]


def test_mini_chart_panel_uses_research_style_metrics_and_candlestick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state: dict[str, str] = {"overview_selected_ticker": "NVDA"}
    metrics: list[tuple[tuple[object, ...], dict[str, object]]] = []
    rendered: list[tuple[str, int]] = []
    monkeypatch.setattr(overview.st, "session_state", state)
    monkeypatch.setattr(overview.st, "columns", lambda spec: [_Column() for _ in range(spec)])
    monkeypatch.setattr(
        overview.st,
        "metric",
        lambda *args, **kwargs: metrics.append((args, kwargs)),
    )
    monkeypatch.setattr(
        overview.st,
        "radio",
        lambda *args, **kwargs: ChartPeriod.SIX_MONTH,
    )
    monkeypatch.setattr(overview.st, "button", lambda *args, **kwargs: False)
    monkeypatch.setattr(overview, "render_html", lambda html: None)

    def fake_series(ticker: str, period_value: str):
        return make_ohlc_series(ticker=ticker, period=ChartPeriod(period_value))

    monkeypatch.setattr(
        overview,
        "_cached_ohlc_for_overview",
        fake_series,
    )
    monkeypatch.setattr(
        overview,
        "render_candlestick",
        lambda series, height: rendered.append((series.ticker, height)),
    )

    overview._render_mini_chart_panel()

    assert [call[0][0] for call in metrics] == ["Latest", "Period change", "Period"]
    assert rendered == [("NVDA", 420)]
