from __future__ import annotations

from app.domain.csv_import import ImportPlan
from app.domain.reconcile import ReconcileRow, reconcile
from app.ports.repository import TransactionRepository


def reconcile_book(plan: ImportPlan, tx_repo: TransactionRepository) -> list[ReconcileRow]:
    """Load the current book and reconcile it against the CSV import plan."""
    transactions = tx_repo.load_all()
    return reconcile(plan.rows, transactions)
