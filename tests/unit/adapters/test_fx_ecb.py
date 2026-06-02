"""Unit tests for EcbFxAdapter — CSV parsing, cross-rate, weekend walk-back, cache."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.fx_ecb.adapter import EcbFxAdapter, parse_ecb_zip
from app.domain.money import Currency
from app.ports.fx_feed import FxRateUnavailableError

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_ecb_zip(rows: list[dict[str, str]]) -> bytes:
    """Build a minimal ECB-format zip for testing."""
    headers = ["Date", "USD", "JPY"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("eurofxref-hist.csv", buf.getvalue())
    return zip_buf.getvalue()


# ECB reference data used across tests:
# 2026-05-28 (Wednesday) and 2026-05-29 (Thursday) are business days.
# 2026-05-30 (Friday) is a business day too.
# 2026-05-31 (Saturday) and 2026-06-01 (Sunday) have no ECB data.
_ROWS = [
    {"Date": "2026-05-30", "USD": "1.1300", "JPY": "162.00"},  # Friday
    {"Date": "2026-05-29", "USD": "1.1280", "JPY": "161.50"},  # Thursday
    {"Date": "2026-05-28", "USD": "1.1250", "JPY": "161.00"},  # Wednesday
]
_ZIP = _make_ecb_zip(_ROWS)


def _make_adapter(cache_dir: Path) -> EcbFxAdapter:
    return EcbFxAdapter(cache_path=cache_dir / "ecb.json")


# ---------------------------------------------------------------------------
# 1. parse_ecb_zip — CSV parsing
# ---------------------------------------------------------------------------

def test_parse_ecb_zip_returns_correct_structure() -> None:
    data = parse_ecb_zip(_ZIP)
    assert set(data.keys()) == {"USD", "JPY"}
    assert data["USD"]["2026-05-30"] == "1.1300"
    assert data["JPY"]["2026-05-30"] == "162.00"


def test_parse_ecb_zip_skips_na_values() -> None:
    rows = [{"Date": "2026-05-30", "USD": "1.1300", "JPY": "N/A"}]
    data = parse_ecb_zip(_make_ecb_zip(rows))
    assert "JPY" not in data or "2026-05-30" not in data.get("JPY", {})


def test_parse_ecb_zip_skips_empty_values() -> None:
    rows = [{"Date": "2026-05-30", "USD": "", "JPY": "162.00"}]
    data = parse_ecb_zip(_make_ecb_zip(rows))
    assert "USD" not in data or "2026-05-30" not in data.get("USD", {})


# ---------------------------------------------------------------------------
# 2. Cold cache — fetches and writes disk
# ---------------------------------------------------------------------------

def test_cold_cache_populates_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _make_adapter(tmp_path)
    monkeypatch.setattr("app.adapters.fx_ecb.adapter._fetch_ecb_zip", lambda: _ZIP)

    rate = adapter.get_historical_rate(Currency.EUR, Currency.USD, date(2026, 5, 30))

    assert rate == Decimal("1.130000")
    assert (tmp_path / "ecb.json").exists()
    disk = json.loads((tmp_path / "ecb.json").read_text())
    assert disk["USD"]["2026-05-30"] == "1.1300"


# ---------------------------------------------------------------------------
# 3. Warm cache — no network call
# ---------------------------------------------------------------------------

def test_warm_cache_no_network_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Pre-populate disk cache
    cache_data = {"USD": {"2026-05-30": "1.1300"}, "JPY": {"2026-05-30": "162.00"}}
    (tmp_path / "ecb.json").write_text(json.dumps(cache_data))

    call_count = {"n": 0}
    def _mock_fetch() -> bytes:
        call_count["n"] += 1
        return b""

    adapter = _make_adapter(tmp_path)
    monkeypatch.setattr("app.adapters.fx_ecb.adapter._fetch_ecb_zip", _mock_fetch)

    rate = adapter.get_historical_rate(Currency.EUR, Currency.USD, date(2026, 5, 30))
    assert rate == Decimal("1.130000")
    assert call_count["n"] == 0


# ---------------------------------------------------------------------------
# 4. Memory cache — second call does not re-read disk
# ---------------------------------------------------------------------------

def test_memory_cache_serves_second_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _make_adapter(tmp_path)
    monkeypatch.setattr("app.adapters.fx_ecb.adapter._fetch_ecb_zip", lambda: _ZIP)

    r1 = adapter.get_historical_rate(Currency.EUR, Currency.USD, date(2026, 5, 30))
    r2 = adapter.get_historical_rate(Currency.EUR, Currency.USD, date(2026, 5, 30))
    assert r1 == r2


# ---------------------------------------------------------------------------
# 5. Weekend walk-back — Saturday returns Friday's rate
# ---------------------------------------------------------------------------

def test_weekend_saturday_returns_friday_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _make_adapter(tmp_path)
    monkeypatch.setattr("app.adapters.fx_ecb.adapter._fetch_ecb_zip", lambda: _ZIP)

    # 2026-05-31 is Saturday — should fall back to Friday 2026-05-30
    rate = adapter.get_historical_rate(Currency.EUR, Currency.USD, date(2026, 5, 31))
    assert rate == Decimal("1.130000")


def test_weekend_sunday_returns_friday_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _make_adapter(tmp_path)
    monkeypatch.setattr("app.adapters.fx_ecb.adapter._fetch_ecb_zip", lambda: _ZIP)

    # 2026-06-01 is Sunday — should fall back to Friday 2026-05-30
    rate = adapter.get_historical_rate(Currency.EUR, Currency.USD, date(2026, 6, 1))
    assert rate == Decimal("1.130000")


# ---------------------------------------------------------------------------
# 6. Cross-rate derivation — USD/JPY via EUR cross
# ---------------------------------------------------------------------------

def test_cross_rate_usd_jpy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _make_adapter(tmp_path)
    monkeypatch.setattr("app.adapters.fx_ecb.adapter._fetch_ecb_zip", lambda: _ZIP)

    # rate(USD, JPY) = ecb[JPY] / ecb[USD] = 162.00 / 1.1300
    expected = (Decimal("162.00") / Decimal("1.1300")).quantize(Decimal("0.000001"))
    rate = adapter.get_historical_rate(Currency.USD, Currency.JPY, date(2026, 5, 30))
    assert rate == expected


def test_cross_rate_jpy_usd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _make_adapter(tmp_path)
    monkeypatch.setattr("app.adapters.fx_ecb.adapter._fetch_ecb_zip", lambda: _ZIP)

    # rate(JPY, USD) = ecb[USD] / ecb[JPY] = 1.1300 / 162.00
    expected = (Decimal("1.1300") / Decimal("162.00")).quantize(Decimal("0.000001"))
    rate = adapter.get_historical_rate(Currency.JPY, Currency.USD, date(2026, 5, 30))
    assert rate == expected


# ---------------------------------------------------------------------------
# 7. EUR base/quote special cases
# ---------------------------------------------------------------------------

def test_eur_usd_returns_ecb_rate_directly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _make_adapter(tmp_path)
    monkeypatch.setattr("app.adapters.fx_ecb.adapter._fetch_ecb_zip", lambda: _ZIP)

    # rate(EUR, USD) = ecb[USD] / ecb[EUR] = 1.1300 / 1 = 1.1300
    rate = adapter.get_historical_rate(Currency.EUR, Currency.USD, date(2026, 5, 30))
    assert rate == Decimal("1.130000")


def test_usd_eur_returns_inverse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _make_adapter(tmp_path)
    monkeypatch.setattr("app.adapters.fx_ecb.adapter._fetch_ecb_zip", lambda: _ZIP)

    # rate(USD, EUR) = ecb[EUR] / ecb[USD] = 1 / 1.1300
    expected = (Decimal("1") / Decimal("1.1300")).quantize(Decimal("0.000001"))
    rate = adapter.get_historical_rate(Currency.USD, Currency.EUR, date(2026, 5, 30))
    assert rate == expected


def test_same_currency_returns_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _make_adapter(tmp_path)
    monkeypatch.setattr("app.adapters.fx_ecb.adapter._fetch_ecb_zip", lambda: _ZIP)

    rate = adapter.get_historical_rate(Currency.USD, Currency.USD, date(2026, 5, 30))
    assert rate == Decimal("1")


# ---------------------------------------------------------------------------
# 8. clear_cache resets in-memory state
# ---------------------------------------------------------------------------

def test_clear_cache_resets_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _make_adapter(tmp_path)
    monkeypatch.setattr("app.adapters.fx_ecb.adapter._fetch_ecb_zip", lambda: _ZIP)

    adapter.get_historical_rate(Currency.EUR, Currency.USD, date(2026, 5, 30))
    assert adapter._data is not None

    adapter.clear_cache()
    assert adapter._data is None


# ---------------------------------------------------------------------------
# 9. Error conditions
# ---------------------------------------------------------------------------

def test_no_data_within_7_days_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Dataset only has data from 2026-05-28..30; ask for 2026-05-01 (way before)
    adapter = _make_adapter(tmp_path)
    monkeypatch.setattr("app.adapters.fx_ecb.adapter._fetch_ecb_zip", lambda: _ZIP)

    with pytest.raises(FxRateUnavailableError):
        adapter.get_historical_rate(Currency.EUR, Currency.USD, date(2026, 5, 1))


def test_corrupted_disk_cache_refetches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "ecb.json").write_text("NOT VALID JSON {{{{")
    adapter = _make_adapter(tmp_path)
    monkeypatch.setattr("app.adapters.fx_ecb.adapter._fetch_ecb_zip", lambda: _ZIP)

    rate = adapter.get_historical_rate(Currency.EUR, Currency.USD, date(2026, 5, 30))
    assert rate == Decimal("1.130000")
