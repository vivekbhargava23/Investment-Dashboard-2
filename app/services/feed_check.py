from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal

from app.domain.feed_check import FeedCheck, evaluate_deviations
from app.domain.isin_map import IsinMapDocument
from app.domain.models import Transaction
from app.domain.money import Currency
from app.ports.fx_feed import FxRateUnavailableError, HistoricalFxProvider
from app.ports.price_feed import PriceProvider, PriceUnavailableError


def check_feeds(
    transactions: Sequence[Transaction],
    isin_doc: IsinMapDocument,
    price_provider: PriceProvider,
    fx_provider: HistoricalFxProvider,
    *,
    max_trades: int = 3,
) -> dict[str, FeedCheck]:
    """Compare recent Scalable trade prices with mapped historical feed closes."""
    if max_trades < 1:
        raise ValueError("max_trades must be at least 1")

    by_isin: dict[str, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        if tx.source == "scalable_csv" and tx.isin is not None:
            by_isin[tx.isin].append(tx)

    checks: dict[str, FeedCheck] = {}
    for isin in sorted(by_isin):
        mapping = isin_doc.entries.get(isin)
        ticker = (
            mapping.ticker
            if mapping is not None and mapping.status == "mapped"
            else None
        )
        if ticker is None:
            checks[isin] = evaluate_deviations(isin, None, [])
            continue

        recent = sorted(
            by_isin[isin], key=lambda tx: (tx.trade_date, tx.id)
        )[-max_trades:]
        pairs: list[tuple[Decimal, Decimal]] = []
        for tx in recent:
            try:
                close = price_provider.get_historical_close(ticker, tx.trade_date)
                close_eur = close.amount
                if close.currency != Currency.EUR:
                    rate = fx_provider.get_historical_rate(
                        close.currency, Currency.EUR, tx.trade_date
                    )
                    close_eur *= rate
            except (PriceUnavailableError, FxRateUnavailableError):
                continue
            pairs.append((tx.price_native.amount, close_eur))

        checks[isin] = evaluate_deviations(isin, ticker, pairs)

    return checks
