from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.domain.fifo import SellExceedsOpenSharesError, compute_positions, simulate_lot_consumption
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.positions import LivePosition
from app.domain.realised_gain import RealisedGain
from app.domain.tax.models import MarginalTaxImpact, TaxProfile
from app.ports.tax_profile_repo import YearlyTaxInputs
from app.services.tax_planning import compute_marginal_tax_for_realised_gains
from app.services.valuation import compute_portfolio_summary

_EUR = Currency.EUR


class SellSimulationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    shares: Decimal
    sell_price_native: Money
    sell_fx_rate_eur: Decimal
    sell_date: date


class LotConsumption(BaseModel):
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
    model_config = ConfigDict(frozen=True)

    open_shares_after: Decimal
    cost_basis_eur_after: Money
    unrealised_gain_eur_after: Money | None
    weight_pct_before: Decimal | None
    weight_pct_after: Decimal | None
    weight_change_pct: Decimal | None


class SellSimulation(BaseModel):
    model_config = ConfigDict(frozen=True)

    request: SellSimulationRequest
    is_valid: bool
    validation_error: str | None = None
    lot_consumption: tuple[LotConsumption, ...] = ()
    realised_gains: tuple[RealisedGain, ...] = ()
    total_realised_gain_eur: Money = Money(amount=Decimal("0"), currency=_EUR)
    marginal_tax: MarginalTaxImpact | None = None
    position_after: PositionAfterSnapshot | None = None


def simulate_sell(
    request: SellSimulationRequest,
    transactions: Sequence[Transaction],
    profile: TaxProfile,
    yearly_inputs: YearlyTaxInputs,
    live_positions: dict[str, LivePosition],
) -> SellSimulation:
    # Step 1: derive open_lots
    positions = compute_positions(transactions)
    position = positions.get(request.ticker)
    
    if position is None or position.open_shares == 0:
        return SellSimulation(
            request=request,
            is_valid=False,
            validation_error=f"No open position for {request.ticker}."
        )

    # Step 2: Build a hypothetical Transaction
    try:
        # TICKET-008c validator runs on instantiation and may raise
        hypothetical_sell = Transaction(
            id="simulated-sell",
            type=TransactionType.SELL,
            ticker=request.ticker,
            shares=request.shares,
            price_native=request.sell_price_native,
            fx_rate_eur=request.sell_fx_rate_eur,
            trade_date=request.sell_date,
        )
    except Exception as e:
        return SellSimulation(
            request=request,
            is_valid=False,
            validation_error=str(e),
        )

    # Step 3: try simulate_lot_consumption
    try:
        gains, remaining_lots = simulate_lot_consumption(
            position.open_lots, request.shares, hypothetical_sell
        )
    except SellExceedsOpenSharesError as e:
        return SellSimulation(
            request=request,
            is_valid=False,
            validation_error=str(e),
        )

    # Convert gains to lot_consumption
    lot_consumption_rows: list[LotConsumption] = []
    total_gain_amount = Decimal("0")
    sell_price_eur = request.sell_price_native.amount * request.sell_fx_rate_eur
    
    for i, gain in enumerate(gains, start=1):
        total_gain_amount += gain.realised_gain_eur.amount
        
        lot_cost_native = next(
            (lot.cost_per_share_native for lot in position.open_lots if lot.source_transaction_id == gain.buy_transaction_id),
            Money(amount=Decimal("0"), currency=request.sell_price_native.currency)
        )
        lot_fx = next(
            (lot.fx_rate_eur for lot in position.open_lots if lot.source_transaction_id == gain.buy_transaction_id),
            Decimal("1.0")
        )
        
        lot_consumption_rows.append(
            LotConsumption(
                lot_index=i,
                buy_transaction_id=gain.buy_transaction_id,
                buy_date=gain.buy_date,
                shares_consumed=gain.shares,
                cost_per_share_native=lot_cost_native,
                cost_per_share_eur=Money(
                    amount=lot_cost_native.amount * lot_fx,
                    currency=_EUR
                ),
                sell_price_eur=Money(amount=sell_price_eur, currency=_EUR),
                realised_gain_eur=gain.realised_gain_eur,
            )
        )

    # Step 4: compute marginal tax
    marginal_tax = compute_marginal_tax_for_realised_gains(
        current_transactions=transactions,
        proposed_sell=hypothetical_sell,
        profile=profile,
        carryforward_eur_aktien=yearly_inputs.carryforward_aktien_eur,
        carryforward_eur_general=yearly_inputs.carryforward_general_eur,
        additional_dividend_income_eur=yearly_inputs.additional_dividend_income_eur,
        additional_interest_income_eur=yearly_inputs.additional_interest_income_eur,
    )

    # Step 5: compute position_after
    open_shares_after = position.open_shares - request.shares
    cost_basis_eur_after_amount = sum((lot.cost_basis_eur.amount for lot in remaining_lots), Decimal("0"))
    
    live_pos = live_positions.get(request.ticker)
    unrealised_gain_eur_after = None
    if live_pos is not None and live_pos.live_price_native is not None:
        unrealised_gain_eur_after = Money(
            amount=(open_shares_after * live_pos.live_price_native.amount * live_pos.current_fx_rate) - cost_basis_eur_after_amount,
            currency=_EUR
        )
    
    weight_pct_before = None
    weight_pct_after = None
    weight_change_pct = None
    
    from datetime import datetime
    portfolio_summary = compute_portfolio_summary(
        live_positions,
        datetime.combine(request.sell_date, datetime.min.time())
    )
    
    if live_pos is not None and live_pos.live_value_eur is not None and portfolio_summary.total_value_eur is not None:
        total_value = portfolio_summary.total_value_eur.amount
        if total_value > 0:
            weight_pct_before = (live_pos.live_value_eur.amount / total_value) * 100
            
            # Value after
            value_after_amount = open_shares_after * live_pos.live_price_native.amount * live_pos.current_fx_rate
            total_value_after = total_value - (request.shares * request.sell_price_native.amount * request.sell_fx_rate_eur)
            if total_value_after > 0:
                weight_pct_after = (value_after_amount / total_value_after) * 100
                weight_change_pct = weight_pct_after - weight_pct_before

    position_after = PositionAfterSnapshot(
        open_shares_after=open_shares_after,
        cost_basis_eur_after=Money(amount=cost_basis_eur_after_amount, currency=_EUR),
        unrealised_gain_eur_after=unrealised_gain_eur_after,
        weight_pct_before=weight_pct_before,
        weight_pct_after=weight_pct_after,
        weight_change_pct=weight_change_pct,
    )

    return SellSimulation(
        request=request,
        is_valid=True,
        lot_consumption=tuple(lot_consumption_rows),
        realised_gains=tuple(gains),
        total_realised_gain_eur=Money(amount=total_gain_amount, currency=_EUR),
        marginal_tax=marginal_tax,
        position_after=position_after,
    )
