#!/usr/bin/env python3
"""Migrate TICKER_KIND from classification.py into isin_map.json.

Run once after deploying TICKET-H1. Idempotent: re-running is a no-op.

Usage:
    python tools/migrate_classification_to_isin_map.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.adapters.isin_map.repo import JsonIsinMapRepository
from app.config import get_settings
from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.tax.classification import InstrumentKind

# Original TICKER_KIND dict from classification.py — preserved here for migration.
_LEGACY_TICKER_KIND: dict[str, InstrumentKind] = {
    "VUSA.DE": InstrumentKind.AKTIENFONDS,
    "NVDA": InstrumentKind.AKTIE,
    "RHM.DE": InstrumentKind.AKTIE,
    "MU": InstrumentKind.AKTIE,
    "ANET": InstrumentKind.AKTIE,
    "MRVL": InstrumentKind.AKTIE,
    "APD": InstrumentKind.AKTIE,
    "AVGO": InstrumentKind.AKTIE,
    "ETN": InstrumentKind.AKTIE,
    "ASX": InstrumentKind.AKTIE,
    "5631.T": InstrumentKind.AKTIE,
    "HY9H.F": InstrumentKind.AKTIE,
}


def run() -> None:
    settings = get_settings()
    repo = JsonIsinMapRepository(Path(settings.isin_map_json_path))
    doc = repo.load()

    updated_entries: dict[str, IsinMapping] = dict(doc.entries)
    migrated: list[str] = []
    already_set: list[str] = []
    not_in_map: list[str] = []

    for ticker, kind in _LEGACY_TICKER_KIND.items():
        upper = ticker.upper()
        found = False
        for isin, entry in updated_entries.items():
            if entry.ticker and entry.ticker.upper() == upper:
                found = True
                if entry.instrument_kind is not None:
                    already_set.append(ticker)
                else:
                    updated_entries[isin] = IsinMapping(
                        ticker=entry.ticker,
                        name=entry.name,
                        status=entry.status,
                        last_seen_in_csv=entry.last_seen_in_csv,
                        instrument_kind=kind,
                    )
                    migrated.append(ticker)
                break
        if not found:
            not_in_map.append(ticker)

    new_doc = IsinMapDocument(version=doc.version, entries=updated_entries)
    repo.save(new_doc)

    print("Migration complete.")
    if migrated:
        print(f"  Migrated ({len(migrated)}): {', '.join(migrated)}")
    if already_set:
        print(f"  Already had kind ({len(already_set)}): {', '.join(already_set)}")
    if not_in_map:
        print(
            f"  WARNING — {len(not_in_map)} ticker(s) from legacy TICKER_KIND not found in "
            f"isin_map.json (were they added directly without CSV import?):\n"
            f"  {', '.join(not_in_map)}\n"
            f"  Use the Mappings page to add and classify these ISINs manually."
        )


if __name__ == "__main__":
    run()
