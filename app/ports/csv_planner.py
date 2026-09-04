"""Port for the CSV import planner.

The planner itself is an adapter (it parses broker-specific rows), so the sync
service takes it as a parameter and passes the parsed rows straight through
without ever inspecting them.
"""
from __future__ import annotations

from typing import Any, Protocol

from app.domain.csv_import import ImportPlan
from app.domain.isin_map import IsinMapDocument
from app.domain.models import Transaction


class ImportPlanner(Protocol):
    def __call__(
        self,
        rows: Any,
        existing_txs: list[Transaction],
        isin_doc: IsinMapDocument,
    ) -> ImportPlan: ...
