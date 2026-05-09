from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.domain.analytics_views import (
    CurrentPositionCard,
    PostTradeWeightPreview,
    RiskBasedResult,
    SizerView,
    WeightBasedResult,
)
from app.domain.money import Currency, Money
from app.domain.positions import LivePosition, OpenLot, PortfolioSummary, Position
from app.services.analytics_sizer import MISSING_PRICE_REASON, STALE_PRICE_REASON
from app.ui.pages import analytics


def _columns(n: int) -> list[MagicMock]:
    cols = []
    for _ in range(n):
        col = MagicMock()
        col.__enter__ = MagicMock(return_value=col)
        col.__exit__ = MagicMock(return_value=False)
        cols.append(col)
    return cols


def _view(*, degraded_reason: str | None = None, include_results: bool = True) -> SizerView:
    current = CurrentPositionCard(
        ticker="AAPL",
        name="AAPL",
        weight_pct=Decimal("18"),
        market_value_eur=Money(amount=Decimal("18000"), currency=Currency.EUR),
        last_price_native=Money(amount=Decimal("200"), currency=Currency.USD),
        last_price_eur=Money(amount=Decimal("180"), currency=Currency.EUR),
        open_lot_count=2,
        staleness=degraded_reason,
    )
    if not include_results:
        return SizerView(
            current=current,
            risk_based=None,
            weight_based=None,
            post_trade=None,
            degraded_reason=degraded_reason,
        )
    return SizerView(
        current=current,
        risk_based=RiskBasedResult(
            shares=Decimal("69.44"),
            trade_value_eur=Money(amount=Decimal("12500"), currency=Currency.EUR),
            risk_eur=Money(amount=Decimal("1000"), currency=Currency.EUR),
            risk_pct_input=Decimal("1"),
            stop_price_native=Money(amount=Decimal("184"), currency=Currency.USD),
        ),
        weight_based=WeightBasedResult(
            shares=Decimal("11.11"),
            delta_eur=Money(amount=Decimal("2000"), currency=Currency.EUR),
            current_weight_pct=Decimal("18"),
            target_weight_pct=Decimal("20"),
        ),
        post_trade=PostTradeWeightPreview(
            current_weight_pct=Decimal("18"),
            new_weight_pct=Decimal("27.11"),
            bucket="amber",
        ),
        degraded_reason=degraded_reason,
    )


def _live_position(
    *,
    ticker: str = "AAPL",
    price_native: Decimal = Decimal("200"),
    currency: Currency = Currency.USD,
    fx_rate: Decimal = Decimal("0.9"),
    current_fx_rate: Decimal | None = Decimal("0.9"),
) -> LivePosition:
    lot = OpenLot(
        source_transaction_id=f"{ticker}-lot",
        ticker=ticker,
        trade_date=datetime(2025, 1, 1).date(),
        remaining_shares=Decimal("100"),
        cost_per_share_native=Money(amount=price_native, currency=currency),
        fx_rate_eur=fx_rate,
    )
    position = Position(
        ticker=ticker,
        open_shares=Decimal("100"),
        open_lots=(lot,),
        realised_gain_eur_ytd=Money(amount=Decimal("0"), currency=Currency.EUR),
        cost_basis_eur=Money(
            amount=Decimal("100") * price_native * fx_rate,
            currency=Currency.EUR,
        ),
    )
    return LivePosition(
        position=position,
        live_price_native=Money(amount=price_native, currency=currency),
        live_value_eur=Money(
            amount=Decimal("100") * price_native * fx_rate,
            currency=Currency.EUR,
        ),
        unrealised_gain_eur=Money(amount=Decimal("0"), currency=Currency.EUR),
        unrealised_gain_pct=Decimal("0"),
        current_fx_rate=current_fx_rate,
        staleness_reason=None,
    )


def _summary() -> PortfolioSummary:
    return PortfolioSummary(
        total_value_eur=Money(amount=Decimal("100000"), currency=Currency.EUR),
        total_cost_basis_eur=Money(amount=Decimal("100000"), currency=Currency.EUR),
        total_unrealised_gain_eur=Money(amount=Decimal("0"), currency=Currency.EUR),
        total_unrealised_gain_pct=Decimal("0"),
        total_realised_gain_eur_ytd=Money(amount=Decimal("0"), currency=Currency.EUR),
        position_count=1,
        live_position_count=1,
        staleness="live",
        as_of=datetime(2026, 5, 9, 12, 0),
    )


def test_sizer_tab_empty_portfolio_shows_info_only() -> None:
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.get_repository") as mock_repo,
        patch("app.ui.pages.analytics._cached_concentration_live_positions") as mock_live,
    ):
        mock_repo.return_value.load_all.return_value = []
        mock_live.return_value = {}
        analytics._render_sizer_tab()

    mock_st.info.assert_called_once_with(
        "No positions yet — add transactions in Manage Portfolio to enable sizing."
    )
    mock_st.columns.assert_not_called()


def test_sizer_tab_smoke_renders_inputs_and_result_cards() -> None:
    live = {"AAPL": _live_position()}
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.get_repository") as mock_repo,
        patch("app.ui.pages.analytics._cached_concentration_live_positions") as mock_live,
        patch("app.ui.pages.analytics._cached_concentration_summary") as mock_summary,
        patch("app.ui.pages.analytics.compute_sizer_view") as mock_compute,
        patch("app.ui.pages.analytics.render_html") as mock_html,
    ):
        mock_st.session_state = {}
        mock_st.columns.return_value = _columns(2)
        mock_st.selectbox.return_value = "AAPL"
        mock_st.radio.return_value = "buy"
        mock_st.number_input.side_effect = [1.0, 8.0, 20.0]
        mock_repo.return_value.load_all.return_value = []
        mock_live.return_value = live
        mock_summary.return_value = _summary()
        mock_compute.return_value = _view()

        analytics._render_sizer_tab()

    mock_st.columns.assert_called_once_with([1, 1])
    mock_compute.assert_called_once()
    assert mock_html.call_count == 4


def test_sizer_tab_live_eur_price_without_fx_rate_renders_results() -> None:
    live = {
        "HY9H.F": _live_position(
            ticker="HY9H.F",
            price_native=Decimal("1065"),
            currency=Currency.EUR,
            fx_rate=Decimal("1"),
            current_fx_rate=None,
        )
    }
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.get_repository") as mock_repo,
        patch("app.ui.pages.analytics._cached_concentration_live_positions") as mock_live,
        patch("app.ui.pages.analytics._cached_concentration_summary") as mock_summary,
        patch("app.ui.pages.analytics.render_html") as mock_html,
    ):
        mock_st.session_state = {}
        mock_st.columns.return_value = _columns(2)
        mock_st.selectbox.return_value = "HY9H.F"
        mock_st.radio.return_value = "buy"
        mock_st.number_input.side_effect = [1.0, 8.0, 20.0]
        mock_repo.return_value.load_all.return_value = []
        mock_live.return_value = live
        mock_summary.return_value = _summary()

        analytics._render_sizer_tab()

    mock_st.error.assert_not_called()
    assert mock_html.call_count == 4
    rendered_html = "".join(call.args[0] for call in mock_html.call_args_list)
    assert "HY9H.F" in rendered_html
    assert "€1.065,00" in rendered_html


def test_sizer_view_missing_price_banner_hides_result_cards() -> None:
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.render_html") as mock_html,
    ):
        analytics._render_sizer_view(
            _view(degraded_reason=MISSING_PRICE_REASON, include_results=False)
        )

    mock_st.error.assert_called_once_with(MISSING_PRICE_REASON)
    mock_html.assert_not_called()


def test_sizer_view_stale_banner_still_renders_results() -> None:
    with (
        patch("app.ui.pages.analytics.st") as mock_st,
        patch("app.ui.pages.analytics.render_html") as mock_html,
    ):
        analytics._render_sizer_view(_view(degraded_reason=STALE_PRICE_REASON))

    mock_st.warning.assert_called_once_with(STALE_PRICE_REASON)
    assert mock_html.call_count == 3


def test_weight_bar_preview_uses_shared_component() -> None:
    with patch("app.ui.pages.analytics.render_weight_bar") as mock_bar:
        mock_bar.return_value = "<bar />"
        html = analytics._build_post_trade_preview_html(_view())

    mock_bar.assert_called_once()
    assert mock_bar.call_args.kwargs["scale_max"] == Decimal("40")
    assert mock_bar.call_args.kwargs["danger_threshold"] == Decimal("35")
    assert mock_bar.call_args.args[0] == Decimal("27.11")
    assert "35% cap" in html


def test_share_display_uses_format_shares() -> None:
    with patch("app.ui.pages.analytics.format_shares") as mock_format:
        mock_format.return_value = "formatted"
        html = analytics._build_risk_result_card_html(_view())

    mock_format.assert_called_once_with(Decimal("69.44"))
    assert "formatted" in html
