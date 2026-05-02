"""
app/core/lot.py

OpenLot model and FIFO disposal engine.
German law mandates FIFO for lot accounting — never average cost.

OpenLot is a derived view of unconsumed BUY shares; it is produced by
replay_transactions(), never stored directly.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Literal, Sequence

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from app.core.transaction import Transaction


class OpenLot(BaseModel):
    """A single unconsumed buy: shares still held after FIFO replay."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ticker: str
    purchase_date: date
    purchase_price: float = Field(gt=0, description="Price per share at purchase in native currency")
    shares: float = Field(gt=0, description="Number of shares, fractional allowed")

    @field_validator("ticker", mode="before")
    @classmethod
    def normalise_ticker(cls, v: str) -> str:
        return v.strip().upper()

    @property
    def cost_basis(self) -> float:
        """Total cost of this lot (purchase_price × shares)."""
        return self.purchase_price * self.shares


class LotDisposal(BaseModel):
    """Shares consumed from one lot during a FIFO disposal."""

    lot_id: str
    purchase_date: date
    purchase_price: float
    shares_disposed: float
    cost_basis: float   # purchase_price × shares_disposed
    proceeds: float     # sell_price × shares_disposed
    gain: float         # proceeds − cost_basis


class FifoResult(BaseModel):
    """Outcome of a FIFO disposal simulation."""

    disposals: list[LotDisposal]
    remaining_lots: list[OpenLot]
    total_gain: float
    total_proceeds: float
    total_cost_basis: float

    @property
    def is_gain(self) -> bool:
        return self.total_gain >= 0

    @property
    def is_loss(self) -> bool:
        return self.total_gain < 0


class RealisedDisposal(BaseModel):
    """
    A historical FIFO disposal — what happened when a sell was processed.
    Used by the tax engine and the chart marker logic.
    """
    sell_transaction_id: str
    trade_date: date
    ticker: str
    disposals: list[LotDisposal]
    total_proceeds: float
    total_cost_basis: float
    total_gain: float


_FLOAT_EPSILON = 1e-9  # tolerance for floating-point share comparisons


def dispose_fifo(
    open_lots: Sequence[OpenLot],
    shares_to_sell: float,
    sell_price: float,
) -> FifoResult:
    """
    Simulate a FIFO disposal of shares across a list of open lots.

    Lots are consumed oldest-first (by purchase_date). Partial lot
    consumption is handled — the remainder stays as a lot entry.

    Args:
        open_lots:      All open lots for the position, any order.
        shares_to_sell: Positive number of shares to dispose of.
        sell_price:     Sale price per share in native currency.

    Returns:
        FifoResult with per-lot disposal detail and remaining lots.

    Raises:
        ValueError: If shares_to_sell or sell_price are not positive.
        ValueError: If shares_to_sell exceeds total shares held.
    """
    if shares_to_sell <= 0:
        raise ValueError(f"shares_to_sell must be positive, got {shares_to_sell}")
    if sell_price <= 0:
        raise ValueError(f"sell_price must be positive, got {sell_price}")

    sorted_lots = sorted(open_lots, key=lambda lot: lot.purchase_date)
    print(f"DEBUG_FIFO: Processing {len(sorted_lots)} lots for FIFO.")
    total_available = sum(lot.shares for lot in sorted_lots)

    if shares_to_sell > total_available + _FLOAT_EPSILON:
        raise ValueError(
            f"Cannot sell {shares_to_sell} shares — only {total_available:.4f} held"
        )

    disposals: list[LotDisposal] = []
    remaining_lots: list[OpenLot] = []
    still_to_sell = shares_to_sell

    for lot in sorted_lots:
        if still_to_sell <= _FLOAT_EPSILON:
            remaining_lots.append(lot)
            continue

        print(f"DEBUG: FIFO Matching - Selling {shares_to_sell} against lot from {lot.purchase_date}")
        if lot.shares <= still_to_sell + _FLOAT_EPSILON:
            # Whole lot consumed
            disposed = lot.shares
            cost = lot.purchase_price * disposed
            proceeds = sell_price * disposed
            # EMERGENCY MATH OVERRIDE: Literal gain calculation
            literal_gain = (sell_price - lot.purchase_price) * disposed
            disposals.append(
                LotDisposal(
                    lot_id=lot.id,
                    purchase_date=lot.purchase_date,
                    purchase_price=lot.purchase_price,
                    shares_disposed=disposed,
                    cost_basis=cost,
                    proceeds=proceeds,
                    gain=literal_gain,
                )
            )
            still_to_sell -= disposed
        else:
            # Partial lot consumed — remainder kept with original lot id
            disposed = still_to_sell
            cost = lot.purchase_price * disposed
            proceeds = sell_price * disposed
            # EMERGENCY MATH OVERRIDE: Literal gain calculation
            literal_gain = (sell_price - lot.purchase_price) * disposed
            disposals.append(
                LotDisposal(
                    lot_id=lot.id,
                    purchase_date=lot.purchase_date,
                    purchase_price=lot.purchase_price,
                    shares_disposed=disposed,
                    cost_basis=cost,
                    proceeds=proceeds,
                    gain=literal_gain,
                )
            )
            remaining_lots.append(
                OpenLot(
                    id=lot.id,
                    ticker=lot.ticker,
                    purchase_date=lot.purchase_date,
                    purchase_price=lot.purchase_price,
                    shares=lot.shares - disposed,
                )
            )
            still_to_sell = 0.0

    return FifoResult(
        disposals=disposals,
        remaining_lots=remaining_lots,
        total_gain=sum(d.gain for d in disposals),
        total_proceeds=sum(d.proceeds for d in disposals),
        total_cost_basis=sum(d.cost_basis for d in disposals),
    )


def replay_transactions(
    txns: list[Transaction],
) -> tuple[list[OpenLot], list[RealisedDisposal]]:
    """
    Replay an ordered transaction log to derive current open lots and the
    full history of FIFO disposals.

    Buys are added to the open-lot list. Sells consume the oldest open lots
    first (FIFO) and produce a RealisedDisposal record. Errors raise:
      - ValueError if a sell exceeds available shares at that point in time
      - ValueError if any transaction has an unknown type

    Args:
        txns: All transactions for one ticker, any order. Will be sorted
            by trade_date (stable) before replay.

    Returns:
        (open_lots, realised_disposals)
    """
    # Stable sort by trade_date — preserves user-entered ordering for same-day
    sorted_txns = sorted(txns, key=lambda t: t.trade_date)

    open_lots: list[OpenLot] = []
    realised: list[RealisedDisposal] = []

    for t in sorted_txns:
        if t.trade_type == "buy":
            open_lots.append(OpenLot(
                id=t.id,
                ticker=t.ticker,
                purchase_date=t.trade_date,
                purchase_price=t.price,
                shares=t.shares,
            ))
        elif t.trade_type == "sell":
            result = dispose_fifo(open_lots, t.shares, t.price)
            open_lots = result.remaining_lots
            gain = result.total_gain
            print(f"TERMINAL_DEBUG: Realized Gain Calculated: {gain} EUR")
            realised.append(RealisedDisposal(
                sell_transaction_id=t.id,
                trade_date=t.trade_date,
                ticker=t.ticker,
                disposals=result.disposals,
                total_proceeds=result.total_proceeds,
                total_cost_basis=result.total_cost_basis,
                total_gain=gain,
            ))
        else:
            raise ValueError(f"Unknown trade_type: {t.trade_type}")

    return open_lots, realised
