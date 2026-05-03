import argparse
import csv
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.adapters.repo_json import JsonTransactionRepository
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money


def main(input_path: Path, output_path: Path, force: bool = False) -> int:
    if output_path.exists() and not force:
        print(f"Refusing to overwrite {output_path}. Use --force or pick a different --output.")
        return 1

    try:
        with open(input_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        print(f"Error: Input file {input_path} not found.")
        return 1

    transactions = []
    skipped = 0

    for row_num, row in enumerate(rows, start=2):  # 1-indexed, +1 for header
        try:
            tx = Transaction(
                id=str(uuid4()),
                ticker=row["ticker"],
                type=TransactionType(row["type"]),
                trade_date=date.fromisoformat(row["trade_date"]),
                shares=Decimal(row["shares"]),
                price_native=Money(
                    amount=Decimal(row["price_native"]), 
                    currency=Currency(row["currency"])
                ),
                fx_rate_eur=Decimal(row["fx_rate_eur"]),
                notes=row.get("notes")
            )
            transactions.append(tx)
        except (ValidationError, ValueError, KeyError) as e:
            print(f"Row {row_num} invalid: {e}. Skipping.")
            skipped += 1
            
    output_path.parent.mkdir(parents=True, exist_ok=True)
    repo = JsonTransactionRepository(output_path)
    repo.save_all(transactions)
    
    print(f"{len(transactions)} transactions imported, {skipped} rows skipped.")
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the portfolio from a CSV file.")
    parser.add_argument("--input", type=Path, default=Path("docs/reference/seed_portfolio.csv"),
                        help="Path to the input CSV file")
    parser.add_argument("--output", type=Path, default=Path("data/portfolio.json"),
                        help="Path to the output JSON file")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite the output file if it exists")
    
    args = parser.parse_args()
    sys.exit(main(args.input, args.output, args.force))
