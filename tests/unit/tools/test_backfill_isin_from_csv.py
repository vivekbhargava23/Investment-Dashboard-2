"""Tests for tools/backfill_isin_from_csv.py."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Import the module under test directly.
# tools/ is not a package, so we resolve the path and import via importlib.
_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent.parent / "tools" / "backfill_isin_from_csv.py"
)
_spec = importlib.util.spec_from_file_location("backfill_isin_from_csv", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["backfill_isin_from_csv"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

main = _mod.main  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CSV_HEADER = (
    "date;time;status;reference;description;assetType;type;isin;"
    "shares;price;amount;fee;tax;currency"
)


def _csv_row(reference: str, isin: str, tx_type: str = "Buy") -> str:
    sign = "-" if tx_type in ("Buy", "Savings plan") else ""
    return (
        f"2025-01-15;10:00:00;Executed;{reference};Desc;Security;"
        f"{tx_type};{isin};10;100,00;{sign}1.000,00;0,99;0,00;EUR"
    )


def _write_csv(path: Path, references: list[tuple[str, str]]) -> None:
    """Write a minimal Scalable CSV with the given (reference, isin) pairs."""
    lines = [_CSV_HEADER]
    for ref, isin in references:
        lines.append(_csv_row(ref, isin))
    path.write_text("\n".join(lines), encoding="utf-8")


def _scalable_tx(tx_id: str, ticker: str, csv_ref: str | None, isin: str | None) -> dict:
    return {
        "id": tx_id,
        "type": "buy",
        "ticker": ticker,
        "trade_date": "2025-01-15",
        "shares": "10",
        "price_native": {"amount": "100", "currency": "EUR"},
        "fees_native": None,
        "fx_rate_eur": "1",
        "notes": None,
        "csv_reference": csv_ref,
        "source": "scalable_csv",
        "isin": isin,
    }


def _manual_tx(tx_id: str, ticker: str) -> dict:
    return {
        "id": tx_id,
        "type": "buy",
        "ticker": ticker,
        "trade_date": "2025-01-15",
        "shares": "5",
        "price_native": {"amount": "200", "currency": "EUR"},
        "fees_native": None,
        "fx_rate_eur": "1",
        "notes": None,
        "csv_reference": None,
        "source": "manual",
        "isin": None,
    }


def _write_portfolio(path: Path, version: int, transactions: list[dict]) -> None:
    data = {"version": version, "transactions": transactions}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_portfolio(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Dry-run tests
# ---------------------------------------------------------------------------


def test_dry_run_plans_correctly(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    csv_path = tmp_path / "export.csv"

    # 5 CSV transactions: 3 unbackfilled, 2 already set
    _write_portfolio(portfolio, 3, [
        _scalable_tx("T1", "NVDA", "REF001", None),
        _scalable_tx("T2", "DELL", "REF002", None),
        _scalable_tx("T3", "MU",   "REF003", None),
        _scalable_tx("T4", "AAPL", "REF004", "US0378331005"),  # already set
        _scalable_tx("T5", "MSFT", "REF005", "US5949181045"),  # already set
    ])
    _write_csv(csv_path, [
        ("REF001", "US67066G1040"),
        ("REF002", "US24703L2025"),
        ("REF003", "US5951121038"),
        ("REF004", "US0378331005"),
        ("REF005", "US5949181045"),
    ])

    original_mtime = portfolio.stat().st_mtime
    rc = main(["--portfolio", str(portfolio), "--csv", str(csv_path), "--dry-run"])

    assert rc == 0
    # File must not be touched
    assert portfolio.stat().st_mtime == original_mtime
    # No backup created
    backups = list(tmp_path.glob("*.backfill.bak.*"))
    assert not backups


def test_dry_run_is_default_when_no_flag(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    csv_path = tmp_path / "export.csv"
    _write_portfolio(portfolio, 3, [_scalable_tx("T1", "NVDA", "REF001", None)])
    _write_csv(csv_path, [("REF001", "US67066G1040")])

    original_mtime = portfolio.stat().st_mtime
    rc = main(["--portfolio", str(portfolio), "--csv", str(csv_path)])

    assert rc == 0
    assert portfolio.stat().st_mtime == original_mtime


# ---------------------------------------------------------------------------
# Apply tests
# ---------------------------------------------------------------------------


def test_apply_backfills_correctly(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    csv_path = tmp_path / "export.csv"

    _write_portfolio(portfolio, 3, [
        _scalable_tx("T1", "NVDA", "REF001", None),
        _scalable_tx("T2", "DELL", "REF002", None),
        _scalable_tx("T3", "MU",   "REF003", None),
        _scalable_tx("T4", "AAPL", "REF004", "US0378331005"),
        _scalable_tx("T5", "MSFT", "REF005", "US5949181045"),
    ])
    _write_csv(csv_path, [
        ("REF001", "US67066G1040"),
        ("REF002", "US24703L2025"),
        ("REF003", "US5951121038"),
        ("REF004", "US0378331005"),
        ("REF005", "US5949181045"),
    ])

    rc = main(["--portfolio", str(portfolio), "--csv", str(csv_path), "--apply"])

    assert rc == 0

    # Backup must exist and contain original content (no isin on T1-T3)
    backups = list(tmp_path.glob("portfolio.json.backfill.bak.*"))
    assert len(backups) == 1
    bak = json.loads(backups[0].read_text())
    bak_by_id = {t["id"]: t for t in bak["transactions"]}
    assert bak_by_id["T1"]["isin"] is None
    assert bak_by_id["T4"]["isin"] == "US0378331005"

    # Portfolio must have all 5 ISINs set correctly
    data = _read_portfolio(portfolio)
    by_id = {t["id"]: t for t in data["transactions"]}
    assert by_id["T1"]["isin"] == "US67066G1040"
    assert by_id["T2"]["isin"] == "US24703L2025"
    assert by_id["T3"]["isin"] == "US5951121038"
    assert by_id["T4"]["isin"] == "US0378331005"  # unchanged
    assert by_id["T5"]["isin"] == "US5949181045"  # unchanged


def test_apply_idempotent(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    csv_path = tmp_path / "export.csv"

    _write_portfolio(portfolio, 3, [
        _scalable_tx("T1", "NVDA", "REF001", None),
    ])
    _write_csv(csv_path, [("REF001", "US67066G1040")])

    rc1 = main(["--portfolio", str(portfolio), "--csv", str(csv_path), "--apply"])
    assert rc1 == 0

    data_after_first = _read_portfolio(portfolio)

    rc2 = main(["--portfolio", str(portfolio), "--csv", str(csv_path), "--apply"])
    assert rc2 == 0

    data_after_second = _read_portfolio(portfolio)
    # Content identical after second run
    assert data_after_second == data_after_first


def test_already_set_isin_never_overwritten(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    csv_path = tmp_path / "export.csv"

    _write_portfolio(portfolio, 3, [
        _scalable_tx("T1", "NVDA", "REF001", "US0000000000"),  # wrong but set
    ])
    # CSV says the ISIN should be something else
    _write_csv(csv_path, [("REF001", "US1111111111")])

    rc = main(["--portfolio", str(portfolio), "--csv", str(csv_path), "--apply"])

    assert rc == 0
    data = _read_portfolio(portfolio)
    assert data["transactions"][0]["isin"] == "US0000000000"


# ---------------------------------------------------------------------------
# Skip / warning cases
# ---------------------------------------------------------------------------


def test_missing_csv_reference_skipped(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    csv_path = tmp_path / "export.csv"

    _write_portfolio(portfolio, 3, [
        _scalable_tx("T1", "NVDA", None, None),  # csv_reference is None
    ])
    _write_csv(csv_path, [("REF001", "US67066G1040")])

    rc = main(["--portfolio", str(portfolio), "--csv", str(csv_path), "--apply"])

    assert rc == 0
    data = _read_portfolio(portfolio)
    # isin stays None — no crash
    assert data["transactions"][0]["isin"] is None


def test_reference_not_in_csv_skipped(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    csv_path = tmp_path / "export.csv"

    _write_portfolio(portfolio, 3, [
        _scalable_tx("T1", "NVDA", "REFMISSING", None),  # ref not in CSV
    ])
    _write_csv(csv_path, [("REFATHER", "US67066G1040")])

    rc = main(["--portfolio", str(portfolio), "--csv", str(csv_path), "--apply"])

    assert rc == 0
    data = _read_portfolio(portfolio)
    assert data["transactions"][0]["isin"] is None


def test_manual_transactions_silently_skipped(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    csv_path = tmp_path / "export.csv"

    _write_portfolio(portfolio, 3, [
        _manual_tx("M1", "SAP.DE"),
    ])
    _write_csv(csv_path, [("REF001", "DE0007164600")])

    rc = main(["--portfolio", str(portfolio), "--csv", str(csv_path), "--apply"])

    assert rc == 0
    data = _read_portfolio(portfolio)
    assert data["transactions"][0]["isin"] is None  # unchanged


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_wrong_schema_version_errors(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    csv_path = tmp_path / "export.csv"

    _write_portfolio(portfolio, 2, [])  # v2, not v3
    _write_csv(csv_path, [])

    rc = main(["--portfolio", str(portfolio), "--csv", str(csv_path), "--dry-run"])

    assert rc == 1
    # File must not be mutated
    data = _read_portfolio(portfolio)
    assert data["version"] == 2


def test_missing_csv_file_errors(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    _write_portfolio(portfolio, 3, [])

    rc = main(["--portfolio", str(portfolio), "--csv", str(tmp_path / "nonexistent.csv")])

    assert rc == 1


def test_missing_portfolio_file_errors(tmp_path: Path) -> None:
    csv_path = tmp_path / "export.csv"
    _write_csv(csv_path, [])

    rc = main(["--portfolio", str(tmp_path / "nonexistent.json"), "--csv", str(csv_path)])

    assert rc == 1


def test_both_dry_run_and_apply_errors(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    csv_path = tmp_path / "export.csv"
    _write_portfolio(portfolio, 3, [])
    _write_csv(csv_path, [])

    with pytest.raises(SystemExit) as exc_info:
        main(["--portfolio", str(portfolio), "--csv", str(csv_path), "--dry-run", "--apply"])

    assert exc_info.value.code != 0
