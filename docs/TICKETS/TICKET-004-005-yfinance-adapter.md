# TICKET-004-005 — yfinance adapter for prices and FX (consolidated)

**Status:** IN_REVIEW
**Priority:** P0
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-03)
**Implemented by:** _pending_
**Depends on:** TICKET-001 (domain models — Money, Currency)

> **Note on numbering:** This ticket consolidates what was originally planned as TICKET-004 (ECB FX adapter) and TICKET-005 (yfinance price adapter). In chat session 2026-05-03 we decided that yfinance handles both prices and FX adequately for a personal portfolio, eliminating the need for a separate ECB integration. The number `004-005` is preserved so the backlog stays sequentially traceable and no later ticket needs renumbering.

---

## Problem

We have a domain layer (TICKETs 001, 002) and a way to persist transactions (TICKET-003). What we don't have: any way to know what those transactions are *worth right now*. The portfolio's "live" view — current price, current FX rate, unrealised gain — needs an external data source.

This ticket builds two ports and one adapter that satisfies both:

1. **`PriceProvider` port** — the abstract contract for "give me the current or historical close price of a ticker."
2. **`FxProvider` port** — the abstract contract for "give me the current or historical EUR/USD rate."
3. **`YfinanceAdapter`** — a single concrete class that implements both ports using the `yfinance` Python library.

Two ports because they're conceptually distinct (a future Finnhub adapter would implement only `PriceProvider`); one adapter because yfinance happens to handle both data types well and there's no benefit to splitting the implementation.

After this ticket, the system can:
- Fetch live prices for any ticker the user holds.
- Fetch the current EUR/USD rate for valuation.
- Look up a historical price or FX rate for a given date (used by the Manage Portfolio form to pre-fill the FX rate when entering a USD transaction).

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-03:

1. **yfinance for both prices and FX.** Single library, handles both. ECB FX adapter abandoned because the precision difference (≤0.5%) doesn't matter for personal portfolio use, and the simpler integration outweighs the legal-precision argument.
2. **Smoothness is a hard requirement.** The UI should feel "snap to click." This is achieved with two cooperating cache layers: this ticket's in-memory adapter cache (60-second TTL on current data, infinite on historical) and Streamlit's `@st.cache_data` at the UI layer (added in TICKET-008). This ticket only owns the adapter cache.
3. **No background jobs, no threading.** The adapter is request-response and synchronous. Cache invalidation has exactly one trigger: a user-initiated refresh (the "Refresh" button in the UI calls `clear_cache()`). Predictable behaviour, no race conditions, no surprise stale data.
4. **No on-disk cache.** The in-memory dict rebuilds in 1–2 seconds per session start. Worth the trade for zero corruption risk and zero "did I clear the cache" debugging.
5. **Cost basis is never cached because it is never recomputed.** Cost basis EUR is frozen on the `Transaction` at creation time (TICKET-001 architecture). The cache only exists for live data and historical lookups used during transaction entry.
6. **EUR/USD only for now.** The `Currency` enum has only `EUR` and `USD`. The adapter validates and rejects other currencies. Adding GBP/CHF later is a one-line change in the enum plus a test; the adapter's logic generalises automatically because yfinance ticker construction is `f"{base}{quote}=X"`.
7. **Two test layers: fakes for unit tests, real yfinance for integration tests.** Unit tests use `tests/fakes/` Protocol implementations that don't touch the network. Integration tests are gated behind `@pytest.mark.integration` and skipped by default in CI. This keeps the fast feedback loop fast and shields CI from yfinance flakiness.

## Acceptance criteria

### Two ports

#### `app/ports/price_feed.py`

- [ ] `PriceProvider` is a `typing.Protocol` (not an ABC). Methods:
  - `get_current_price(self, ticker: str) -> Money` — fetch the most recent traded price. Currency is determined by the ticker (e.g., `NVDA` → USD, `RHM.DE` → EUR). The adapter is responsible for inferring the currency; callers must trust it.
  - `get_historical_close(self, ticker: str, on_date: date) -> Money` — fetch the close price for a specific past date. Same currency inference.
  - `clear_cache(self) -> None` — invalidate all cached prices.
- [ ] `PriceUnavailableError(Exception)` defined in this file. Constructor: `(ticker: str, reason: str)`. Message format: `"Price unavailable for {ticker}: {reason}"`. Exposes `.ticker` and `.reason` attributes.
- [ ] `TickerNotFoundError(PriceUnavailableError)` — subclass for the specific case of yfinance returning empty / 404. Distinguishable from network errors.

#### `app/ports/fx_feed.py`

- [ ] `FxProvider` is a `typing.Protocol`. Methods:
  - `get_current_rate(self, base: Currency, quote: Currency) -> Decimal` — returns rate as `quote_per_base`. E.g., `get_current_rate(EUR, USD)` returns "how many USD per 1 EUR" (~1.08 currently). For the inverse needed by the Transaction model (`fx_rate_eur` = "how many EUR per 1 native"), call `get_current_rate(USD, EUR)`.
  - `get_historical_rate(self, base: Currency, quote: Currency, on_date: date) -> Decimal` — same semantics, for a specific past date.
  - `clear_cache(self) -> None` — invalidate all cached rates.
- [ ] `FxRateUnavailableError(Exception)` — constructor `(base: Currency, quote: Currency, on_date: date | None, reason: str)`. Message: `"FX rate unavailable for {base}/{quote}{date_part}: {reason}"` where `date_part` is empty for current rates and ` on {on_date}` for historical.
- [ ] `UnsupportedCurrencyPairError(FxRateUnavailableError)` — raised if the pair is not EUR/USD or USD/EUR (in either direction). Distinguishable from network failures.

### One adapter

#### `app/adapters/yfinance_feed/__init__.py`

- [ ] Re-exports `YfinanceAdapter` so callers can `from app.adapters.yfinance_feed import YfinanceAdapter`.

#### `app/adapters/yfinance_feed/yfinance_adapter.py`

- [ ] `YfinanceAdapter` class. Constructor: `__init__(self, current_ttl_seconds: int = 60)`. The TTL parameter exists so tests can pass `0` for "no caching" or large values for "cache forever."
- [ ] Implements both `PriceProvider` and `FxProvider` Protocols (verify with `mypy` — Protocols are duck-typed, so this is enforced by usage rather than inheritance).

##### Internal cache structure

- [ ] Two dicts on the instance:
  - `_current_cache: dict[str, tuple[float, Money | Decimal]]` — key is `f"price:{ticker}"` for prices or `f"fx:{base}/{quote}"` for rates. Value is `(unix_timestamp_when_cached, value)`. Look-up checks if `time.monotonic() - timestamp < self.current_ttl_seconds`.
  - `_historical_cache: dict[str, Money | Decimal]` — key includes the date: `f"price:{ticker}:{on_date.isoformat()}"` or `f"fx:{base}/{quote}:{on_date.isoformat()}"`. No TTL — historical closes are immutable facts.
- [ ] Use `time.monotonic()` not `time.time()` for the TTL clock. Monotonic is immune to system clock changes (NTP adjustments, daylight savings); regular time isn't.

##### Currency inference for tickers

- [ ] Helper method `_infer_currency(ticker: str) -> Currency`:
  - If ticker contains `.DE`, `.F`, `.MI`, `.PA`, `.AS` (European exchanges) → `Currency.EUR`
  - Otherwise → `Currency.USD` (default for unsuffixed US tickers like `NVDA`, `MU`)
  - This is a pragmatic heuristic; document its limits in a docstring. Adding new exchanges is a one-line addition.
- [ ] Validate inferred currency against the `Currency` enum — if somehow a third currency comes back, raise `PriceUnavailableError(ticker, "Unsupported listing currency")`.

##### `get_current_price` implementation

- [ ] Steps:
  1. Check `_current_cache` with key `f"price:{ticker}"`. If present and within TTL → return cached `Money`.
  2. Call `yf.Ticker(ticker).fast_info["lastPrice"]` (or `.history(period="1d")["Close"].iloc[-1]` as fallback if `fast_info` returns None — yfinance's fast_info is faster but less reliable).
  3. If yfinance raises any exception OR returns `None`/`NaN` → raise `TickerNotFoundError(ticker, "yfinance returned no current price")`.
  4. Wrap the result: `Money(amount=Decimal(str(price)).quantize(Decimal("0.0001")), currency=inferred_currency)`. Note: `Decimal(str(price))` — never `Decimal(price)` — to avoid float drift.
  5. Cache the `Money` with current monotonic timestamp.
  6. Return.

##### `get_historical_close` implementation

- [ ] Steps:
  1. Check `_historical_cache` with key `f"price:{ticker}:{on_date.isoformat()}"`. If present → return.
  2. Call `yf.Ticker(ticker).history(start=on_date, end=on_date + timedelta(days=1))`. yfinance's `start`/`end` is half-open; this gets exactly one day.
  3. If the resulting DataFrame is empty (e.g., weekend, holiday, or before the ticker's IPO) → expand the lookup window: `history(start=on_date - timedelta(days=7), end=on_date + timedelta(days=1))` and take the last row (most recent close on or before `on_date`). If still empty → raise `PriceUnavailableError(ticker, f"No historical close near {on_date}")`.
  4. Wrap and cache as in `get_current_price`.

##### `get_current_rate` implementation

- [ ] Steps:
  1. Validate the pair: if not `(EUR, USD)` or `(USD, EUR)` → raise `UnsupportedCurrencyPairError`.
  2. Determine the yfinance ticker. yfinance uses `EURUSD=X` to mean "USD per 1 EUR."
     - For `get_current_rate(EUR, USD)` → fetch `EURUSD=X`, return as-is.
     - For `get_current_rate(USD, EUR)` → fetch `EURUSD=X`, return `Decimal("1") / rate`.
  3. Cache key: always `f"fx:{base}/{quote}"`. Cache the *direction-specific* rate, so each direction is one fetch and one cache entry. (Inverting on lookup is fine but caching both directions is also fine; the spec says use the direction-specific key for clarity.)
  4. Quantize to 6 decimal places: `rate.quantize(Decimal("0.000001"))`. Six dp is enough for FX precision and avoids spurious differences between `0.92` and `0.920000`.
  5. Failure mode: yfinance returns no data → `FxRateUnavailableError(base, quote, None, "yfinance returned no current rate")`.

##### `get_historical_rate` implementation

- [ ] Steps:
  1. Validate the pair (same as current).
  2. Check `_historical_cache`.
  3. yfinance call: `yf.Ticker("EURUSD=X").history(start=on_date, end=on_date + timedelta(days=1))`. Take the close.
  4. Same weekend/holiday expansion as `get_historical_close` (FX trades 24/5 but yfinance reports daily closes; weekends will be empty).
  5. Inversion logic same as current rate.
  6. Quantize to 6 dp, cache, return.

##### `clear_cache` implementation

- [ ] Empty both `_current_cache` and `_historical_cache` dicts. Two lines. Do not clear yfinance's own internal caches (we don't control those, and they're not the issue we're solving).

### Test fakes (reusable across all later tickets)

#### `tests/fakes/__init__.py`

- [ ] Re-exports `FakePriceProvider` and `FakeFxProvider`.

#### `tests/fakes/price_feed.py`

- [ ] `FakePriceProvider` class. Implements the `PriceProvider` Protocol via duck typing.
- [ ] Constructor: `__init__(self, current_prices: dict[str, Money] | None = None, historical_prices: dict[tuple[str, date], Money] | None = None)`.
- [ ] `get_current_price`: lookup in `current_prices` dict; raise `TickerNotFoundError` if missing.
- [ ] `get_historical_close`: lookup by `(ticker, on_date)` tuple; raise if missing.
- [ ] `clear_cache`: no-op.
- [ ] Helper method `set_price(ticker: str, money: Money)` for tests that need to mutate during the test.

#### `tests/fakes/fx_feed.py`

- [ ] `FakeFxProvider` class. Implements `FxProvider`.
- [ ] Constructor: `__init__(self, current_rates: dict[tuple[Currency, Currency], Decimal] | None = None, historical_rates: dict[tuple[Currency, Currency, date], Decimal] | None = None)`.
- [ ] Methods follow the same lookup-or-raise pattern.

### Tests

#### `tests/unit/adapters/test_yfinance_adapter_caching.py`

These tests do NOT hit the network. They use `pytest-mock` (or `unittest.mock`) to patch `yfinance.Ticker` so the cache logic can be tested in isolation. Caching is the highest-risk part of this adapter; it deserves dedicated tests.

- [ ] **Current price cached within TTL**: patch `yf.Ticker` to return $100. Call `get_current_price("NVDA")` twice. Assert yfinance was called exactly once and both returns equal Money($100, USD).
- [ ] **Current price refetched after TTL expires**: same setup, but use `current_ttl_seconds=0`. Patch `time.monotonic` to advance. Both calls hit yfinance.
- [ ] **Historical never expires**: call `get_historical_close("NVDA", date(2024,1,2))` twice. yfinance called once.
- [ ] **`clear_cache` invalidates current**: prime cache with one call, `clear_cache()`, second call hits yfinance again.
- [ ] **`clear_cache` invalidates historical**: same pattern.
- [ ] **Different tickers cached independently**: `get_current_price("NVDA")` and `get_current_price("MU")` are two separate cache entries.
- [ ] **Same ticker different dates cached independently**: `get_historical_close("NVDA", date(2024,1,2))` and `(NVDA, 2024,1,3)` are two entries.
- [ ] **Cache key format**: explicitly assert that `f"price:{ticker}"` and `f"price:{ticker}:{date}"` keys exist in the dicts after population (this catches refactor bugs where cache keys silently change).

#### `tests/unit/adapters/test_yfinance_adapter_inference.py`

- [ ] **Currency inference: `NVDA` → USD**
- [ ] **Currency inference: `RHM.DE` → EUR**
- [ ] **Currency inference: `HY9H.F` → EUR**
- [ ] **Currency inference: `MU` → USD** (no suffix)
- [ ] **Currency inference: `MTE.DE` → EUR**
- [ ] **Edge case: `BRK.B` (US ticker with a dot but not a European suffix)** → USD. The inference must check for known European suffixes, not just "contains a dot."

#### `tests/unit/adapters/test_yfinance_adapter_errors.py`

- [ ] **yfinance raises → `PriceUnavailableError`**: patch `yf.Ticker` to raise `Exception("network down")`. Assert `PriceUnavailableError` raised, with the original exception chained (`__cause__`).
- [ ] **yfinance returns NaN → `TickerNotFoundError`**: patch to return `float("nan")`. Assert `TickerNotFoundError`.
- [ ] **yfinance returns empty DataFrame for historical → expansion logic kicks in**: first call returns empty, second (wider window) returns one row. Adapter returns the row's close.
- [ ] **Both windows empty → `PriceUnavailableError`**: both calls return empty. Adapter raises with a message containing the date.
- [ ] **Unsupported currency pair**: `get_current_rate(EUR, Currency("GBP"))` (need to fake a Currency value) → assert `UnsupportedCurrencyPairError`. *Note: since the Currency enum only has EUR and USD, this test may need to be skipped or written in a way that doesn't require constructing an unsupported value. Acceptable alternative: write the test to confirm `get_current_rate(EUR, USD)` and `(USD, EUR)` both succeed; document that adding new currencies is the test's purpose.*

#### `tests/unit/fakes/test_fakes.py`

- [ ] **`FakePriceProvider` returns prices it was constructed with.**
- [ ] **`FakePriceProvider` raises `TickerNotFoundError` for missing tickers.**
- [ ] **`FakePriceProvider.set_price` mutates.**
- [ ] **`FakeFxProvider` round-trips both current and historical.**
- [ ] **Both fakes are usable as `PriceProvider`/`FxProvider` types**: `pp: PriceProvider = FakePriceProvider(...)` typechecks under mypy.

#### `tests/integration/test_yfinance_real.py`

These tests hit the real yfinance service and are gated.

- [ ] Mark all tests in this file with `@pytest.mark.integration`.
- [ ] Add `markers = ["integration: hits real network services"]` to `pyproject.toml` `[tool.pytest.ini_options]` if not already present.
- [ ] Configure pytest so integration tests are skipped by default. Add a CLI option `--run-integration` that opts in. Implement via `conftest.py`:
  ```python
  def pytest_addoption(parser):
      parser.addoption("--run-integration", action="store_true", default=False)

  def pytest_collection_modifyitems(config, items):
      if config.getoption("--run-integration"):
          return
      skip_integration = pytest.mark.skip(reason="needs --run-integration flag")
      for item in items:
          if "integration" in item.keywords:
              item.add_marker(skip_integration)
  ```
- [ ] **Smoke: real NVDA current price** — fetch, assert it's a Money in USD with positive amount.
- [ ] **Smoke: real RHM.DE current price** — assert Money in EUR.
- [ ] **Smoke: real EUR/USD rate** — assert Decimal between 0.5 and 2.0 (sanity bounds).
- [ ] **Smoke: NVDA historical close on 2024-01-02** — assert it returns a known-stable historical value (not exact match — within 0.5% tolerance to absorb yfinance backfill differences).
- [ ] CI does NOT run these. The README documents how to run locally: `pytest --run-integration tests/integration/test_yfinance_real.py`.

### Lints / quality
- [ ] `pytest` — all unit tests pass; integration tests skipped by default
- [ ] `ruff check .` — passes
- [ ] `mypy app/` — passes; **strict on `app/domain/`**, `app/ports/` clean too
- [ ] `lint-imports` — passes; in particular:
  - `app.ports` imports from `app.domain` only
  - `app.adapters.yfinance_feed` imports from `app.ports` and `app.domain` only (NOT from `app.services` or `app.ui`)

### State updates (per CLAUDE.md session-end ritual)
- [ ] `docs/SESSION_LOG.md` appended
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-004-005 → IN_REVIEW)
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-005 row → IN_REVIEW)
- [ ] Ticket file `Status: IN_REVIEW`
- [ ] PR opened via `gh pr create --fill --base main`

## Files created

```
app/ports/price_feed.py
app/ports/fx_feed.py
app/adapters/yfinance_feed/__init__.py
app/adapters/yfinance_feed/yfinance_adapter.py
tests/fakes/__init__.py
tests/fakes/price_feed.py
tests/fakes/fx_feed.py
tests/unit/adapters/__init__.py
tests/unit/adapters/test_yfinance_adapter_caching.py
tests/unit/adapters/test_yfinance_adapter_inference.py
tests/unit/adapters/test_yfinance_adapter_errors.py
tests/unit/fakes/__init__.py
tests/unit/fakes/test_fakes.py
tests/integration/test_yfinance_real.py
tests/conftest.py            ← creates the --run-integration option
```

## Files possibly updated

```
app/ports/__init__.py        ← export PriceProvider, FxProvider, errors
app/adapters/__init__.py     ← (no change strictly needed)
pyproject.toml               ← add `markers` config to pytest section
docs/TICKETS/BACKLOG.md      ← TICKET-005 row → IN_REVIEW
```

## Out of scope

- Streamlit-level caching (`@st.cache_data`) — that's TICKET-008's job
- Persistent on-disk price cache — explicit non-goal of this ticket
- Finnhub adapter / fallback chain — when yfinance is insufficient, a future ticket adds Finnhub. The Protocol-based design means it slots in without changing callers.
- Background refresh, websockets, real-time streaming — explicitly not doing
- Currency support beyond EUR and USD — adding GBP/CHF is a future enum extension
- Wiring the adapter into the Streamlit app — that's TICKET-006 (valuation service) and TICKET-008 (UI)
- Rate-limit handling for yfinance — yfinance has no documented rate limit; if we hit one, a future ticket addresses it

## Notes (architectural and methodological — for future AI sessions)

### Why the two-cache architecture matters

The cache in this ticket is the *first* of two cache layers. The second is `@st.cache_data` at the UI level (TICKET-008). They cooperate:

- **Adapter cache**: shields the network. Multiple calls to `get_current_price("NVDA")` within 60s → one network call.
- **Streamlit cache**: shields the *computation*. Multiple Streamlit reruns with identical inputs → one call to `compute_positions()`.

Without the Streamlit cache, every UI interaction (clicking a chart timeframe, hovering a row) would re-run `compute_positions()` even though prices haven't changed. Without the adapter cache, the first call after every cache-miss in Streamlit would hit yfinance. Both layers together produce "snap to click."

The single trigger for invalidating both: the user clicks "Refresh." The UI calls `service.clear_caches()` which calls `adapter.clear_cache()` AND `st.cache_data.clear()`. Predictable, manual, no surprises.

### Why no on-disk cache yet

Three reasons:

1. **Rebuild cost is small.** A typical session uses ~10 tickers; first-load cache population is ~1–2 seconds. Not noticeable after the first interaction.
2. **Corruption risk.** Disk caches need atomic writes, schema versioning, and cleanup logic. We have that pattern (TICKET-003) but adding it for prices doubles the surface area for bugs.
3. **Staleness hazards.** A disk cache from yesterday might silently load when you start the app today. The 60s in-memory TTL is far stricter and far safer.

If profiling later shows that session-start latency is a real annoyance, add a Parquet-backed historical cache in a later ticket. Don't speculate.

### Why historical is infinite TTL

A daily close on 2024-03-15 is, by definition, a fact about the past. yfinance can correct historical data (rare, e.g., for stock splits), but for a personal portfolio the corrections don't matter and the user can hit Refresh if they want to repull.

### Why fakes live in `tests/fakes/` not `tests/unit/`

The fakes are reused by every later ticket's tests (services, UI, end-to-end). Putting them in their own package makes the dependency direction clear: production code → ports → fakes (in tests). If we put them under `tests/unit/`, future tests in `tests/integration/` would have to reach across — fine in Python but architecturally muddy.

### Why integration tests are skipped by default

Three reasons specific to yfinance:

1. **It can be flaky.** Yahoo occasionally rate-limits or returns intermittent errors. CI failures from external services are noise, not signal.
2. **They're slow.** Real network calls take 200ms+ each. Integration tests would slow `pytest` from <1s to 10s+.
3. **They're not strictly necessary in CI.** The unit tests with mocks confirm our code is correct. The integration tests confirm yfinance still works the way we think — useful but not blocking.

The `--run-integration` flag lets you run them locally before a release if you want to sanity-check the integration. CI keeps the fast feedback loop.

### Why monotonic clock for the TTL

Regular `time.time()` reflects wall-clock time, which can jump forward or backward (NTP sync, manual changes, daylight savings). A TTL based on wall-clock can fire late or early. `time.monotonic()` always advances — perfect for "has 60 seconds elapsed since I cached this?"

### Why the adapter is one class, not two

`PriceProvider` and `FxProvider` are conceptually distinct ports (a Finnhub adapter would be price-only). But the implementation against yfinance shares: cache structure, time logic, error wrapping, ticker construction patterns. Splitting into two classes would duplicate ~50 lines of code and add the risk that the two caches behave subtly differently. One class with two cache namespaces is cleaner. The Protocol-based design means callers see the abstractions, not the implementation choice.

### What to do when yfinance breaks

It will. Some morning, yfinance will return None for everything because Yahoo changed their internal API. The right response:

1. Don't patch the adapter to work around it inline. Open a ticket: "yfinance broken, evaluate Finnhub fallback."
2. The valuation service (TICKET-006) catches `PriceUnavailableError` and returns positions with `live_price_eur=None`. The UI shows "—" for those. Cost basis still works.
3. Discuss in chat (with me) whether to add Finnhub now or wait.

This ticket's job is to fail cleanly when yfinance breaks. Recovery is a downstream concern.

### Methodology note: why this ticket is dense

This ticket file is long (and that's the point). Future AI sessions reading this should understand: a comprehensive ticket file is worth more than a "brief" one because it eliminates ambiguity at execution time. Every test case named here is a test that gets written. Every architectural decision is a design choice that will not be re-litigated. The cost is 30 minutes of careful drafting in chat; the savings are hours of debugging caused by ambiguous specs.

When future tickets reuse patterns established here (cache layers, fake providers, integration test gating), they don't need to re-explain — they reference this ticket. The first ticket of a kind is verbose; the tenth is short.
