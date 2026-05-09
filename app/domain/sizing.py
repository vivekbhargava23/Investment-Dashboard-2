from __future__ import annotations

from decimal import Decimal

_HUNDRED = Decimal("100")


def risk_based_shares(
    *,
    portfolio_value_eur: Decimal,
    risk_pct: Decimal,
    stop_pct: Decimal,
    price_eur: Decimal,
) -> Decimal:
    """Return unrounded shares sized to risk ``risk_pct`` at ``stop_pct``.

    Formula:
    ``(portfolio_value_eur * risk_pct / 100) / (price_eur * stop_pct / 100)``.

    Raises ``ValueError`` when portfolio value or price is non-positive, or when
    ``risk_pct`` / ``stop_pct`` are outside ``(0, 100]``.
    """
    if portfolio_value_eur <= 0:
        raise ValueError("portfolio_value_eur must be positive")
    if price_eur <= 0:
        raise ValueError("price_eur must be positive")
    if risk_pct <= 0 or risk_pct > _HUNDRED:
        raise ValueError("risk_pct must be greater than 0 and at most 100")
    if stop_pct <= 0 or stop_pct > _HUNDRED:
        raise ValueError("stop_pct must be greater than 0 and at most 100")

    risk_eur = portfolio_value_eur * risk_pct / _HUNDRED
    loss_per_share_eur = price_eur * stop_pct / _HUNDRED
    return risk_eur / loss_per_share_eur


def weight_based_delta_shares(
    *,
    target_weight_pct: Decimal,
    current_weight_pct: Decimal,
    portfolio_value_eur: Decimal,
    price_eur: Decimal,
) -> Decimal:
    """Return signed unrounded shares needed to reach ``target_weight_pct``.

    Formula:
    ``(target_weight_pct - current_weight_pct) / 100 * portfolio_value_eur / price_eur``.

    Raises ``ValueError`` when portfolio value or price is non-positive, or when
    either input weight is negative. Weights above 100 are accepted; callers own
    any policy clamp.
    """
    if portfolio_value_eur <= 0:
        raise ValueError("portfolio_value_eur must be positive")
    if price_eur <= 0:
        raise ValueError("price_eur must be positive")
    if target_weight_pct < 0:
        raise ValueError("target_weight_pct must be non-negative")
    if current_weight_pct < 0:
        raise ValueError("current_weight_pct must be non-negative")

    target_delta_eur = (
        (target_weight_pct - current_weight_pct) / _HUNDRED * portfolio_value_eur
    )
    return target_delta_eur / price_eur
