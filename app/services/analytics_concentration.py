from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from app.domain import analytics
from app.domain.analytics_views import ConcentrationRow, ConcentrationView
from app.domain.money import Currency, Money
from app.domain.positions import LivePosition, PortfolioSummary

MAX_POSITION_WEIGHT_PCT: Final[Decimal] = Decimal("35")
BAR_SCALE_MAX_PCT: Final[Decimal] = Decimal("40")

TOP_1_GREEN_LT_PCT: Final[Decimal] = Decimal("25")
TOP_1_RED_GTE_PCT: Final[Decimal] = Decimal("35")
TOP_3_GREEN_LT_PCT: Final[Decimal] = Decimal("50")
TOP_3_RED_GTE_PCT: Final[Decimal] = Decimal("70")
HHI_GREEN_LT: Final[Decimal] = Decimal("1500")
HHI_RED_GTE: Final[Decimal] = Decimal("2500")

_ZERO_EUR = Money(amount=Decimal("0"), currency=Currency.EUR)
_PCT_QUANT = Decimal("0.01")


def compute_concentration_view(
    positions: list[LivePosition],
    summary: PortfolioSummary,
) -> ConcentrationView:
    """Compute current portfolio concentration from live positions only.

    Stale positions remain visible in rows but contribute EUR 0 to weights and
    currency split. Ties sort alphabetically by ticker for deterministic output.
    """
    if not positions:
        return ConcentrationView(
            top_1_pct=Decimal("0"),
            top_3_pct=Decimal("0"),
            herfindahl=Decimal("0"),
            weights_by_ticker=[],
            currency_split=[],
            rows=[],
        )

    total_value = summary.total_value_eur.amount
    if total_value <= 0:
        total_value = Decimal("0")

    rows: list[ConcentrationRow] = []
    weight_pairs: list[tuple[str, Decimal]] = []
    currency_buckets: dict[Currency, Decimal] = {}

    for live_position in positions:
        ticker = live_position.ticker
        value_eur = _live_value_or_zero(live_position)
        weight_pct = Decimal("0")
        if total_value > 0 and not live_position.is_stale and value_eur.amount > 0:
            weight_pct = _quantize_pct(value_eur.amount / total_value * Decimal("100"))
            weight_pairs.append((ticker, weight_pct))
            currency = _native_currency(live_position)
            currency_buckets[currency] = (
                currency_buckets.get(currency, Decimal("0")) + value_eur.amount
            )

        rows.append(
            ConcentrationRow(
                ticker=ticker,
                name=ticker,
                weight_pct=weight_pct,
                value_eur=value_eur,
                currency=_native_currency(live_position),
                thesis_status=None,
                staleness_reason=live_position.staleness_reason,
            )
        )

    weights_by_ticker = sorted(weight_pairs, key=lambda item: (-item[1], item[0]))
    sorted_rows = sorted(rows, key=lambda row: (-row.weight_pct, row.ticker))
    currency_split = sorted(
        currency_buckets.items(),
        key=lambda item: (-item[1], item[0].value),
    )
    weights = [weight for _, weight in weights_by_ticker]

    return ConcentrationView(
        top_1_pct=weights[0] if weights else Decimal("0"),
        top_3_pct=sum(weights[:3], Decimal("0")),
        herfindahl=(
            analytics.herfindahl_index(weights).quantize(_PCT_QUANT, rounding=ROUND_HALF_UP)
            if weights
            else Decimal("0")
        ),
        weights_by_ticker=weights_by_ticker,
        currency_split=currency_split,
        rows=sorted_rows,
    )


def _live_value_or_zero(position: LivePosition) -> Money:
    if position.is_stale or position.live_value_eur is None:
        return _ZERO_EUR
    return position.live_value_eur


def _native_currency(position: LivePosition) -> Currency:
    if position.live_price_native is not None:
        return position.live_price_native.currency
    if position.position.open_lots:
        return position.position.open_lots[0].cost_per_share_native.currency
    return Currency.EUR


def _quantize_pct(value: Decimal) -> Decimal:
    return value.quantize(_PCT_QUANT, rounding=ROUND_HALF_UP)
