# TICKET-025 — Company data layer: models, ports, yfinance + Finnhub adapters, JSON cache with TTL

**Status:** QUEUED
**Priority:** HIGH
**Estimated session length:** 1.5 – 2 hr
**Drafted by:** Vivek + Claude (chat 2026-05-12)
**Implemented by:** _pending_
**Depends on:** TICKET-001 (domain Money), TICKET-020 (TickerResolver port — for ticker validation conventions), TICKET-022a (`OhlcDataProvider` — reuse the price history adapter)

> **After this ticket merges, the dashboard can fetch and cache a full company profile.** A new `app/domain/company.py` defines `CompanyData` and its sub-models (profile, latest quote, price history pointer, fundamentals, multiples, dividends, ownership, insider transactions). A `CompanyDataProvider` Port is added under `app/ports/`. Two adapters ship: a `company_yfinance` adapter that fills what yfinance can fill, and a `company_finnhub` adapter that fills the rest (next earnings, insider transactions, institutional holders). A third decorator adapter `company_cache` wraps either real adapter with per-section JSON caching at `data/companies/`. **No UI in this ticket.** Tabs and pages come in C2–C7.

---

## Problem

The existing Research page (TICKET-022b) renders an OHLC chart and basic info for one ticker. The Company Deep Dive milestone (see `docs/COMPANY_DEEP_DIVE_HANDOFF.md`) needs much more: fundamentals over time, multiples history, ownership, insider activity, dividend history. That data has to come from yfinance + Finnhub, has to be cached on disk to keep the UI snappy and the rate limits respected, and has to live behind a Port so the UI layers above it (C2–C7) can be written against a stable interface.

This ticket builds **only** the data layer — domain models, the Port, three adapters, and a service that wires them. The Company page itself, the tabs, the watchlist, and the glossary all sit on top of this in subsequent tickets.

C1 is foundational. C2–C7 will not be implementable until C1 is merged.

---

## Architectural decisions implemented by this ticket

These were settled in the brainstorm session (see `docs/COMPANY_DEEP_DIVE_HANDOFF.md`) and the chat session 2026-05-12.

### 1. Three cache files per ticker, not one

Each ticker gets three files under `data/companies/<TICKER>/`:

```
data/companies/
└── NVDA/
    ├── profile.json       ← name, sector, industry, country, ISIN, employees, mcap-as-of (TTL 30d)
    ├── prices.json        ← latest quote + last 5Y daily close history (TTL 15min market hours, 24h after close)
    └── financials.json    ← quarterly + annual fundamentals, multiples, dividends, ownership, insider tx (TTL 24h)
```

Three files, not one big file, for three reasons:

1. **Independent TTLs.** Profile is stable for weeks; prices move every minute. Mixing them forces one TTL to win, which means either stale prices or wasted profile refreshes.
2. **No read-modify-write race.** A single-file design forces every refresh to read the whole file, mutate the section, and rewrite. Two refreshes in flight can stomp each other. With three files, each refresh writes its own file independently.
3. **Easier to inspect.** A future support session can `cat data/companies/NVDA/prices.json` and see exactly the price cache state without wading through 200 lines of financials.

Within `financials.json`, the four sub-sections (fundamentals, multiples, dividends, ownership_and_insiders) share a TTL because they're all in the "fetched once a day" tier. If a future ticket wants to separate them, that's a refactor.

### 2. Cache file format with explicit `fetched_at` and `source`

Every cache file is JSON of shape:

```json
{
  "ticker": "NVDA",
  "fetched_at": "2026-05-12T14:23:00+00:00",
  "source": "yfinance",
  "data": { ... }
}
```

The `fetched_at` timestamp is **timezone-aware ISO 8601, UTC**. The cache TTL check compares `now() - fetched_at` against the TTL for that section.

`source` is `"yfinance"` or `"finnhub"` — a debug aid; the cache adapter doesn't branch on it.

`data` is the serialised Pydantic model dump for that section.

### 3. Domain models are frozen Pydantic v2; the `CompanyData` root has all-optional sub-sections

```python
class CompanyProfile(BaseModel):
    model_config = ConfigDict(frozen=True)
    ticker: str
    name: str
    isin: str | None
    sector: str | None
    industry: str | None
    country: str | None
    currency: str                       # e.g. "USD", "EUR"
    employees: int | None
    market_cap: Money | None
    long_description: str | None

class LatestQuote(BaseModel):
    model_config = ConfigDict(frozen=True)
    ticker: str
    price: Money
    previous_close: Money
    day_change_pct: Decimal              # signed
    as_of: datetime                      # UTC

class PriceHistoryPoint(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: date
    close: Decimal                       # in the ticker's native currency
    volume: int | None

class QuarterlyFundamentals(BaseModel):
    model_config = ConfigDict(frozen=True)
    period_end: date                     # last day of the quarter
    revenue: Decimal | None
    gross_profit: Decimal | None
    operating_income: Decimal | None     # EBIT
    net_income: Decimal | None
    free_cash_flow: Decimal | None
    eps_diluted: Decimal | None
    shares_diluted: int | None
    # Balance sheet bits
    total_debt: Decimal | None
    cash_and_equivalents: Decimal | None
    # Derived (computed at fetch time, frozen on the model)
    net_debt: Decimal | None             # total_debt - cash
    ebitda: Decimal | None
    currency: str                        # the report currency

class AnnualFundamentals(BaseModel):
    model_config = ConfigDict(frozen=True)
    fiscal_year: int
    period_end: date
    # ...same fields as QuarterlyFundamentals
    revenue: Decimal | None
    gross_profit: Decimal | None
    operating_income: Decimal | None
    net_income: Decimal | None
    free_cash_flow: Decimal | None
    eps_diluted: Decimal | None
    shares_diluted: int | None
    total_debt: Decimal | None
    cash_and_equivalents: Decimal | None
    net_debt: Decimal | None
    ebitda: Decimal | None
    capex: Decimal | None                # annual only — for capital allocation tab
    buybacks: Decimal | None             # annual only
    dividends_paid: Decimal | None       # annual only
    stock_based_compensation: Decimal | None
    currency: str

class CurrentMultiples(BaseModel):
    model_config = ConfigDict(frozen=True)
    as_of: datetime
    pe_trailing: Decimal | None
    ps_trailing: Decimal | None
    ev_ebitda: Decimal | None
    p_fcf: Decimal | None
    p_book: Decimal | None
    dividend_yield_pct: Decimal | None   # signed; null if non-payer

class DividendEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    ex_date: date
    amount_per_share: Decimal
    currency: str

class InstitutionalHolder(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    shares_held: int
    pct_of_shares_outstanding: Decimal
    shares_change_qoq: int | None        # signed; null if first report
    as_of: date

class InsiderTransaction(BaseModel):
    model_config = ConfigDict(frozen=True)
    insider_name: str
    insider_title: str | None
    transaction_date: date
    transaction_type: Literal["BUY", "SELL", "OPTION_EXERCISE", "OTHER"]
    shares: int
    price_per_share: Decimal | None
    value: Decimal | None                # in ticker's native currency

class OwnershipSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    as_of: date
    insider_ownership_pct: Decimal | None
    institutional_ownership_pct: Decimal | None
    top_institutional_holders: list[InstitutionalHolder]
    recent_insider_transactions: list[InsiderTransaction]   # last 12 months

class NextCatalyst(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["EARNINGS", "DIVIDEND", "EX_DIVIDEND", "SPLIT"]
    date: date
    detail: str | None                   # e.g. "Q1 FY26 earnings"

class CompanyData(BaseModel):
    """Root aggregate. Every sub-section is optional — adapters fill what they can."""
    model_config = ConfigDict(frozen=True)
    ticker: str
    profile: CompanyProfile | None
    latest_quote: LatestQuote | None
    price_history: list[PriceHistoryPoint]         # may be empty; never None
    quarterly_fundamentals: list[QuarterlyFundamentals]  # may be empty
    annual_fundamentals: list[AnnualFundamentals]        # may be empty
    current_multiples: CurrentMultiples | None
    dividends: list[DividendEvent]                 # may be empty
    ownership: OwnershipSnapshot | None
    next_catalyst: NextCatalyst | None
    # Per-section fetch metadata — surfaced to UI for "Data as of HH:MM"
    profile_fetched_at: datetime | None
    prices_fetched_at: datetime | None
    financials_fetched_at: datetime | None
    # Per-section fetch errors — surfaced to UI as banners ("Insider data unavailable: rate limit")
    fetch_errors: dict[str, str]                   # section name → error string; empty dict if all OK
```

Two rules on the model:

- **Frozen.** Once built, the object cannot be mutated. Refreshes return a new `CompanyData`.
- **All-optional sub-sections.** If yfinance can't supply `quarterly_fundamentals` for a given ticker, the list is empty. The UI shows "data unavailable for this section" — never silently substitutes. This is the "no silent fallback" rule from METHODOLOGY's anti-patterns.

### 4. The Port

```python
# app/ports/company_data.py

class CompanyDataProvider(Protocol):
    """Single read interface for everything Company Deep Dive needs."""

    def get_company(self, ticker: str) -> CompanyData:
        """Fetch full company data. Never raises for partial data — populates fetch_errors instead.

        Raises only for completely unrecoverable cases (invalid ticker format, all sources down).
        """
        ...

    def refresh_section(
        self,
        ticker: str,
        section: Literal["profile", "prices", "financials"],
    ) -> CompanyData:
        """Force-refresh a specific cache section. Returns the new full CompanyData.

        For cache adapters: invalidate that section's cache file and re-fetch.
        For non-cache adapters: equivalent to get_company (no cache to bypass).
        """
        ...
```

That's the entire surface area. Two methods. Adapters can be unit-tested against this Protocol; services depend on this Protocol; the cache decorator implements this Protocol wrapping another instance of this Protocol.

### 5. Three adapters, layered via composition

```
company_cache  →  wraps  →  company_yfinance + company_finnhub (composed)
```

- **`app/adapters/company_yfinance/`** — implements `CompanyDataProvider` against yfinance. Fills profile, latest quote, price history, fundamentals, current multiples, dividends. Leaves `ownership` and `next_catalyst` empty (yfinance is unreliable for those).
- **`app/adapters/company_finnhub/`** — implements `CompanyDataProvider` against Finnhub. Fills `next_catalyst` (next earnings via `/stock/earnings-calendar`), `ownership.top_institutional_holders` (via `/stock/institutional-ownership`), `ownership.recent_insider_transactions` (via `/stock/insider-transactions`). Leaves price history, fundamentals etc. empty.
- **`app/adapters/company_composite/`** — implements `CompanyDataProvider` by calling both underlying adapters and merging their `CompanyData` results into one. Each section comes from whichever adapter populated it; if both did, yfinance wins for everything except `ownership` and `next_catalyst` (where Finnhub wins).
- **`app/adapters/company_cache/`** — decorator. Wraps the composite. On `get_company`, checks each of the three cache files; if fresh (within TTL), reads from disk; if stale or missing, calls the wrapped adapter for that section only, writes the result to disk, returns the merged `CompanyData`. The merge respects the per-section structure.

`refresh_section` skips the cache check for the named section. The other two sections still serve from cache.

The composite adapter exists so the cache adapter sees one Provider, not two. Without it, the cache adapter would need to know about two underlying adapters, which couples concerns.

### 6. Adapter wiring lives in `app/adapters/company_factory.py`

A single module-level function:

```python
def build_company_provider(
    *,
    cache_root: Path = Path("data/companies"),
    finnhub_api_key: str | None = None,
) -> CompanyDataProvider:
    """Build the production CompanyDataProvider: cache(composite(yfinance, finnhub))."""
```

Service-layer code calls `build_company_provider()` once at app startup (wired in `app/ui/wiring.py`). Tests bypass this and construct in-memory fakes directly.

If `finnhub_api_key` is `None`, the composite is built with only the yfinance adapter — Finnhub sections will simply be missing from `CompanyData`. This is graceful degradation: the user can run the app without a Finnhub key.

### 7. Cache TTLs are constants in `app/adapters/company_cache/ttl.py`

```python
PROFILE_TTL = timedelta(days=30)
PRICES_TTL_MARKET_HOURS = timedelta(minutes=15)
PRICES_TTL_AFTER_CLOSE = timedelta(hours=24)
FINANCIALS_TTL = timedelta(hours=24)

def prices_ttl(now: datetime) -> timedelta:
    """Return 15min during NYSE market hours (14:30–21:00 UTC Mon–Fri), 24h otherwise."""
```

The market-hours check is a pure function taking `now` as a parameter (no `datetime.now()` inside). Test it directly.

NYSE hours rather than a more nuanced exchange-aware check because the primary use case is US/CA tickers via Finnhub and US-listed yfinance. European tickers will still get reasonable freshness (15min during NYSE overlap is fine for end-of-day uses).

### 8. Cache reads tolerate corrupted files; cache writes are atomic

If a cache file exists but cannot be parsed (truncated, hand-edited, model schema changed), the cache adapter:

1. Logs a warning: `Cache file {path} is corrupt: {reason}. Re-fetching.`
2. Treats the file as missing and re-fetches.
3. Overwrites the corrupt file with fresh data.

It does **not** raise. A corrupt cache file is recoverable; the user shouldn't see an exception.

Writes are atomic: write to `<path>.tmp`, then `os.replace(<path>.tmp, <path>)`. This avoids a half-written file if the process dies mid-write.

### 9. Service layer is thin

```python
# app/services/company.py

def get_company(ticker: str, *, provider: CompanyDataProvider) -> CompanyData:
    """Fetch (cached or fresh) full company data for a ticker."""
    return provider.get_company(ticker.upper())

def refresh_company_section(
    ticker: str,
    section: Literal["profile", "prices", "financials"],
    *,
    provider: CompanyDataProvider,
) -> CompanyData:
    """Force-refresh one section. UI calls this from the per-tab refresh button."""
    return provider.refresh_section(ticker.upper(), section)
```

Two functions, both two-liners. The Port already does the work; the service exists so the UI doesn't import the Port directly and so future cross-cutting logic (e.g. logging, metrics) has a home.

### 10. No streamlit, no UI, no glossary in this ticket

This ticket adds **zero** files under `app/ui/`. The Company page, the tabs, the watchlist, and the glossary tooltip system are all in C2–C7. C1 must be reviewable on its own: the diff should not touch any UI file.

---

## Acceptance criteria

### `app/domain/company.py` — new module

- [ ] Defines every Pydantic model from decision §3 exactly: `CompanyProfile`, `LatestQuote`, `PriceHistoryPoint`, `QuarterlyFundamentals`, `AnnualFundamentals`, `CurrentMultiples`, `DividendEvent`, `InstitutionalHolder`, `InsiderTransaction`, `OwnershipSnapshot`, `NextCatalyst`, `CompanyData`.
- [ ] Every model is frozen (`model_config = ConfigDict(frozen=True)`).
- [ ] `Money` from `app.domain.models` is used for monetary values that carry a currency; raw `Decimal` is used for ratios/percentages and for the per-fundamentals reporting-currency amounts (`revenue`, `net_income` etc.) where the currency is on the parent.
- [ ] No `Any`, no `dict[str, Any]`, no `object` field types. Everything typed.
- [ ] **Layer rules:** zero I/O imports. No `requests`, `httpx`, `yfinance`, `pathlib`, `open`. No `streamlit`. No `datetime.now()` calls inside any method or default factory (any `datetime` is passed in).

### `app/ports/company_data.py` — new Port

- [ ] Defines `CompanyDataProvider` as a `runtime_checkable` `Protocol` with `get_company` and `refresh_section` per decision §4.
- [ ] Defines a custom exception `CompanyDataError(Exception)` raised only for unrecoverable cases (invalid ticker, all sources down). **Not** raised for partial data.
- [ ] No imports outside `typing`, `app.domain.company`, and `app.domain.models`.

### `app/adapters/company_yfinance/` — yfinance adapter

- [ ] New package directory with `__init__.py` exposing `YfinanceCompanyAdapter`.
- [ ] Implements `CompanyDataProvider`.
- [ ] `get_company`:
  - Builds `yf.Ticker(ticker)` once.
  - Populates `profile` from `.info` (name, sector, industry, country, currency, employees, mcap, long_business_summary).
  - Populates `latest_quote` from `.info` (regularMarketPrice + regularMarketPreviousClose).
  - Populates `price_history` from `.history(period="5y")` — last 5 years of daily closes.
  - Populates `quarterly_fundamentals` from `.quarterly_financials` + `.quarterly_balance_sheet` + `.quarterly_cashflow` for the last 20 quarters. Derive `net_debt = total_debt - cash_and_equivalents` and `ebitda = operating_income + depreciation`.
  - Populates `annual_fundamentals` from the annual equivalents for the last 10 years. Includes `capex`, `buybacks` (from cashflow `Common Stock Repurchased`), `dividends_paid`, `stock_based_compensation`.
  - Populates `current_multiples` from `.info` (`trailingPE`, `priceToSalesTrailing12Months`, `enterpriseToEbitda`, `priceToBook`, `dividendYield`). Compute `p_fcf` from price × shares ÷ ttm-FCF.
  - Populates `dividends` from `.dividends` (full history).
  - Leaves `ownership = None`, `next_catalyst = None`.
- [ ] **Partial-fill behaviour:** if any individual section fetch fails (yfinance throws, returns empty df, returns NaN where required), that section is left empty/None and a string is added to `fetch_errors[section]` describing the failure. The function still returns a `CompanyData`.
- [ ] **Unrecoverable case:** if `yf.Ticker(ticker).info` returns an empty dict or yfinance signals the ticker is invalid (`info.get("regularMarketPrice") is None and info.get("symbol") is None`), raise `CompanyDataError(f"Ticker {ticker!r} not found")`. Do not return a `CompanyData` with everything None.
- [ ] `refresh_section`: same as `get_company` (no cache to bypass).
- [ ] **Layer rules:** the only place `yfinance` and `pandas` are imported.

### `app/adapters/company_finnhub/` — Finnhub adapter

- [ ] New package directory with `__init__.py` exposing `FinnhubCompanyAdapter`.
- [ ] Constructor takes `api_key: str`. If empty string, raise on construction (`ValueError`).
- [ ] Implements `CompanyDataProvider`.
- [ ] `get_company`:
  - Populates `next_catalyst` from `/stock/earnings-calendar?symbol={ticker}` — pick the soonest future earnings date.
  - Populates `ownership.top_institutional_holders` from `/stock/institutional-ownership` (top 10). Compute `shares_change_qoq` by diffing against last quarter's snapshot if available (Finnhub returns this directly in newer API versions; if not present, leave `None`).
  - Populates `ownership.recent_insider_transactions` from `/stock/insider-transactions` filtered to the last 12 months. Map Finnhub's transaction codes to the `Literal["BUY", "SELL", "OPTION_EXERCISE", "OTHER"]` enum.
  - Populates `ownership.insider_ownership_pct` and `ownership.institutional_ownership_pct` from `/stock/profile2` (if present) or leave `None`.
  - Leaves every other section empty/None.
- [ ] **Partial-fill behaviour:** same as yfinance — section-level failures populate `fetch_errors`, function still returns.
- [ ] **Rate-limit handling:** if the HTTP response is 429, populate `fetch_errors[section] = "rate limited"` for whatever section was being fetched. No retry, no backoff. The user can hit the refresh button later.
- [ ] **Unrecoverable case:** if the API key is rejected (401), raise `CompanyDataError("Finnhub API key invalid")`.
- [ ] **Layer rules:** the only place `requests` (or `httpx`) is imported. Use a 10-second timeout on every HTTP call.

### `app/adapters/company_composite/` — composite adapter

- [ ] New package directory with `__init__.py` exposing `CompositeCompanyAdapter`.
- [ ] Constructor takes one or more `CompanyDataProvider` instances (variadic).
- [ ] `get_company`: calls each underlying adapter sequentially; merges the resulting `CompanyData` objects into one, with per-section precedence per decision §5 (yfinance wins by default; Finnhub wins for `ownership` and `next_catalyst`).
- [ ] `refresh_section`: calls `refresh_section` on each underlying adapter for the relevant section, then merges.
- [ ] `fetch_errors` from all underlying adapters are unioned (last writer wins on key collision — irrelevant in practice because adapters don't overlap on sections).

### `app/adapters/company_cache/` — cache decorator adapter

- [ ] New package directory with `__init__.py` exposing `CacheCompanyAdapter`.
- [ ] Constructor: `CacheCompanyAdapter(inner: CompanyDataProvider, cache_root: Path, *, now: Callable[[], datetime] = lambda: datetime.now(UTC))`. The `now` parameter is for test injection.
- [ ] On `get_company(ticker)`:
  - Compute the three cache file paths: `{cache_root}/{ticker}/profile.json`, `prices.json`, `financials.json`.
  - For each section, check if the file exists and is within TTL (per `ttl.py`). If yes, parse and use it. If no (missing, stale, or corrupt per decision §8), call `inner.refresh_section(ticker, section)` and write the result to disk.
  - Merge the three sections into a single `CompanyData` and return.
  - Populate `profile_fetched_at`, `prices_fetched_at`, `financials_fetched_at` from the respective files' `fetched_at` timestamps.
- [ ] On `refresh_section(ticker, section)`:
  - Delete the named section's cache file (if it exists).
  - Call `get_company(ticker)` — which will now re-fetch that section.
- [ ] **Cache file format:** exactly the shape in decision §2. Each file is a dict with `ticker`, `fetched_at`, `source`, `data`.
- [ ] **Corrupt-file handling:** per decision §8. Log a warning (via the stdlib `logging` module — no `print`), re-fetch, overwrite.
- [ ] **Atomic writes:** per decision §8. Write to `<path>.tmp`, `os.replace` to final.
- [ ] **Directory creation:** ensure `{cache_root}/{ticker}/` exists before writing (use `mkdir(parents=True, exist_ok=True)`).
- [ ] **Layer rules:** the only adapter that touches `pathlib`/`json`/`os`. No `yfinance`, no `requests`.

### `app/adapters/company_cache/ttl.py` — TTL constants and market-hours helper

- [ ] Defines `PROFILE_TTL`, `PRICES_TTL_MARKET_HOURS`, `PRICES_TTL_AFTER_CLOSE`, `FINANCIALS_TTL` per decision §7.
- [ ] Defines `prices_ttl(now: datetime) -> timedelta` returning the 15min/24h decision per NYSE hours. `now` parameter is required — no internal `datetime.now()`.
- [ ] Pure function; testable in isolation.

### `app/adapters/company_factory.py` — production wiring

- [ ] Defines `build_company_provider(cache_root: Path = Path("data/companies"), finnhub_api_key: str | None = None) -> CompanyDataProvider`.
- [ ] Reads `FINNHUB_API_KEY` from environment as default if argument is `None` (use `os.environ.get`).
- [ ] If Finnhub key is missing/empty, builds the composite with yfinance only. Logs an info message.
- [ ] Returns the cache-wrapped composite.

### `app/services/company.py` — new module

- [ ] Defines `get_company(ticker: str, *, provider: CompanyDataProvider) -> CompanyData` per decision §9.
- [ ] Defines `refresh_company_section(ticker, section, *, provider) -> CompanyData` per decision §9.
- [ ] Ticker is uppercased before being passed to the provider.
- [ ] **Layer rules:** no `streamlit`, no adapter imports. Imports: `app.domain.company`, `app.ports.company_data`.

### `.gitignore` update

- [ ] Append `data/companies/` (entire directory, recursively gitignored). Cache files must not be committed.

### `tests/unit/domain/test_company_models.py` — new tests

- [ ] **Frozen contract:** for each model, assert mutating any field raises `ValidationError` (Pydantic's frozen behaviour).
- [ ] **CompanyData with everything None:** can be constructed; serialises to JSON; round-trips back via `model_validate_json`.
- [ ] **CompanyData with everything populated:** can be constructed with realistic test fixtures (hand-built); round-trips.
- [ ] **fetch_errors default:** `CompanyData(...)` without `fetch_errors` defaults to `{}`.

### `tests/unit/adapters/test_company_cache.py` — new tests

These use a temp directory and a fake `inner: CompanyDataProvider`.

- [ ] **Cold cache:** no files exist → adapter calls `inner.refresh_section` three times (once per section) → cache files now exist on disk with the expected JSON shape.
- [ ] **Warm cache, all fresh:** files exist with recent `fetched_at` → adapter reads from disk, `inner.refresh_section` is never called.
- [ ] **Warm cache, one stale section:** `prices.json` is older than `PRICES_TTL_AFTER_CLOSE` (and now is outside market hours) → `inner.refresh_section(ticker, "prices")` called exactly once; the other two sections served from disk.
- [ ] **Corrupt cache file:** write `"not json"` to `profile.json` → adapter logs a warning, calls `inner.refresh_section`, overwrites the file with valid JSON.
- [ ] **Atomic write:** monkeypatch `os.replace` to raise after `<path>.tmp` is written → assert `<path>` (the final path) doesn't exist (the failed write is contained to `.tmp`).
- [ ] **`refresh_section("prices")`:** deletes `prices.json` and re-fetches, even if it was fresh.
- [ ] **Per-section `fetched_at` populated on returned `CompanyData`:** assert `profile_fetched_at`, `prices_fetched_at`, `financials_fetched_at` all match the timestamps in the cache files.
- [ ] **Cache root directory created if missing:** point `cache_root` at a nonexistent path; first `get_company` call creates it.

### `tests/unit/adapters/test_company_ttl.py` — new tests

- [ ] `prices_ttl(now=Mon 15:00 UTC)` returns `PRICES_TTL_MARKET_HOURS` (15min).
- [ ] `prices_ttl(now=Sat 15:00 UTC)` returns `PRICES_TTL_AFTER_CLOSE` (24h).
- [ ] `prices_ttl(now=Mon 22:00 UTC)` (after NYSE close) returns `PRICES_TTL_AFTER_CLOSE`.
- [ ] `prices_ttl(now=Mon 13:00 UTC)` (before NYSE open) returns `PRICES_TTL_AFTER_CLOSE`.

### `tests/unit/adapters/test_company_composite.py` — new tests

These use two fake `CompanyDataProvider` instances.

- [ ] **Two adapters fill disjoint sections:** yfinance-fake returns CompanyData with `profile` populated; finnhub-fake returns CompanyData with `ownership` populated. Composite returns CompanyData with both populated.
- [ ] **Precedence for overlapping sections:** both fakes set `next_catalyst` → Finnhub wins.
- [ ] **Both fakes set `profile`:** yfinance wins.
- [ ] **`fetch_errors` are unioned** across the two adapters.
- [ ] **`refresh_section` forwarded** to all underlying adapters.

### `tests/integration/test_company_yfinance.py` — new integration test

- [ ] **Marked `@pytest.mark.integration`** so it can be skipped in fast CI.
- [ ] **One end-to-end call:** `YfinanceCompanyAdapter().get_company("NVDA")` returns a `CompanyData` with `profile is not None`, `latest_quote is not None`, `len(price_history) > 0`. Allowed to fail in offline CI; the marker handles that.
- [ ] **Invalid ticker:** `get_company("NOTAREALTICKERZZZZ")` raises `CompanyDataError`.

### `tests/integration/test_company_finnhub.py` — new integration test

- [ ] **Marked `@pytest.mark.integration`.**
- [ ] **Skipped if `FINNHUB_API_KEY` env var is not set** (use `pytest.skip` at the top of the test).
- [ ] **One end-to-end call** for a well-known ticker (e.g. `AAPL`): `FinnhubCompanyAdapter(api_key=...).get_company("AAPL")` returns a `CompanyData` with `next_catalyst is not None` and `ownership.top_institutional_holders` non-empty.
- [ ] **Invalid API key:** `FinnhubCompanyAdapter(api_key="invalid").get_company("AAPL")` raises `CompanyDataError`.

### `tests/unit/services/test_company_service.py` — new tests

- [ ] **Happy path:** fake provider returns a known `CompanyData`; service returns it unchanged; ticker passed to provider is uppercased.
- [ ] **`refresh_company_section`:** fake provider's `refresh_section` is called with the right ticker and section.

### State updates (per `AGENTS.md` Step 8b)

- [ ] `docs/SESSION_LOG.md` appended with a new entry.
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-025 → IN_REVIEW under "In review 👀").
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-025 row → IN_REVIEW; new "Milestone — Company Deep Dive" section created if not already present from the draft script).
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --base main`, body contains `Closes #<N>`.

---

## Files created

```
app/domain/company.py
app/ports/company_data.py
app/adapters/company_yfinance/__init__.py
app/adapters/company_yfinance/adapter.py
app/adapters/company_finnhub/__init__.py
app/adapters/company_finnhub/adapter.py
app/adapters/company_composite/__init__.py
app/adapters/company_composite/adapter.py
app/adapters/company_cache/__init__.py
app/adapters/company_cache/adapter.py
app/adapters/company_cache/ttl.py
app/adapters/company_factory.py
app/services/company.py
tests/unit/domain/test_company_models.py
tests/unit/adapters/test_company_cache.py
tests/unit/adapters/test_company_ttl.py
tests/unit/adapters/test_company_composite.py
tests/integration/test_company_yfinance.py
tests/integration/test_company_finnhub.py
tests/unit/services/test_company_service.py
```

## Files modified

```
.gitignore                              ← append data/companies/
docs/PROJECT_STATE.md                   ← TICKET-025 → IN_REVIEW
docs/SESSION_LOG.md                     ← new session entry
docs/TICKETS/BACKLOG.md                 ← TICKET-025 row → IN_REVIEW
```

## Files NOT to modify

- `app/ui/**` — **zero UI changes in this ticket.** If you find yourself opening a Streamlit file, you've drifted. The UI is C2–C7.
- `app/domain/models.py` — `Money` is reused as-is. If you need a new value object, stop and report.
- `app/ports/price_feed.py`, `app/ports/fx_feed.py` — existing ports; unrelated. Do not refactor them "while you're here."
- `app/adapters/price_yfinance/` — the existing price adapter from TICKET-004-005 stays. The new `company_yfinance` adapter is independent and can coexist.
- `app/services/valuation.py`, `app/services/trading.py` — read-only for this ticket. The Live Overview and Manage Portfolio flows must not change.
- `pyproject.toml` / `environment.yml` — yfinance, pydantic, requests are already deps. **No new dependencies.**
- `.importlinter` — the existing layer rules already cover `app/adapters/*` and `app/services/*`. The new modules slot into the existing config without changes. If you find yourself wanting to edit `.importlinter`, stop and report — that's an architectural change.

---

## Out of scope

- **Watchlist** — `data/watchlist.json`, the `WatchlistService`, the star toggle. **C7.**
- **Glossary tooltip system** — `app/ui/glossary.py`. **C7.**
- **The Company Deep Dive page itself** — `app/ui/pages/company.py`. **C2.**
- **Any tab content** — Snapshot, Financials, Valuation, Capital & Ownership, Business stub, Risk stub. **C3–C6.**
- **Historical multiples computation** (P/E over 5Y, EV/EBITDA over 5Y from price × historical EPS). The data plumbing is here; the computation is in C5 (Valuation tab) because it's a presentation-layer concern that doesn't need to live in the cache.
- **Peer multiples table data** — peer set selection is manual user entry; the peer multiples themselves come from calling `get_company` per peer ticker. The orchestration is C5, not C1.
- **Segment revenue data** — out of scope for v1 of the entire milestone (no reliable data source). Tab 2 (Business) is a stub.
- **Currency conversion of fundamentals to EUR.** Fundamentals stay in their native reporting currency. The Money on `market_cap` carries its currency. UI presentation in EUR (for portfolio context) is a presentation-layer concern handled per tab.
- **`@st.cache_data`** anywhere — caching is at the adapter layer, not the UI layer.
- **Background refresh** — there is no background job. Refresh happens lazily on `get_company` (if TTL expired) or eagerly when the user clicks a refresh button (C2 wires the button; it calls `refresh_company_section`).
- **Cache size limits / eviction.** The directory grows unbounded; not a concern at single-user scale.
- **Async / concurrent fetches.** The adapter is synchronous. Two calls to `get_company` for different tickers run sequentially. C2 may add a spinner; it does not parallelise.
- **Persistence of `fetch_errors` across cache refreshes.** Errors are per-fetch; a successful refetch clears them. (They're written to disk inside the section file alongside the data, so a cached section "remembers" its last error until refresh — but they're not aggregated.)
- **Schema migration when models change.** If `CompanyData` gains a field later, old cache files will fail to parse. Per decision §8, that triggers a re-fetch. No migration tool needed.

---

## Test cases (manual review checklist for the PR)

The data layer has no UI to click through, so review is primarily reading the diff and running `pytest`. The few observable checks:

- [ ] `pytest tests/unit/domain/test_company_models.py tests/unit/adapters/ tests/unit/services/test_company_service.py` — all pass.
- [ ] `pytest tests/integration/test_company_yfinance.py -m integration` (with network) — passes for `NVDA`.
- [ ] If `FINNHUB_API_KEY` is set: `pytest tests/integration/test_company_finnhub.py -m integration` — passes for `AAPL`.
- [ ] `ruff check . && mypy app/ && lint-imports` — all pass.
- [ ] **Smoke check from a Python REPL** (one-off, for the PR review):

  ```python
  from app.adapters.company_factory import build_company_provider
  provider = build_company_provider()
  data = provider.get_company("NVDA")
  print(data.profile.name, data.profile.sector, data.latest_quote.price)
  print(len(data.price_history), len(data.quarterly_fundamentals))
  print(data.fetch_errors)
  ```

  - First call writes three files under `data/companies/NVDA/`. Verify by `ls data/companies/NVDA/`.
  - Second call (immediately) is served from cache — verify by observing it returns in <100ms (or by checking that no network call is made; print a marker from inside the adapter if helpful).
  - `data.fetch_errors` either empty or contains expected entries (e.g. Finnhub sections empty if no API key).

- [ ] **Manual `data/companies/NVDA/profile.json` inspection:** valid JSON, has the `ticker / fetched_at / source / data` shape, `fetched_at` is recent and timezone-aware.

- [ ] **No UI regressions:** open the app, navigate to Live Overview and Manage Portfolio. Nothing should look different. (This is a paranoia check — C1 doesn't touch UI files, but it adds adapters that share the yfinance dep with the existing price adapter.)

---

## Notes (architectural and methodological — for future AI sessions)

### Why a composite adapter instead of letting the cache adapter know about two underlying providers

The cache adapter's job is purely "is this file fresh? if not, refetch." It shouldn't have to know that "refetch" means "ask yfinance for some sections and Finnhub for others." That coupling sits in the composite, which exists for exactly this reason. A future adapter (e.g. a third data source) plugs into the composite without touching the cache adapter at all.

### Why three cache files, not one with TTL-per-section

Tried in my head: one big `<TICKER>.json` with three sub-sections, each carrying its own `fetched_at`. The TTL check would inspect each sub-section's `fetched_at` independently. Cleaner on paper.

The killer is concurrent writes. If a price refresh and a profile refresh both fire (two browser tabs, or one tab triggering both), they'd both read the file, both mutate their section, both write the merged result — the second write stomps the first. With three files, each refresh's write target is independent.

Locking would solve it but adds machinery (a lock file? a thread lock that doesn't survive process restarts?) for a problem that goes away with three files. Three files is the simplest answer.

### Why partial-fill returns `CompanyData` with `fetch_errors`, not raises

The UI needs to render *something* even when one section failed. Raising forces the UI to handle "completely missing" vs "partially missing" as separate code paths. With `fetch_errors`, the UI has one code path: render every section that has data, and for each section in `fetch_errors`, render a small "data unavailable" banner.

This is the "no silent fallback" rule applied correctly: the failure is *visible* to the user (banner), not hidden behind a default value. The data either is there or is explicitly absent.

### Why the cache adapter logs warnings via stdlib logging, not via a custom helper

Stdlib `logging` is enough. There's no existing logging abstraction in the project. Adding one for this ticket is scope creep. If the project later grows a logging service, the cache adapter's logging calls migrate at that time, in their own ticket.

### Why ISIN and currency live on `CompanyProfile`, not on a separate model

ISIN is identity-adjacent and rarely changes. Currency is per-ticker (in yfinance's data model) and rarely changes. Both are most-naturally read alongside name/sector. Putting them on their own model (`SecurityIdentity`) would be principled but over-modelled at this scale.

### Why `next_catalyst` is a single field, not a list

A user looking at a Snapshot tab wants to see "the next thing" — one date, one description. A list of catalysts is a feature for a future "catalyst calendar" page, not for the deep dive snapshot. If/when that page exists, the field becomes `next_catalysts: list[NextCatalyst]` and the Snapshot tab picks `[0]`.

### Files NOT to modify is unusually long because this ticket is unusually orthogonal

C1 builds a parallel data layer next to the existing one. The existing price adapter (TICKET-004-005), the existing valuation service (TICKET-006), the existing UI — none of them need to change. The risk during implementation is "while I'm here, let me consolidate `app/adapters/price_yfinance/` and the new `app/adapters/company_yfinance/` since they both wrap yfinance" — **don't**. The price adapter has a narrow, hot, low-latency surface. The company adapter has a broad, cached, low-frequency surface. They have different shapes for a reason.
