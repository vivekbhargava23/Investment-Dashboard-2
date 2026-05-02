"""
One-shot: rebuild the tax_year block from all sell lots in the current year.

Run this once after Phase 2 to clean up historical drift.

Usage: python scripts/recompute_tax_year.py
"""
from __future__ import annotations

from datetime import date
import sys

from app.core.tax import (
    DEFAULT_SPARERPAUSCHBETRAG,
    recompute_tax_year_from_realised_gains_eur,
)
from app.data.repository import load_portfolio, load_tax_year, save_tax_year


def main() -> int:
    portfolio = load_portfolio()
    existing = load_tax_year()
    year = existing.year if existing else date.today().year
    sparerpauschbetrag = (
        existing.sparerpauschbetrag if existing else DEFAULT_SPARERPAUSCHBETRAG
    )
    loss_pot = existing.loss_pot_carried_in if existing else 0.0

    gains_eur: list[float] = []
    for pos in portfolio.positions:
        for lot in pos.lots:
            if lot.lot_type != "sell":
                continue
            if lot.purchase_date.year != year:
                continue
            if lot.realised_gain is None:
                print(f"WARN: sell lot {lot.id} has no realised_gain — skipping")
                continue
            gains_eur.append(lot.realised_gain)

    new = recompute_tax_year_from_realised_gains_eur(
        year=year,
        realised_gains_eur=gains_eur,
        sparerpauschbetrag=sparerpauschbetrag,
        loss_pot_carried_in=loss_pot,
    )
    save_tax_year(new)
    print(
        f"OK: tax_year for {year} rebuilt from {len(gains_eur)} sell lots — "
        f"gains €{new.realised_gains:.2f}, losses €{new.realised_losses:.2f}, "
        f"allowance_used €{new.allowance_used:.2f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
