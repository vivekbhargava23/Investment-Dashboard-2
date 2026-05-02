"""
One-shot migration: rewrite data/portfolio.json from the lot-list schema
to the transaction-log schema.

For positions with pre-consumed buy lots (the old schema reduced lot shares
in-place when sells were recorded), the buy totals are insufficient for FIFO
replay. This script augments the oldest pre-sell buy lot by the total sell
share count so the replay produces the same open lots as the original JSON.

Idempotent: detects already-migrated files and exits 0 without changes.
Always writes a backup before overwriting.

Usage: python scripts/migrate_to_transactions.py
"""
from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path

from app.core.lot import replay_transactions
from app.core.transaction import Transaction


_RUNTIME = Path("data/portfolio.json")
_SEED = Path("app/data/seeds/portfolio.json")


def _is_already_migrated(raw: dict) -> bool:
    return any("transactions" in p for p in raw.get("positions", []))


def _ensure_fifo_feasible(transactions: list[dict]) -> None:
    """
    Augment the oldest pre-sell buy lot so FIFO replay won't fail.

    Old JSON stored remaining shares in buy lots (not original quantities).
    Sells therefore exceed available pre-sell buy shares. Adding the total
    sell count to the oldest pre-sell buy lot restores a replayable history
    that produces identical open lots.

    Mutates dicts in-place. No-op if there are no sell transactions.
    """
    sells = [t for t in transactions if t["trade_type"] == "sell"]
    if not sells:
        return

    total_sells = sum(t["shares"] for t in sells)

    # Sort by date to find the oldest pre-sell buy
    earliest_sell_date = min(t["trade_date"] for t in sells)
    by_date = sorted(transactions, key=lambda t: t["trade_date"])
    oldest_pre_sell_buy = next(
        (t for t in by_date
         if t["trade_type"] == "buy" and t["trade_date"] <= earliest_sell_date),
        None,
    )

    if oldest_pre_sell_buy is not None:
        oldest_pre_sell_buy["shares"] += total_sells
    else:
        # Degenerate: no pre-sell buy lot in JSON (all were fully consumed and removed).
        # Create a synthetic buy dated on the earliest sell using that sell's price.
        first_sell = min(sells, key=lambda t: t["trade_date"])
        synthetic = {
            "id": str(uuid.uuid4()),
            "ticker": first_sell["ticker"],
            "trade_date": first_sell["trade_date"],
            "trade_type": "buy",
            "shares": total_sells,
            "price": first_sell["price"],
            "fees": 0.0,
            "note": "migration-synthetic-buy",
        }
        transactions.append(synthetic)
        print(
            f"  WARNING: {first_sell['ticker']} had no pre-sell buy lots; "
            f"synthetic buy of {total_sells} shares inserted"
        )


def _migrate_position(p: dict) -> dict:
    """Convert a position dict from lots schema to transactions schema in place."""
    old_lots = p.pop("lots")
    transactions = []

    for lot in old_lots:
        t = {
            "id": lot["id"],
            "ticker": p["ticker"],
            "trade_date": lot["purchase_date"],
            "trade_type": lot.get("lot_type", "buy"),
            "shares": lot["shares"],
            "price": lot["purchase_price"],
            "fees": 0.0,
            "note": "",
        }
        transactions.append(t)

    _ensure_fifo_feasible(transactions)
    p["transactions"] = transactions
    return p


def _migrate(path: Path) -> bool:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if _is_already_migrated(raw):
        print(f"SKIP: {path} already on new schema")
        return False

    backup = path.with_suffix(path.suffix + ".pre-tx-migration")
    shutil.copyfile(path, backup)
    print(f"OK: backup written to {backup}")

    for p in raw["positions"]:
        _migrate_position(p)

    # Verify FIFO replay succeeds for every position
    for p in raw["positions"]:
        try:
            txns = [Transaction(**t) for t in p["transactions"]]
            replay_transactions(txns)
        except Exception as exc:
            print(f"FAIL: FIFO replay failed for {p['ticker']}: {exc}")
            shutil.copyfile(backup, path)
            print(f"REVERTED: {path} restored from backup")
            return False

    path.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"OK: {path} migrated to transaction-log schema")
    return True


def main() -> int:
    changed = False
    for path in [_RUNTIME, _SEED]:
        if path.exists():
            if _migrate(path):
                changed = True
    if not changed:
        print("Nothing to do.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
