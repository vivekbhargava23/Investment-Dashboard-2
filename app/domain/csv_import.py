"""Domain types for the CSV import workbench."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class RowStatus(StrEnum):
    ALREADY_IMPORTED = "already_imported"
    CONFLICT_WITH_MANUAL = "conflict_with_manual"
    NEW = "new"
    UNMAPPED_ISIN = "unmapped_isin"
    IGNORED_ISIN = "ignored_isin"
    OUT_OF_SCOPE_V1 = "out_of_scope_v1"
    INTERNAL_TRANSFER = "internal_transfer"
    CANCELLED_OR_EXPIRED = "cancelled_or_expired"
    PARSE_ERROR = "parse_error"
    VALIDATION_ERROR = "validation_error"


class PlannedAction(StrEnum):
    NOOP = "noop"
    INSERT = "insert"
    REPLACE = "replace"
    KEEP = "keep"
    SKIP = "skip"


class PlannedRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    row_number: int
    trade_date: date
    csv_type: str
    isin: str
    reference: str
    description: str
    shares: Decimal | None
    price: Decimal | None
    amount: Decimal | None
    fee: Decimal | None
    tax: Decimal | None
    status: RowStatus
    action: PlannedAction
    proposed_ticker: str | None = None
    conflict_tx_id: str | None = None
    error_message: str | None = None
    fx_rate_eur: Decimal | None = None


class ImportPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    rows: tuple[PlannedRow, ...]

    def count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.rows:
            counts[row.status] = counts.get(row.status, 0) + 1
        return counts

    def ready_to_import(self) -> list[PlannedRow]:
        return [r for r in self.rows if r.action in (PlannedAction.INSERT, PlannedAction.REPLACE)]
