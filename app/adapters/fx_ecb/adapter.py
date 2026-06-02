"""ECB daily reference rate adapter (HistoricalFxProvider, ADR-007).

Fetches the full ECB rate history from eurofxref-hist.zip (one HTTP call) and
caches it as JSON at the configured path. Subsequent lookups are served from the
in-memory or disk cache with no network access.

ECB publishes EUR-base rates only (e.g. USD = 1.0518 means 1 EUR = 1.0518 USD).
Cross rates are derived: rate(base, quote) = ecb[quote] / ecb[base], where
ecb[EUR] = 1 by definition.

Weekend and holiday gaps: the adapter walks back up to 7 calendar days to find
the nearest prior business day with a published rate.
"""
from __future__ import annotations

import csv
import io
import json
import os
import urllib.request
import zipfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.domain.money import Currency
from app.ports.fx_feed import FxRateUnavailableError, UnsupportedCurrencyPairError

_ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"

# Currencies the ECB publishes (= Currency enum minus EUR)
_SUPPORTED: frozenset[str] = frozenset(c.value for c in Currency if c != Currency.EUR)


def _fetch_ecb_zip() -> bytes:
    """Download the ECB history zip. Raises FxRateUnavailableError on failure."""
    try:
        with urllib.request.urlopen(_ECB_URL, timeout=30) as resp:
            data: bytes = resp.read()
            return data
    except Exception as exc:
        raise FxRateUnavailableError(
            Currency.EUR, Currency.USD, None, f"ECB fetch failed: {exc}"
        ) from exc


def parse_ecb_zip(zip_bytes: bytes) -> dict[str, dict[str, str]]:
    """Parse ECB zip bytes into {currency: {iso_date: rate_str}}.

    Separated from network fetch so tests can inject fixture bytes.
    """
    data: dict[str, dict[str, str]] = {}

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
        csv_text = zf.read(csv_name).decode("utf-8")

    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        date_str = (row.get("Date") or row.get(" Date") or "").strip()
        if not date_str:
            continue
        for col, val in row.items():
            col = col.strip()
            if col == "Date" or col not in _SUPPORTED:
                continue
            val = val.strip()
            if not val or val == "N/A":
                continue
            data.setdefault(col, {})[date_str] = val

    return data


class EcbFxAdapter:
    """HistoricalFxProvider backed by ECB daily reference rates with disk cache.

    Cache schema: {"USD": {"2025-12-31": "1.0518", ...}, "JPY": {...}}
    """

    def __init__(self, cache_path: Path) -> None:
        self._cache_path = cache_path
        self._data: dict[str, dict[str, str]] | None = None

    # ------------------------------------------------------------------
    # HistoricalFxProvider protocol
    # ------------------------------------------------------------------

    def get_historical_rate(
        self, base: Currency, quote: Currency, on_date: date
    ) -> Decimal:
        if base == quote:
            return Decimal("1")

        self._validate_pair(base, quote, on_date)

        data = self._load()
        effective_iso = self._walk_back(data, on_date)

        if effective_iso is None:
            # Cache may be stale — attempt a single re-fetch
            data = self._fetch_and_store()
            effective_iso = self._walk_back(data, on_date)

        if effective_iso is None:
            raise FxRateUnavailableError(
                base, quote, on_date,
                "No ECB rate found within 7 calendar days of the requested date"
            )

        return self._cross_rate(data, base, quote, effective_iso, on_date)

    def clear_cache(self) -> None:
        self._data = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_pair(
        self, base: Currency, quote: Currency, on_date: date
    ) -> None:
        if base != Currency.EUR and base.value not in _SUPPORTED:
            raise UnsupportedCurrencyPairError(
                base, quote, on_date, f"Unsupported currency: {base}"
            )
        if quote != Currency.EUR and quote.value not in _SUPPORTED:
            raise UnsupportedCurrencyPairError(
                base, quote, on_date, f"Unsupported currency: {quote}"
            )

    def _load(self) -> dict[str, dict[str, str]]:
        if self._data is not None:
            return self._data
        if self._cache_path.exists():
            try:
                with open(self._cache_path, encoding="utf-8") as f:
                    self._data = json.load(f)
                return self._data
            except Exception:
                pass
        self._data = self._fetch_and_store()
        return self._data

    def _fetch_and_store(self) -> dict[str, dict[str, str]]:
        data = parse_ecb_zip(_fetch_ecb_zip())
        self._data = data
        self._write_cache(data)
        return data

    def _write_cache(self, data: dict[str, dict[str, str]]) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._cache_path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            os.replace(tmp, self._cache_path)
        except OSError:
            pass  # cache write failure is non-fatal

    @staticmethod
    def _walk_back(
        data: dict[str, dict[str, str]], on_date: date, max_days: int = 7
    ) -> str | None:
        for i in range(max_days):
            iso = (on_date - timedelta(days=i)).isoformat()
            if any(iso in rates for rates in data.values()):
                return iso
        return None

    @staticmethod
    def _cross_rate(
        data: dict[str, dict[str, str]],
        base: Currency,
        quote: Currency,
        iso_date: str,
        original_date: date,
    ) -> Decimal:
        def ecb_per_eur(ccy: Currency) -> Decimal:
            if ccy == Currency.EUR:
                return Decimal("1")
            rates = data.get(ccy.value, {})
            val = rates.get(iso_date)
            if val is None:
                raise UnsupportedCurrencyPairError(
                    base, quote, original_date,
                    f"No ECB rate for {ccy} on {iso_date}"
                )
            return Decimal(val)

        # rate(base, quote) = quote_per_eur / base_per_eur
        return (ecb_per_eur(quote) / ecb_per_eur(base)).quantize(Decimal("0.000001"))
