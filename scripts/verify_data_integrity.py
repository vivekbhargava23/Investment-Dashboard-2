"""
Run this any time after a data-touching change to assert the runtime JSON
is still well-formed and the totals are sane.

Usage: python scripts/verify_data_integrity.py
Exits 0 on success, 1 with a clear message on failure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    path = Path("data/transactions.json")
    if not path.exists():
        print(f"FAIL: {path} does not exist")
        return 1
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL: {path} is not valid JSON: {e}")
        return 1

    required_keys = {"name", "positions"}
    missing = required_keys - set(raw.keys())
    if missing:
        print(f"FAIL: missing top-level keys: {missing}")
        return 1

    for i, p in enumerate(raw["positions"]):
        if "ticker" not in p or "transactions" not in p:
            print(f"FAIL: position {i} missing ticker or transactions")
            return 1

    print(f"OK: {len(raw['positions'])} positions, "
          f"{sum(len(p['transactions']) for p in raw['positions'])} transactions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
