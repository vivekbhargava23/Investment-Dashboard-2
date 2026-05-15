#!/usr/bin/env python3
"""CLI: import a Scalable Capital CSV export into data/portfolio.json.

Usage:
    python tools/import_scalable_csv.py --input data/scalable_raw.csv

Optional:
    --isin-map  path to isin_map.json  (default: data/isin_map.json)
    --portfolio path to portfolio.json (default: data/portfolio.json)
    --dry-run   parse and report without writing any files
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.adapters.isin_map.repo import JsonIsinMapRepository
from app.adapters.repo_json.json_repo import JsonTransactionRepository
from app.adapters.scalable_csv.importer import ImportSummary, run_import
from app.adapters.scalable_csv.parser import ParseError, parse_csv


def _print_summary(summary: ImportSummary) -> None:
    filename = Path(summary.csv_path).name
    print(f"\nScalable CSV import — {filename}")
    print("=" * (25 + len(filename)))
    print(f"Rows in CSV:           {summary.total_rows}")

    if summary.status_filtered:
        detail = ", ".join(
            f"{k}: {v}" for k, v in sorted(summary.status_filtered_detail.items())
        )
        print(f"  Status-filtered:     {summary.status_filtered:>5}    ({detail})")

    if summary.out_of_scope:
        print(f"  Out of scope:        {summary.out_of_scope:>5}    "
              "(Deposit/Distribution/Interest/Taxes/Withdrawal/Corp-action — see TICKET-CSV-3)")

    print(f"  In scope:            {summary.in_scope:>5}")
    print(f"    Already in portfolio: {summary.already_existing:>4}")
    print(f"    New transactions:     {summary.new_transactions:>4}    (added to portfolio.json)")
    print(f"    Unmapped ISINs:       {summary.unmapped:>4}    "
          "(skipped; map them in isin_map.json and re-run)")

    if summary.invalid_mapping:
        print(f"    Invalid mappings:     {summary.invalid_mapping:>4}    "
              "(ticker→currency mismatch; use EUR-denominated ticker)")

    if summary.unmapped_isins:
        print("\nISINs requiring mapping:")
        for isin, name in summary.unmapped_isins:
            print(f"  ✗ {isin}  {name}")

    if summary.invalid_mapping_errors:
        print("\nInvalid mapping errors:")
        for isin, err in summary.invalid_mapping_errors:
            first_line = err.split("\n")[0]
            print(f"  ✗ {isin}  {first_line}")

    print(
        f"\nPortfolio now has {summary.portfolio_total} transactions "
        f"across {summary.unique_tickers} unique tickers."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import a Scalable Capital CSV export into data/portfolio.json"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/scalable_raw.csv"),
        help="Path to the Scalable Capital CSV export (default: data/scalable_raw.csv)",
    )
    parser.add_argument(
        "--isin-map",
        dest="isin_map",
        type=Path,
        default=Path("data/isin_map.json"),
        help="Path to the ISIN→ticker mapping file (default: data/isin_map.json)",
    )
    parser.add_argument(
        "--portfolio",
        type=Path,
        default=Path("data/portfolio.json"),
        help="Path to the portfolio JSON file (default: data/portfolio.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report without writing any files",
    )
    args = parser.parse_args(argv)

    # Parse CSV
    try:
        rows = parse_csv(args.input)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ParseError as exc:
        print(f"Parse error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"Dry run: parsed {len(rows)} rows from {args.input}")
        print("(no files written)")
        return 0

    tx_repo = JsonTransactionRepository(args.portfolio)
    isin_map_repo = JsonIsinMapRepository(args.isin_map)

    try:
        summary = run_import(
            rows=rows,
            csv_filename=str(args.input),
            tx_repo=tx_repo,
            isin_map_repo=isin_map_repo,
        )
    except ValueError as exc:
        print(f"Import error: {exc}", file=sys.stderr)
        return 1

    _print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
