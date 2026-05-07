# ruff: noqa: E501
"""Pre-trade sell simulator service.

Read-only: simulate_sell computes the full impact of a hypothetical sell
(FIFO lot consumption, realised gain, marginal tax, position change) without
writing any transactions. The writer path remains Manage Portfolio.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.domain.fifo import SellExceedsOpenSharesError, compute_positions, simulate_lot_consumption
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.positions import LivePosition, OpenLot
from app.domain.realised_gain import RealisedGain
from app.domain.tax.models import MarginalTaxImpact, TaxProfile
from app.services.tax_planning import compute_marginal_tax_for_realised_gains

_EUR = Currency.EUR
_ZERO_EUR = Money.zero(_EUR)


class SellSimulationRequest(BaseModel):
    """Input for simulate_sell."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    shares: Decimal
    sell_price_native: Money
    sell_fx_rate_eur: Decimal
    sell_date: date


class LotConsumption(BaseModel):
    """One row of the FIFO lot-consumption table."""

    model_config = ConfigDict(frozen=True)

    lot_index: int
    buy_transaction_id: str
    buy_date: date
    shares_consumed: Decimal
    cost_per_share_native: Money
    cost_per_share_eur: Money
    sell_price_eur: Money
    realised_gain_eur: Money


class PositionAfterSnapshot(BaseModel):
    """Post-sell position snapshot."""

    model_config = ConfigDict(frozen=True)

    open_shares_after: Decimal
    cost_basis_eur_after: Money
    unrealised_gain_eur_after: Money | None
    weight_pct_before: Decimal | None
    weight_pct_after: Decimal | None
    weight_change_pct: Decimal | None


class SellSimulation(BaseModel):
    """Full output of simulate_sell."""

    model_config = ConfigDict(frozen=True)

    request: SellSimulationRequest
    is_valid: bool
    validation_error: str | None
    lot_consumption: tuple[LotConsumption, ...]
    realised_gains: tuple[RealisedGain, ...]
    total_realised_gain_eur: Money
    marginal_tax: MarginalTaxImpact | None
    position_after: PositionAfterSnapshot | None


def _invalid(request: SellSimulationRequest, message: str) -> SellSimulation:
    return SellSimulation(
        request=request,
        is_valid=False,
        validation_error=message,
        lot_consumption=(),
        realised_gains=(),
        total_realised_gain_eur=_ZERO_EUR,
        marginal_tax=None,
        position_after=None,
    )


def simulate_sell(
    request: SellSimulationRequest,
    transactions: Sequence[Transaction],
    profile: TaxProfile,
    live_positions: dict[str, LivePosition],
    *,
    carryforward_eur_aktien: Money = _ZERO_EUR,
    carryforward_eur_general: Money = _ZERO_EUR,
    additional_dividend_income_eur: Money = _ZERO_EUR,
    additional_interest_income_eur: Money = _ZERO_EUR,
) -> SellSimulation:
    """Simulate selling shares of a position without writing any transactions.

    Returns a SellSimulation with is_valid=False and a validation_error on input
    errors (no open position, over-sell, currency mismatch). Unexpected failures in
    the tax or position-after steps propagate to the caller.
    """
    ticker = request.ticker.strip().upper()

    # Step 1: derive open_lots for the ticker
    positions = compute_positions(list(transactions))
    if ticker not in positions:
        return _invalid(request, f"No open position for {ticker}.")

    position = positions[ticker]

    # Step 2: build the hypothetical sell transaction
    # Use a deterministic ID so simulate_sell is pure (same input → same output).
    stable_id = f"sim-{ticker}-{request.sell_date}-{request.shares}-{request.sell_price_native.amount}"
    try:
        hypothetical_sell = Transaction(
            id=stable_id,
            type=TransactionType.SELL,
            ticker=ticker,
            trade_date=request.sell_date,
            shares=request.shares,
            price_native=request.sell_price_native,
            fx_rate_eur=request.sell_fx_rate_eur,
            notes="[simulator]",
        )
    except Exception as exc:
        return _invalid(request, f"Invalid sell parameters: {exc}")

    # Step 3: FIFO lot consumption
    try:
        gains, remaining_lots = simulate_lot_consumption(
            position.open_lots, request.shares, hypothetical_sell
        )
    except SellExceedsOpenSharesError as exc:
        return _invalid(request, str(exc))

    sell_price_eur_per_share = Money(
        amount=(request.sell_price_native.amount * request.sell_fx_rate_eur).quantize(Decimal("0.0001")),
        currency=_EUR,
    )

    lot_rows: list[LotConsumption] = []
    for idx, (gain, lot) in enumerate(zip(gains, _match_lots_to_gains(gains, position.open_lots)), start=1):
        lot_rows.append(LotConsumption(
            lot_index=idx,
            buy_transaction_id=gain.buy_transaction_id,
            buy_date=gain.buy_date,
            shares_consumed=gain.shares,
            cost_per_share_native=lot.cost_per_share_native,
            cost_per_share_eur=Money(
                amount=(lot.cost_per_share_native.amount * lot.fx_rate_eur).quantize(Decimal("0.0001")),
                currency=_EUR,
            ),
            sell_price_eur=sell_price_eur_per_share,
            realised_gain_eur=gain.realised_gain_eur,
        ))

    total_gain_amount = sum((g.realised_gain_eur.amount for g in gains), Decimal("0"))
    total_realised_gain_eur = Money(amount=total_gain_amount, currency=_EUR)

    # Step 4: marginal tax
    marginal_tax = compute_marginal_tax_for_realised_gains(
        current_transactions=list(transactions),
        proposed_sell=hypothetical_sell,
        profile=profile,
        carryforward_eur_aktien=carryforward_eur_aktien,
        carryforward_eur_general=carryforward_eur_general,
        additional_dividend_income_eur=additional_dividend_income_eur,
        additional_interest_income_eur=additional_interest_income_eur,
    )

    # Step 5: position after snapshot
    remaining_cost_basis = sum(
        (lot.cost_basis_eur.amount for lot in remaining_lots), Decimal("0")
    )
    open_shares_after = position.open_shares - request.shares

    live_pos = live_positions.get(ticker)
    portfolio_total_before: Decimal | None = None
    portfolio_total_after: Decimal | None = None

    if live_pos is not None and not live_pos.is_stale and live_pos.live_value_eur is not None:
        sell_proceeds_eur = sell_price_eur_per_share.amount * request.shares
        unrealised_after = None
        if live_pos.live_price_native is not None:
            live_eur_per_share = live_pos.live_price_native.amount * (live_pos.current_fx_rate or Decimal("1"))
            unrealised_after = Money(
                amount=(live_eur_per_share * open_shares_after - remaining_cost_basis).quantize(Decimal("0.01")),
                currency=_EUR,
            )

        # Portfolio total from all live positions
        all_live_total = sum(
            (p.live_value_eur.amount for p in live_positions.values() if p.live_value_eur is not None),
            Decimal("0"),
        )
        if all_live_total > 0:
            portfolio_total_before = all_live_total
            portfolio_total_after = all_live_total - sell_proceeds_eur

        weight_before = (live_pos.live_value_eur.amount / portfolio_total_before * Decimal("100")).quantize(Decimal("0.01")) if portfolio_total_before and portfolio_total_before > 0 else None
        if portfolio_total_after and portfolio_total_after > 0 and live_pos.live_price_native is not None:
            value_after = live_pos.live_price_native.amount * (live_pos.current_fx_rate or Decimal("1")) * open_shares_after
            weight_after = (value_after / portfolio_total_after * Decimal("100")).quantize(Decimal("0.01"))
        else:
            weight_after = None

        weight_change = (weight_after - weight_before).quantize(Decimal("0.01")) if weight_before is not None and weight_after is not None else None

        position_after = PositionAfterSnapshot(
            open_shares_after=open_shares_after,
            cost_basis_eur_after=Money(amount=remaining_cost_basis, currency=_EUR),
            unrealised_gain_eur_after=unrealised_after,
            weight_pct_before=weight_before,
            weight_pct_after=weight_after,
            weight_change_pct=weight_change,
        )
    else:
        position_after = PositionAfterSnapshot(
            open_shares_after=open_shares_after,
            cost_basis_eur_after=Money(amount=remaining_cost_basis, currency=_EUR),
            unrealised_gain_eur_after=None,
            weight_pct_before=None,
            weight_pct_after=None,
            weight_change_pct=None,
        )

    return SellSimulation(
        request=request,
        is_valid=True,
        validation_error=None,
        lot_consumption=tuple(lot_rows),
        realised_gains=tuple(gains),
        total_realised_gain_eur=total_realised_gain_eur,
        marginal_tax=marginal_tax,
        position_after=position_after,
    )


def _match_lots_to_gains(
    gains: list[RealisedGain],
    open_lots: tuple[OpenLot, ...],
) -> list[OpenLot]:
    """Return the source OpenLot for each RealisedGain, matched by buy_transaction_id."""
    lots_by_id = {lot.source_transaction_id: lot for lot in open_lots}
    return [lots_by_id[g.buy_transaction_id] for g in gains]
