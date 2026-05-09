from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Literal

from app.domain.analytics_views import (
    CurrentPositionCard,
    PostTradeWeightPreview,
    RiskBasedResult,
    SizerView,
    WeightBasedResult,
)
from app.domain.money import Currency, Money
from app.domain.positions import LivePosition, PortfolioSummary
from app.domain.sizing import risk_based_shares, weight_based_delta_shares
from app.services.analytics_concentration import (
    BAR_SCALE_MAX_PCT,
    MAX_POSITION_WEIGHT_PCT,
)

__all__ = [
    "BAR_SCALE_MAX_PCT",
    "DEFAULT_RISK_PCT",
    "DEFAULT_STOP_PCT",
    "DEFAULT_TARGET_WEIGHT_PCT",
    "MAX_POSITION_WEIGHT_PCT",
    "compute_sizer_view",
    "to_base_eur",
]

DEFAULT_RISK_PCT: Final[Decimal] = Decimal("1.0")
DEFAULT_STOP_PCT: Final[Decimal] = Decimal("8.0")
DEFAULT_TARGET_WEIGHT_PCT: Final[Decimal] = Decimal("15.0")

MISSING_PRICE_REASON: Final[str] = "Selected ticker has no live price."
STALE_PRICE_REASON: Final[str] = "Selected ticker price is stale — results may be inaccurate."
ZERO_PORTFOLIO_REASON: Final[str] = "Portfolio has no value to size against."

_ZERO_EUR = Money(amount=Decimal("0"), currency=Currency.EUR)
_PCT_QUANT = Decimal("0.01")
_HUNDRED = Decimal("100")


def to_base_eur(amount: Decimal, currency: Currency, fx_rate: Decimal) -> Decimal:
    """Convert ``amount`` in ``currency`` to EUR using native-to-EUR ``fx_rate``.

    EUR inputs must use ``fx_rate == Decimal("1")`` so wiring bugs fail loudly.
    No rounding is applied here.
    """
    if currency == Currency.EUR:
        if fx_rate != Decimal("1"):
            raise AssertionError("EUR amounts must use fx_rate 1")
        return amount
    return amount * fx_rate


def compute_sizer_view(
    *,
    positions: list[LivePosition],
    summary: PortfolioSummary,
    selected_ticker: str,
    direction: Literal["buy", "sell"],
    risk_pct: Decimal,
    stop_pct: Decimal,
    target_weight_pct: Decimal,
) -> SizerView:
    """Compute both Position Sizer methods from current live positions."""
    position = _find_position(positions, selected_ticker)
    if position is None:
        return _degraded_empty_view(selected_ticker, ZERO_PORTFOLIO_REASON)

    current = _current_card(position, summary)
    portfolio_value = summary.total_value_eur.amount
    if position.live_price_native is None or position.live_value_eur is None:
        return _degraded_view(current, MISSING_PRICE_REASON)
    if position.current_fx_rate is None:
        return _degraded_view(current, MISSING_PRICE_REASON)
    if portfolio_value <= 0:
        return _degraded_view(current, ZERO_PORTFOLIO_REASON)

    price_native = position.live_price_native
    price_eur = to_base_eur(
        price_native.amount,
        price_native.currency,
        _fx_rate_for(position),
    )
    weight_price_eur = to_base_eur(
        price_native.amount,
        price_native.currency,
        _fx_rate_for(position),
    )

    raw_risk_shares = risk_based_shares(
        portfolio_value_eur=portfolio_value,
        risk_pct=risk_pct,
        stop_pct=stop_pct,
        price_eur=price_eur,
    )
    signed_risk_shares = raw_risk_shares if direction == "buy" else -raw_risk_shares
    trade_value_eur = abs(signed_risk_shares * price_eur)
    risk_eur_amount = to_base_eur(
        portfolio_value * risk_pct / _HUNDRED,
        Currency.EUR,
        Decimal("1"),
    )
    risk_based = RiskBasedResult(
        shares=signed_risk_shares,
        trade_value_eur=Money(amount=trade_value_eur, currency=Currency.EUR),
        risk_eur=Money(amount=risk_eur_amount, currency=Currency.EUR),
        risk_pct_input=risk_pct,
        stop_price_native=Money(
            amount=_stop_price_native(price_native.amount, stop_pct, direction),
            currency=price_native.currency,
        ),
    )

    weight_shares = weight_based_delta_shares(
        target_weight_pct=target_weight_pct,
        current_weight_pct=current.weight_pct,
        portfolio_value_eur=portfolio_value,
        price_eur=weight_price_eur,
    )
    weight_based = WeightBasedResult(
        shares=weight_shares,
        delta_eur=Money(amount=weight_shares * weight_price_eur, currency=Currency.EUR),
        current_weight_pct=current.weight_pct,
        target_weight_pct=target_weight_pct,
    )

    post_trade = _post_trade_preview(
        current_weight_pct=current.weight_pct,
        current_value_eur=position.live_value_eur.amount,
        portfolio_value_eur=portfolio_value,
        signed_trade_value_eur=signed_risk_shares * price_eur,
    )
    degraded_reason = (
        STALE_PRICE_REASON
        if position.staleness_reason is not None and "stale" in position.staleness_reason
        else None
    )
    return SizerView(
        current=current,
        risk_based=risk_based,
        weight_based=weight_based,
        post_trade=post_trade,
        degraded_reason=degraded_reason,
    )


def _find_position(
    positions: list[LivePosition],
    selected_ticker: str,
) -> LivePosition | None:
    by_ticker = {position.ticker: position for position in positions}
    if selected_ticker in by_ticker:
        return by_ticker[selected_ticker]
    return sorted(positions, key=lambda position: position.ticker)[0] if positions else None


def _current_card(
    position: LivePosition,
    summary: PortfolioSummary,
) -> CurrentPositionCard:
    value_eur = position.live_value_eur or _ZERO_EUR
    price_native = position.live_price_native or Money(
        amount=Decimal("0"),
        currency=_native_currency(position),
    )
    fx_rate = _fx_rate_for(position)
    last_price_eur = Money(
        amount=to_base_eur(price_native.amount, price_native.currency, fx_rate),
        currency=Currency.EUR,
    )
    return CurrentPositionCard(
        ticker=position.ticker,
        name=position.ticker,
        weight_pct=_weight_pct(value_eur.amount, summary.total_value_eur.amount),
        market_value_eur=value_eur,
        last_price_native=price_native,
        last_price_eur=last_price_eur,
        open_lot_count=len(position.position.open_lots),
        staleness=position.staleness_reason,
    )


def _degraded_empty_view(selected_ticker: str, reason: str) -> SizerView:
    current = CurrentPositionCard(
        ticker=selected_ticker,
        name=selected_ticker,
        weight_pct=Decimal("0"),
        market_value_eur=_ZERO_EUR,
        last_price_native=_ZERO_EUR,
        last_price_eur=_ZERO_EUR,
        open_lot_count=0,
        staleness=reason,
    )
    return _degraded_view(current, reason)


def _degraded_view(current: CurrentPositionCard, reason: str) -> SizerView:
    return SizerView(
        current=current,
        risk_based=None,
        weight_based=None,
        post_trade=None,
        degraded_reason=reason,
    )


def _post_trade_preview(
    *,
    current_weight_pct: Decimal,
    current_value_eur: Decimal,
    portfolio_value_eur: Decimal,
    signed_trade_value_eur: Decimal,
) -> PostTradeWeightPreview:
    new_position_value = max(Decimal("0"), current_value_eur + signed_trade_value_eur)
    new_portfolio_value = portfolio_value_eur + signed_trade_value_eur
    new_weight_pct = (
        _weight_pct(new_position_value, new_portfolio_value)
        if new_portfolio_value > 0
        else Decimal("0")
    )
    return PostTradeWeightPreview(
        current_weight_pct=current_weight_pct,
        new_weight_pct=new_weight_pct,
        bucket=_bucket_for_weight(new_weight_pct),
    )


def _bucket_for_weight(value: Decimal) -> Literal["green", "amber", "red"]:
    if value >= MAX_POSITION_WEIGHT_PCT:
        return "red"
    if value >= Decimal("25"):
        return "amber"
    return "green"


def _weight_pct(value_eur: Decimal, portfolio_value_eur: Decimal) -> Decimal:
    if portfolio_value_eur <= 0 or value_eur <= 0:
        return Decimal("0")
    return (value_eur / portfolio_value_eur * _HUNDRED).quantize(
        _PCT_QUANT,
        rounding=ROUND_HALF_UP,
    )


def _stop_price_native(
    price_native: Decimal,
    stop_pct: Decimal,
    direction: Literal["buy", "sell"],
) -> Decimal:
    multiplier = (
        Decimal("1") - stop_pct / _HUNDRED
        if direction == "buy"
        else Decimal("1") + stop_pct / _HUNDRED
    )
    return price_native * multiplier


def _native_currency(position: LivePosition) -> Currency:
    if position.live_price_native is not None:
        return position.live_price_native.currency
    if position.position.open_lots:
        return position.position.open_lots[0].cost_per_share_native.currency
    return Currency.EUR


def _fx_rate_for(position: LivePosition) -> Decimal:
    if _native_currency(position) == Currency.EUR:
        return Decimal("1")
    return position.current_fx_rate or Decimal("0")
