"""Standalone script: migrate portfolio.json from schema v1 to v2.

Usage:
    python -m app.scripts.migrate_portfolio_v1_to_v2
    python -m app.scripts.migrate_portfolio_v1_to_v2 --portfolio data/portfolio.json
    python -m app.scripts.migrate_portfolio_v1_to_v2 \
        --portfolio data/portfolio.json --csv data/scalable_raw.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate portfolio.json v1 → v2")
    parser.add_argument(
        "--portfolio",
        type=Path,
        default=Path("data/portfolio.json"),
        help="Path to portfolio.json (default: data/portfolio.json)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Optional path to scalable_raw.csv to improve reference matching",
    )
    args = parser.parse_args()

    if not args.portfolio.exists():
        print(f"Error: {args.portfolio} not found.", file=sys.stderr)
        return 1

    from app.adapters.repo_json.migration import migrate_v1_to_v2

    result = migrate_v1_to_v2(args.portfolio, args.csv)
    print(str(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
