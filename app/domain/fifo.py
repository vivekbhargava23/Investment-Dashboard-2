from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from decimal import Decimal

from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.positions import OpenLot, Position
from app.domain.realised_gain import RealisedGain


class SellExceedsOpenSharesError(Exception):
    """Raised when a sell transaction attempts to consume more shares than are currently held."""

    pass


def compute_positions(transactions: Sequence[Transaction]) -> dict[str, Position]:
    """
    Computes current open positions and YTD realised gains for a sequence of transactions.
    """
    sorted_txs = _sort_transactions(transactions)
    ticker_queues: dict[str, deque[OpenLot]] = {}
    ticker_realised_gains: dict[str, list[RealisedGain]] = {}

    # Get the latest year for YTD calculation
    latest_year = 0
    if sorted_txs:
        latest_year = max(tx.trade_date.year for tx in sorted_txs)

    for tx in sorted_txs:
        if tx.ticker not in ticker_queues:
            ticker_queues[tx.ticker] = deque()
            ticker_realised_gains[tx.ticker] = []

        if tx.type == TransactionType.BUY:
            ticker_queues[tx.ticker].append(
                OpenLot(
                    source_transaction_id=tx.id,
                    ticker=tx.ticker,
                    trade_date=tx.trade_date,
                    remaining_shares=tx.shares,
                    cost_per_share_native=tx.price_native,
                    fx_rate_eur=tx.fx_rate_eur,
                )
            )
        elif tx.type == TransactionType.SELL:
            gains, remaining_lots = simulate_lot_consumption(
                tuple(ticker_queues[tx.ticker]), tx.shares, tx
            )
            ticker_queues[tx.ticker] = deque(remaining_lots)
            ticker_realised_gains[tx.ticker].extend(gains)

    # Convert queues to Position objects
    positions: dict[str, Position] = {}
    for ticker, queue in ticker_queues.items():
        open_lots = tuple(queue)
        open_shares = sum((lot.remaining_shares for lot in open_lots), Decimal("0"))

        if open_shares == 0:
            continue

        cost_basis_eur_amount = sum((lot.cost_basis_eur.amount for lot in open_lots), Decimal("0"))
        
        # Calculate YTD realised gains relative to the data provided
        realised_gain_ytd_amount = sum(
            (
                gain.realised_gain_eur.amount
                for gain in ticker_realised_gains[ticker]
                if gain.sell_date.year == latest_year
            ),
            Decimal("0"),
        )

        positions[ticker] = Position(
            ticker=ticker,
            open_shares=open_shares,
            open_lots=open_lots,
            realised_gain_eur_ytd=Money(amount=realised_gain_ytd_amount, currency=Currency.EUR),
            cost_basis_eur=Money(amount=cost_basis_eur_amount, currency=Currency.EUR),
        )

    return positions


def compute_realised_gains(transactions: Sequence[Transaction]) -> list[RealisedGain]:
    """
    Computes all realised gains for a sequence of transactions, returned in chronological order.
    """
    sorted_txs = _sort_transactions(transactions)
    ticker_queues: dict[str, deque[OpenLot]] = {}
    all_gains: list[RealisedGain] = []

    for tx in sorted_txs:
        if tx.ticker not in ticker_queues:
            ticker_queues[tx.ticker] = deque()

        if tx.type == TransactionType.BUY:
            ticker_queues[tx.ticker].append(
                OpenLot(
                    source_transaction_id=tx.id,
                    ticker=tx.ticker,
                    trade_date=tx.trade_date,
                    remaining_shares=tx.shares,
                    cost_per_share_native=tx.price_native,
                    fx_rate_eur=tx.fx_rate_eur,
                )
            )
        elif tx.type == TransactionType.SELL:
            gains, remaining_lots = simulate_lot_consumption(
                tuple(ticker_queues[tx.ticker]), tx.shares, tx
            )
            ticker_queues[tx.ticker] = deque(remaining_lots)
            all_gains.extend(gains)

    # The processing already produces gains in chronological order because we process
    # sorted transactions and _consume_from_lots maintains that order.
    return all_gains


def _sort_transactions(transactions: Sequence[Transaction]) -> list[Transaction]:
    """
    Sorts transactions by trade_date, then type (BUY before SELL), then ID for determinism.
    """
    return sorted(
        transactions,
        key=lambda tx: (
            tx.trade_date,
            0 if tx.type == TransactionType.BUY else 1,
            tx.id,
        ),
    )


def simulate_lot_consumption(
    open_lots: tuple[OpenLot, ...], shares_to_sell: Decimal, sell_tx: Transaction
) -> tuple[list[RealisedGain], tuple[OpenLot, ...]]:
    """
    Consumes shares from the given lots using FIFO, returning the realised gains
    and the remaining open lots without modifying the inputs.
    """
    open_shares = sum((lot.remaining_shares for lot in open_lots), Decimal("0"))
    if shares_to_sell > open_shares:
        raise SellExceedsOpenSharesError(
            f"Sell of {shares_to_sell} {sell_tx.ticker} on {sell_tx.trade_date} "
            f"exceeds open position of {open_shares} shares (transaction {sell_tx.id})"
        )

    gains: list[RealisedGain] = []
    remaining_to_sell = shares_to_sell
    remaining_lots: list[OpenLot] = []

    for lot in open_lots:
        if remaining_to_sell <= 0:
            remaining_lots.append(lot)
            continue

        shares_from_this_lot = min(lot.remaining_shares, remaining_to_sell)
        
        proceeds_eur_amount = (
            shares_from_this_lot * sell_tx.price_native.amount * sell_tx.fx_rate_eur
        )
        cost_basis_eur_amount = (
            shares_from_this_lot * lot.cost_per_share_native.amount * lot.fx_rate_eur
        )
        
        gain = RealisedGain(
            sell_transaction_id=sell_tx.id,
            buy_transaction_id=lot.source_transaction_id,
            ticker=sell_tx.ticker,
            shares=shares_from_this_lot,
            sell_date=sell_tx.trade_date,
            buy_date=lot.trade_date,
            proceeds_eur=Money(amount=proceeds_eur_amount, currency=Currency.EUR),
            cost_basis_eur=Money(amount=cost_basis_eur_amount, currency=Currency.EUR),
            realised_gain_eur=Money(
                amount=proceeds_eur_amount - cost_basis_eur_amount, currency=Currency.EUR
            ),
            holding_period_days=(sell_tx.trade_date - lot.trade_date).days,
        )
        gains.append(gain)
        
        remaining_to_sell -= shares_from_this_lot
        
        if lot.remaining_shares > shares_from_this_lot:
            updated_lot = lot.model_copy(
                update={"remaining_shares": lot.remaining_shares - shares_from_this_lot}
            )
            remaining_lots.append(updated_lot)

    return gains, tuple(remaining_lots)
