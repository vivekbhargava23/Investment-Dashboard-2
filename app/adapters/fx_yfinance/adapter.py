"""FX rate adapters backed by yfinance.

FxYfinanceDiskAdapter: disk-cached historical rates + delegated live rates.
YfinanceLiveFxAdapter: in-memory TTL cache for live FX rates only.

Historical rates are cached indefinitely once written (history is immutable).
Disk cache files live at {cache_dir}/{FROM}_{TO}.json, one file per currency pair.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.adapters._yfinance_client import yf
from app.domain.money import Currency
from app.ports.fx_feed import FxProvider, FxRateUnavailableError, UnsupportedCurrencyPairError

# ---------------------------------------------------------------------------
# Canonical yfinance tickers for currency pairs.
# For reversed pairs, fetch the canonical ticker and invert.
# ---------------------------------------------------------------------------
_FX_CANONICAL: dict[tuple[Currency, Currency], str] = {
    (Currency.EUR, Currency.USD): "EURUSD=X",
    (Currency.EUR, Currency.JPY): "EURJPY=X",
    (Currency.USD, Currency.JPY): "USDJPY=X",
}

_SUPPORTED_PAIRS: frozenset[tuple[Currency, Currency]] = frozenset({
    (Currency.EUR, Currency.USD),
    (Currency.USD, Currency.EUR),
    (Currency.EUR, Currency.JPY),
    (Currency.JPY, Currency.EUR),
    (Currency.USD, Currency.JPY),
    (Currency.JPY, Currency.USD),
})


def _fx_yfinance_ticker(base: Currency, quote: Currency) -> tuple[str, bool]:
    """Return (yfinance_ticker, invert) for the given pair."""
    if (base, quote) in _FX_CANONICAL:
        return _FX_CANONICAL[(base, quote)], False
    return _FX_CANONICAL[(quote, base)], True


class YfinanceLiveFxAdapter:
    """FxProvider backed by yfinance with in-memory TTL cache for live rates.

    Also supports get_historical_rate via yfinance (TICKET-C1 will replace
    historical lookups with the ECB adapter once that is wired in).
    """

    _FX_CANONICAL = _FX_CANONICAL
    _SUPPORTED_PAIRS = _SUPPORTED_PAIRS

    def __init__(self, current_ttl_seconds: int = 60) -> None:
        self.current_ttl_seconds = current_ttl_seconds
        self._current_cache: dict[str, tuple[float, Decimal]] = {}
        self._historical_cache: dict[str, Decimal] = {}

    def get_current_rate(self, base: Currency, quote: Currency) -> Decimal:
        if (base, quote) not in _SUPPORTED_PAIRS:
            raise UnsupportedCurrencyPairError(
                base, quote, None,
                "Supported pairs: EUR/USD, USD/EUR, EUR/JPY, JPY/EUR, USD/JPY, JPY/USD"
            )

        cache_key = f"fx:{base}/{quote}"
        now = time.monotonic()

        if cache_key in self._current_cache:
            ts, value = self._current_cache[cache_key]
            if now - ts < self.current_ttl_seconds:
                return value

        try:
            yf_ticker, invert = _fx_yfinance_ticker(base, quote)
            t = yf.Ticker(yf_ticker)
            rate_raw = t.fast_info.get("lastPrice")

            if rate_raw is None or (isinstance(rate_raw, float) and rate_raw != rate_raw):
                hist = t.history(period="1d")
                if not hist.empty:
                    rate_raw = hist["Close"].iloc[-1]

            if rate_raw is None or (isinstance(rate_raw, float) and rate_raw != rate_raw):
                raise FxRateUnavailableError(
                    base, quote, None, "yfinance returned no current rate"
                )

            rate = Decimal(str(rate_raw))
            if invert:
                rate = Decimal("1") / rate
            rate = rate.quantize(Decimal("0.000001"))

            self._current_cache[cache_key] = (now, rate)
            return rate

        except FxRateUnavailableError:
            raise
        except Exception as e:
            raise FxRateUnavailableError(base, quote, None, str(e)) from e

    def get_historical_rate(self, base: Currency, quote: Currency, on_date: date) -> Decimal:
        if (base, quote) not in _SUPPORTED_PAIRS:
            raise UnsupportedCurrencyPairError(
                base, quote, on_date,
                "Supported pairs: EUR/USD, USD/EUR, EUR/JPY, JPY/EUR, USD/JPY, JPY/USD"
            )

        cache_key = f"fx:{base}/{quote}:{on_date.isoformat()}"
        if cache_key in self._historical_cache:
            return self._historical_cache[cache_key]

        try:
            yf_ticker, invert = _fx_yfinance_ticker(base, quote)
            t = yf.Ticker(yf_ticker)
            hist = t.history(start=on_date, end=on_date + timedelta(days=1))

            if hist.empty:
                hist = t.history(start=on_date - timedelta(days=7), end=on_date + timedelta(days=1))

            if hist.empty:
                raise FxRateUnavailableError(base, quote, on_date, f"No rate near {on_date}")

            rate_raw = hist["Close"].iloc[-1]
            if rate_raw != rate_raw:  # NaN
                raise FxRateUnavailableError(base, quote, on_date, f"NaN rate near {on_date}")

            rate = Decimal(str(rate_raw))
            if invert:
                rate = Decimal("1") / rate
            rate = rate.quantize(Decimal("0.000001"))

            self._historical_cache[cache_key] = rate
            return rate

        except FxRateUnavailableError:
            raise
        except Exception as e:
            raise FxRateUnavailableError(base, quote, on_date, str(e)) from e

    def clear_cache(self) -> None:
        self._current_cache.clear()
        self._historical_cache.clear()


class FxYfinanceDiskAdapter:
    """FxProvider wrapping an inner provider with disk cache for historical rates."""

    def __init__(self, cache_dir: Path, *, inner: FxProvider | None = None) -> None:
        self._cache_dir = cache_dir
        self._inner = inner
        self._memory: dict[str, Decimal] = {}

    # ------------------------------------------------------------------
    # FxProvider protocol
    # ------------------------------------------------------------------

    def get_historical_rate(self, base: Currency, quote: Currency, on_date: date) -> Decimal:
        key = f"{base}/{quote}/{on_date.isoformat()}"
        if key in self._memory:
            return self._memory[key]

        cached = self._read_from_disk(base, quote, on_date)
        if cached is not None:
            self._memory[key] = cached
            return cached

        rate = self._get_inner().get_historical_rate(base, quote, on_date)
        self._write_to_disk(base, quote, on_date, rate)
        self._memory[key] = rate
        return rate

    def get_current_rate(self, base: Currency, quote: Currency) -> Decimal:
        return self._get_inner().get_current_rate(base, quote)

    def clear_cache(self) -> None:
        self._memory.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_inner(self) -> FxProvider:
        if self._inner is None:
            self._inner = YfinanceLiveFxAdapter()
        return self._inner

    def _cache_path(self, base: Currency, quote: Currency) -> Path:
        return self._cache_dir / f"{base}_{quote}.json"

    def _read_from_disk(self, base: Currency, quote: Currency, on_date: date) -> Decimal | None:
        path = self._cache_path(base, quote)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data: dict[str, str] = json.load(f)
            val = data.get(on_date.isoformat())
            return Decimal(val) if val is not None else None
        except Exception:
            return None

    def _write_to_disk(self, base: Currency, quote: Currency, on_date: date, rate: Decimal) -> None:
        path = self._cache_path(base, quote)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    data: dict[str, str] = json.load(f)
            else:
                data = {}
            data[on_date.isoformat()] = str(rate)
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            os.replace(tmp, path)
        except Exception:
            pass  # cache write failure is non-fatal
