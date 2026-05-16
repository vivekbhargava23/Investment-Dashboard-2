#!/usr/bin/env python3
"""Backfill ISIN onto scalable_csv transactions from a Scalable Capital CSV export.

Idempotent: transactions whose ``isin`` is already set are never overwritten.
Safe by default: ``--dry-run`` is the default mode. Use ``--apply`` to write.

Run from the project root:

    python3 tools/backfill_isin_from_csv.py \\
        --portfolio data/portfolio.json \\
        --csv path/to/ScalableCapital-Broker-Transactions.csv \\
        [--dry-run | --apply]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Allow `python3 tools/backfill_isin_from_csv.py` from the project root
# to import app.* without an editable install.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.adapters.scalable_csv.parser import parse_csv  # noqa: E402


def _build_ref_to_isin(csv_path: Path) -> dict[str, str]:
    """Return {reference: isin} for every row in the CSV that has both fields."""
    rows = parse_csv(csv_path)
    result: dict[str, str] = {}
    for row in rows:
        if row.reference and row.isin:
            result[row.reference] = row.isin
    return result


def _plan(
    portfolio: dict[str, object],
    ref_to_isin: dict[str, str],
) -> dict[str, object]:
    """Compute backfill plan without touching the portfolio dict."""
    planned: list[dict[str, str]] = []
    already_set = 0
    no_ref = 0
    not_found: list[tuple[str, str]] = []

    for tx in portfolio.get("transactions", []):  # type: ignore[union-attr]
        if tx.get("source") != "scalable_csv":  # type: ignore[union-attr]
            continue
        isin = tx.get("isin")  # type: ignore[union-attr]
        csv_ref = tx.get("csv_reference")  # type: ignore[union-attr]
        tx_id: str = tx.get("id", "")  # type: ignore[union-attr]

        if isin is not None:
            already_set += 1
        elif csv_ref is None:
            no_ref += 1
        elif csv_ref not in ref_to_isin:
            not_found.append((tx_id, str(csv_ref)))
        else:
            planned.append(
                {
                    "tx_id": tx_id,
                    "ticker": str(tx.get("ticker", "")),  # type: ignore[union-attr]
                    "csv_reference": str(csv_ref),
                    "isin_to_set": ref_to_isin[str(csv_ref)],
                }
            )

    return {
        "planned": planned,
        "already_set": already_set,
        "no_ref": no_ref,
        "not_found": not_found,
    }


def _print_plan(plan: dict[str, object], portfolio_path: Path) -> None:
    planned: list[dict[str, str]] = plan["planned"]  # type: ignore[assignment]
    not_found: list[tuple[str, str]] = plan["not_found"]  # type: ignore[assignment]

    print(f"\nBackfill plan for {portfolio_path}:")
    print(f"  Planned changes:            {len(planned)}")
    print(f"  Already set (skipped):      {plan['already_set']}")
    print(f"  No csv_reference:           {plan['no_ref']}")
    print(f"  Reference not found in CSV: {len(not_found)}")

    if planned:
        print("\nFirst 5 planned changes:")
        for change in planned[:5]:
            print(f"  {change['tx_id']} ({change['ticker']}) → {change['isin_to_set']}")

    if not_found:
        print("\nFirst 5 references not found in CSV:")
        for tx_id, csv_ref in not_found[:5]:
            print(f"  tx {tx_id!r}  csv_reference={csv_ref!r}")


def _apply_plan(
    portfolio: dict[str, object],
    plan: dict[str, object],
) -> int:
    """Mutate portfolio in-place, setting isin on planned transactions. Returns change count."""
    planned: list[dict[str, str]] = plan["planned"]  # type: ignore[assignment]
    ref_to_set = {c["csv_reference"]: c["isin_to_set"] for c in planned}
    count = 0
    for tx in portfolio.get("transactions", []):  # type: ignore[union-attr]
        csv_ref = tx.get("csv_reference")  # type: ignore[union-attr]
        if csv_ref in ref_to_set and tx.get("isin") is None:  # type: ignore[union-attr]
            tx["isin"] = ref_to_set[str(csv_ref)]  # type: ignore[index]
            count += 1
    return count


def _atomic_write(path: Path, data: dict[str, object]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backfill_isin_from_csv",
        description=(
            "Backfill ISIN onto scalable_csv transactions whose isin is None, "
            "using the transaction's csv_reference to look up the ISIN from the "
            "original Scalable Capital CSV export. "
            "Defaults to --dry-run (safe). Pass --apply to write changes."
        ),
    )
    parser.add_argument(
        "--portfolio",
        required=True,
        type=Path,
        help="Path to portfolio.json (must be schema v3)",
    )
    parser.add_argument(
        "--csv",
        required=True,
        type=Path,
        dest="csv_path",
        help="Path to the Scalable Capital CSV export",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the backfill plan without modifying any files (default)",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write changes to portfolio.json (creates a timestamped backup first)",
    )
    args = parser.parse_args(argv)

    if not args.portfolio.exists():
        print(f"Error: portfolio file not found: {args.portfolio}", file=sys.stderr)
        return 1
    if not args.csv_path.exists():
        print(f"Error: CSV file not found: {args.csv_path}", file=sys.stderr)
        return 1

    with open(args.portfolio, encoding="utf-8") as f:
        portfolio: dict[str, object] = json.load(f)

    version = portfolio.get("version")
    if version != 3:
        print(
            f"Error: This script only operates on schema v3. "
            f"Found version {version}. Run the migration first.",
            file=sys.stderr,
        )
        return 1

    ref_to_isin = _build_ref_to_isin(args.csv_path)
    plan = _plan(portfolio, ref_to_isin)
    _print_plan(plan, args.portfolio)

    if not args.apply:
        print("\nDry-run mode — no files modified. Pass --apply to write changes.")
        return 0

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = args.portfolio.with_name(f"portfolio.json.backfill.bak.{ts}")
    shutil.copy2(args.portfolio, backup_path)
    print(f"\nBackup written: {backup_path}")

    _apply_plan(portfolio, plan)
    _atomic_write(args.portfolio, portfolio)

    with open(args.portfolio, encoding="utf-8") as f:
        written: dict[str, object] = json.load(f)
    csv_txs = [
        t
        for t in written.get("transactions", [])  # type: ignore[union-attr]
        if t.get("source") == "scalable_csv"  # type: ignore[union-attr]
    ]
    with_isin = sum(1 for t in csv_txs if t.get("isin") is not None)  # type: ignore[union-attr]
    print(f"Wrote {args.portfolio}")
    print(f"Backfill complete: {with_isin} of {len(csv_txs)} CSV transactions now have ISIN.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
