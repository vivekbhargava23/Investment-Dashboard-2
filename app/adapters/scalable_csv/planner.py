"""Classify parsed CSV rows into planned import actions (no write I/O)."""
from __future__ import annotations

import hashlib
from decimal import Decimal

from app.adapters.scalable_csv.parser import ParsedCsvRow
from app.domain.csv_import import (
    ImportPlan,
    PlannedAction,
    PlannedRow,
    RowStatus,
)
from app.domain.isin_map import IsinMapDocument
from app.domain.models import Transaction
from app.domain.money import Currency
from app.domain.tickers import UnsupportedTickerError, infer_currency_from_ticker
from app.ports.fx_feed import FxProvider

_EXECUTED_STATUS = "Executed"
_IN_SCOPE_TYPES = frozenset({"Buy", "Sell", "Savings plan", "Security transfer"})


def _content_hash(tx: Transaction) -> str:
    key = (
        f"{tx.type}|{tx.ticker}|{tx.trade_date}|"
        f"{tx.shares:.6f}|{tx.price_native.amount:.4f}|{tx.price_native.currency}"
    )
    return hashlib.sha1(key.encode()).hexdigest()


def _row_content_hash(row: ParsedCsvRow, ticker: str, tx_type_str: str) -> str:
    if row.shares is None or row.price is None:
        return ""
    key = (
        f"{tx_type_str}|{ticker}|{row.date}|"
        f"{row.shares:.6f}|{row.price:.4f}|EUR"
    )
    return hashlib.sha1(key.encode()).hexdigest()


def plan_import(
    rows: list[ParsedCsvRow],
    existing_txs: list[Transaction],
    isin_doc: IsinMapDocument,
    *,
    fx_provider: FxProvider | None = None,
) -> ImportPlan:
    """Classify every CSV row into a planned action without writing anything.

    When fx_provider is supplied, non-EUR tickers are resolved via FX lookup:
    - Successful lookup → status NEW with fx_rate_eur set on the row.
    - Failed lookup → status FX_UNAVAILABLE (user may supply rate manually).
    When fx_provider is None, non-EUR tickers remain NEEDS_CURRENCY_SUPPORT.
    """
    existing_by_ref: dict[str, Transaction] = {
        tx.csv_reference: tx
        for tx in existing_txs
        if tx.csv_reference is not None
    }
    existing_by_content: dict[str, Transaction] = {
        _content_hash(tx): tx for tx in existing_txs
    }
    # Legacy: old importer stored reference directly as tx.id for scalable_csv rows
    existing_scalable_ids: set[str] = {
        tx.id for tx in existing_txs if tx.source == "scalable_csv"
    }

    planned: list[PlannedRow] = []

    for row in rows:
        if row.status != _EXECUTED_STATUS:
            planned.append(_make(row, RowStatus.CANCELLED_OR_EXPIRED, PlannedAction.SKIP))
            continue

        if row.type not in _IN_SCOPE_TYPES:
            planned.append(_make(row, RowStatus.OUT_OF_SCOPE_V1, PlannedAction.SKIP))
            continue

        if row.type == "Security transfer" and row.shares is not None and row.shares < 0:
            planned.append(_make(row, RowStatus.OUTGOING_TRANSFER, PlannedAction.SKIP))
            continue

        if row.reference in existing_by_ref or row.reference in existing_scalable_ids:
            planned.append(_make(row, RowStatus.ALREADY_IMPORTED, PlannedAction.NOOP))
            continue

        mapping = isin_doc.entries.get(row.isin)
        if mapping is None or mapping.status == "unmapped":
            planned.append(_make(row, RowStatus.UNMAPPED_ISIN, PlannedAction.SKIP))
            continue

        assert mapping.ticker is not None
        try:
            native_currency = infer_currency_from_ticker(mapping.ticker)
        except UnsupportedTickerError:
            # Currency not in our enum — cannot compute FX rate
            planned.append(_make(
                row, RowStatus.NEEDS_CURRENCY_SUPPORT, PlannedAction.SKIP, ticker=mapping.ticker
            ))
            continue

        if native_currency != Currency.EUR:
            if fx_provider is None:
                planned.append(_make(
                    row, RowStatus.NEEDS_CURRENCY_SUPPORT, PlannedAction.SKIP, ticker=mapping.ticker
                ))
                continue
            fx_rate_eur = _lookup_fx(fx_provider, native_currency, row.date)
            if fx_rate_eur is None:
                planned.append(_make(
                    row, RowStatus.FX_UNAVAILABLE, PlannedAction.SKIP, ticker=mapping.ticker
                ))
                continue
            planned.append(_make(
                row, RowStatus.NEW, PlannedAction.INSERT,
                ticker=mapping.ticker, fx_rate_eur=fx_rate_eur,
            ))
            continue

        tx_type_str = (
            "buy" if row.type in ("Buy", "Savings plan", "Security transfer") else "sell"
        )
        row_hash = _row_content_hash(row, mapping.ticker, tx_type_str)

        if row_hash and row_hash in existing_by_content:
            existing_tx = existing_by_content[row_hash]
            if existing_tx.source == "scalable_csv":
                planned.append(_make(
                    row, RowStatus.ALREADY_IMPORTED, PlannedAction.NOOP, ticker=mapping.ticker
                ))
            else:
                planned.append(_make(
                    row,
                    RowStatus.CONFLICT_WITH_MANUAL,
                    PlannedAction.REPLACE,
                    ticker=mapping.ticker,
                    conflict_tx_id=existing_tx.id,
                ))
            continue

        planned.append(_make(row, RowStatus.NEW, PlannedAction.INSERT, ticker=mapping.ticker))

    return ImportPlan(rows=tuple(planned))


def _lookup_fx(fx_provider: FxProvider, native_ccy: Currency, on_date: object) -> Decimal | None:
    """Return fx_rate_eur (1 native = X EUR) or None on any error."""
    try:
        from datetime import date as date_type
        assert isinstance(on_date, date_type)
        return fx_provider.get_historical_rate(native_ccy, Currency.EUR, on_date)
    except Exception:
        return None


def _make(
    row: ParsedCsvRow,
    status: RowStatus,
    action: PlannedAction,
    *,
    ticker: str | None = None,
    conflict_tx_id: str | None = None,
    error_message: str | None = None,
    fx_rate_eur: Decimal | None = None,
) -> PlannedRow:
    return PlannedRow(
        row_number=row.row_number,
        trade_date=row.date,
        csv_type=row.type,
        isin=row.isin,
        reference=row.reference,
        description=row.description,
        shares=row.shares,
        price=row.price,
        amount=row.amount,
        fee=row.fee,
        tax=row.tax,
        status=status,
        action=action,
        proposed_ticker=ticker,
        conflict_tx_id=conflict_tx_id,
        error_message=error_message,
        fx_rate_eur=fx_rate_eur,
    )
