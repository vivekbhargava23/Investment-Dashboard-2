"""
One-shot migration: fix manually-entered transactions whose ticker↔currency
pairing pre-dates the ADR-005 / TICKET-008c validator.

Broker-sourced rows (source=scalable_csv, switch) are intentionally skipped —
they store EUR prices at face value and must not be rewritten (ADR-005 amendment,
TICKET-CSV-7).

Usage:
    python -m app.scripts.migrate_currency --input data/portfolio.json [options]

Options:
    --output PATH   Where to write the fixed JSON (default: same as --input)
    --dry-run       Print the planned changes; write nothing
    --force         Allow overwriting an existing output file (default: refuse)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.adapters.repo_json.json_repo import JsonTransactionRepository
from app.adapters.yfinance_price.adapter import YfinancePriceAdapter
from app.domain.tickers import UnsupportedTickerError, infer_currency_from_ticker


def _collect_offenders(data: dict[str, Any]) -> list[dict[str, Any]]:
    offenders: list[dict[str, Any]] = []
    for tx in data.get("transactions", []):
        # Broker rows carry their own settlement currency — skip them entirely.
        if tx.get("source", "manual") != "manual":
            continue
        ticker = tx.get("ticker", "")
        currency_str = (tx.get("price_native") or {}).get("currency", "")
        if not ticker or not currency_str:
            continue
        try:
            inferred = infer_currency_from_ticker(ticker)
            if inferred.value != currency_str:
                offenders.append(tx)
        except UnsupportedTickerError:
            offenders.append(tx)
    return offenders


def _migrate_row(
    tx: dict[str, Any],
    price_provider: YfinancePriceAdapter,
    interactive: bool = False,
) -> dict[str, Any]:
    """
    Rewrite a single transaction dict so its currency matches its ticker.

    Strategy: preserve the recorded EUR cost basis, fetch the historical
    native-currency close from yfinance, and back-compute the FX rate.

        new_fx = (total_eur_cost - fees_eur) / (new_price_native * shares)
        total_eur_cost = old_price_native * old_fx * shares + old_fees * old_fx
    """
    ticker = tx["ticker"]
    shares_str = tx.get("shares", "1")
    old_price = Decimal(str(tx["price_native"]["amount"]))
    old_fx = Decimal(str(tx.get("fx_rate_eur", "1")))
    trade_date = date.fromisoformat(tx["trade_date"])

    # Fees (in old native currency)
    fees_native = Decimal("0")
    fees_native_data = tx.get("fees_native")
    if fees_native_data and fees_native_data.get("amount"):
        fees_native = Decimal(str(fees_native_data["amount"]))

    try:
        shares = Decimal(str(shares_str))
    except InvalidOperation:
        shares = Decimal("1")

    # Total EUR cost from the old (possibly wrong) record
    total_eur_cost = (old_price * shares + fees_native) * old_fx

    # Fetch the correct historical native close
    try:
        hist_price = price_provider.get_historical_close(ticker, trade_date)
        new_price_native = hist_price.amount
        new_currency = hist_price.currency.value
    except Exception as exc:
        print(
            f"  WARNING: could not fetch historical price for {ticker} on {trade_date}: {exc}. "
            f"Skipping this row — it will remain as-is."
        )
        return tx

    # Back-compute FX
    net_eur = total_eur_cost - (fees_native * old_fx)
    if shares > 0 and new_price_native > 0:
        new_fx = net_eur / (new_price_native * shares)
    else:
        new_fx = old_fx

    recorded_eur = total_eur_cost

    # Interactive override for the specific legacy row
    if interactive:
        print(
            f"\n  Found legacy {ticker} row recorded as {tx['price_native']['currency']} "
            f"with price={old_price}, fx={old_fx}, shares={shares}, fees={fees_native}."
        )
        print(f"  Recorded EUR cost basis: €{recorded_eur:.2f}")
        print(f"  yfinance historical {new_currency} close on {trade_date}: {new_price_native}")
        print(f"  Inferred new fx_rate_eur: {new_fx:.6f}")
        override = input(
            "  Vivek: is this the right EUR cost basis, or enter an override amount? "
            "[enter to accept / type EUR amount to override]: "
        ).strip()
        if override:
            try:
                override_eur = Decimal(override)
                new_fx = (override_eur - fees_native * old_fx) / (new_price_native * shares)
                print(f"  Using override: €{override_eur:.2f} → fx_rate_eur={new_fx:.6f}")
            except (InvalidOperation, ZeroDivisionError) as e:
                print(f"  Invalid input ({e}), keeping computed value.")

    new_tx = dict(tx)
    new_tx["price_native"] = {
        "amount": str(new_price_native.quantize(Decimal("0.0001"))),
        "currency": new_currency,
    }
    new_tx["fx_rate_eur"] = str(new_fx.quantize(Decimal("0.000001")))
    if fees_native_data and fees_native_data.get("currency"):
        new_fees = dict(fees_native_data)
        new_fees["currency"] = new_currency
        new_tx["fees_native"] = new_fees

    return new_tx


def main(
    input_path: Path,
    output_path: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
    price_provider: YfinancePriceAdapter | None = None,
    interactive: bool | None = None,
) -> int:
    if output_path is None:
        output_path = input_path

    if not input_path.exists():
        print(f"Error: {input_path} does not exist.")
        return 1

    if output_path.exists() and not force and output_path != input_path:
        print(
            f"Refusing to overwrite {output_path}. "
            f"Use --force or choose a different --output."
        )
        return 1

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    offenders = _collect_offenders(data)

    if not offenders:
        print("No legacy currency mismatches found. Nothing to migrate.")
        return 0

    print(f"Found {len(offenders)} row(s) with ticker↔currency mismatches:")
    for o in offenders:
        print(
            f"  {o['ticker']} recorded as {o['price_native']['currency']} "
            f"(inferred: {infer_currency_from_ticker(o['ticker'])})"
        )

    if dry_run:
        print("\n--dry-run: no files written.")
        return 0

    if price_provider is None:
        price_provider = YfinancePriceAdapter()

    offender_ids = {o["id"] for o in offenders}

    # Use interactive mode by default when running from the CLI.
    # Allow callers (tests) to override to False.
    use_interactive = interactive if interactive is not None else sys.stdin.isatty()

    new_transactions = []
    for tx in data["transactions"]:
        if tx["id"] in offender_ids:
            new_tx = _migrate_row(tx, price_provider, interactive=use_interactive)
            new_transactions.append(new_tx)
        else:
            new_transactions.append(tx)

    new_data = dict(data)
    new_data["transactions"] = new_transactions

    # Validate the output round-trips cleanly before writing
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(new_data, tmp, indent=2)
        tmp_path = Path(tmp.name)

    try:
        validation_repo = JsonTransactionRepository(tmp_path)
        validation_repo.load_all()
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        print(f"Validation failed — migrated data does not load cleanly: {exc}")
        print("Aborting. Original file unchanged.")
        return 1
    finally:
        tmp_path.unlink(missing_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, indent=2)

    print(f"\nMigrated {len(offenders)} row(s). Written to {output_path}.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    sys.exit(main(args.input, args.output, args.dry_run, args.force))
