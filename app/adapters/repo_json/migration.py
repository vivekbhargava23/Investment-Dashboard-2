"""One-shot migration: portfolio schema v1 → v2.

Adds csv_reference and source fields to all transactions.
Triggered automatically by JsonTransactionRepository when it reads a v1 file.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MigrationResult:
    csv_matched: int = 0
    switch_tagged: int = 0
    untagged_scalable: int = 0
    manual_tagged: int = 0

    def __str__(self) -> str:
        total = self.csv_matched + self.switch_tagged + self.untagged_scalable + self.manual_tagged
        return (
            f"Migrated {total} transactions: "
            f"{self.csv_matched} CSV-matched, "
            f"{self.switch_tagged} switch-tagged, "
            f"{self.untagged_scalable} untagged-Scalable, "
            f"{self.manual_tagged} manual."
        )


def migrate_v1_to_v2(
    portfolio_path: Path,
    csv_path: Path | None = None,
) -> MigrationResult:
    """Migrate portfolio.json from schema v1 to v2.

    - Adds csv_reference and source to every transaction.
    - Writes backup to portfolio.v1.pre-migration.json.bak before touching the file.
    - Is idempotent: skips silently if version is already 2.
    """
    with open(portfolio_path, encoding="utf-8") as f:
        data = json.load(f)

    if data.get("version") != 1:
        return MigrationResult()

    csv_references: set[str] = set()
    if csv_path is not None and csv_path.exists():
        _load_csv_references(csv_path, csv_references)

    backup_path = portfolio_path.with_name("portfolio.v1.pre-migration.json.bak")
    if not backup_path.exists():
        shutil.copy2(portfolio_path, backup_path)

    result = MigrationResult()
    for tx_data in data.get("transactions", []):
        tx_id: str = tx_data.get("id", "")

        if tx_id in csv_references:
            tx_data["csv_reference"] = tx_id
            tx_data["source"] = "scalable_csv"
            result.csv_matched += 1
        elif tx_id.startswith("SWITCH-101-"):
            parts = tx_id.split("-", 2)
            wwum_ref = parts[2] if len(parts) > 2 else tx_id
            tx_data["csv_reference"] = wwum_ref
            tx_data["source"] = "switch"
            result.switch_tagged += 1
        elif _looks_like_scalable_id(tx_id):
            tx_data["csv_reference"] = None
            tx_data["source"] = "scalable_csv"
            result.untagged_scalable += 1
        else:
            tx_data["csv_reference"] = None
            tx_data["source"] = "manual"
            result.manual_tagged += 1

    data["version"] = 2

    tmp_path = portfolio_path.with_suffix(portfolio_path.suffix + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, portfolio_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    return result


def migrate_v2_to_v3(portfolio_path: Path) -> dict[str, int]:
    """Migrate portfolio.json from schema v2 to v3.

    Adds an ``isin`` field to every transaction via reverse-lookup against
    ``isin_map.json`` in the same directory as the portfolio file.

    - scalable_csv transactions whose ticker appears in the ISIN map receive the
      mapped ISIN.
    - All other transactions (manual, switch, unknown, or scalable_csv with no
      matching ticker) receive ``isin = None``.

    Raises ``RuntimeError`` on ISIN-map collision (two ISINs → same ticker).
    Writes a backup to ``portfolio.json.v2.bak`` before touching the file.
    """
    with open(portfolio_path, encoding="utf-8") as f:
        data = json.load(f)

    if data.get("version") != 2:
        raise ValueError(
            f"migrate_v2_to_v3 requires a v2 portfolio, got v{data.get('version')}"
        )

    # Build reverse map from isin_map.json (same directory as portfolio.json).
    isin_map_path = portfolio_path.parent / "isin_map.json"
    ticker_to_isin: dict[str, str] = {}
    if isin_map_path.exists():
        with open(isin_map_path, encoding="utf-8") as f:
            isin_map_data = json.load(f)

        isin_by_ticker: dict[str, list[str]] = {}
        for isin, entry in isin_map_data.get("entries", {}).items():
            if entry.get("status") == "mapped" and entry.get("ticker"):
                isin_by_ticker.setdefault(entry["ticker"], []).append(isin)

        collisions = {t: isins for t, isins in isin_by_ticker.items() if len(isins) > 1}
        if collisions:
            details = "; ".join(
                f"{t!r} → {sorted(isins)}" for t, isins in sorted(collisions.items())
            )
            raise RuntimeError(
                f"ISIN map collision — cannot migrate: multiple ISINs share a ticker: {details}"
            )

        ticker_to_isin = {t: isins[0] for t, isins in isin_by_ticker.items()}

    # Write backup BEFORE any mutations (check succeeds above, so no collision).
    backup_path = portfolio_path.with_name("portfolio.json.v2.bak")
    shutil.copy2(portfolio_path, backup_path)

    migrated_count = 0
    manual_skipped_count = 0
    scalable_unbackfilled_count = 0

    for tx in data.get("transactions", []):
        source = tx.get("source", "manual")
        ticker = tx.get("ticker", "")

        if source == "scalable_csv" and ticker in ticker_to_isin:
            tx["isin"] = ticker_to_isin[ticker]
            migrated_count += 1
        else:
            tx["isin"] = None
            if source == "manual":
                manual_skipped_count += 1
            elif source == "scalable_csv":
                scalable_unbackfilled_count += 1

    data["version"] = 3

    tmp_path = portfolio_path.with_suffix(portfolio_path.suffix + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, portfolio_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    return {
        "migrated_count": migrated_count,
        "manual_skipped_count": manual_skipped_count,
        "scalable_unbackfilled_count": scalable_unbackfilled_count,
    }


def _looks_like_scalable_id(tx_id: str) -> bool:
    upper = tx_id.upper()
    return upper.startswith("SCAL") or upper.startswith("WWUM")


def _load_csv_references(csv_path: Path, out: set[str]) -> None:
    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=";")
            header_seen = False
            for row in reader:
                if not header_seen:
                    header_seen = True
                    continue
                if len(row) >= 4:
                    ref = row[3].strip()
                    if ref:
                        out.add(ref)
    except OSError:
        pass
