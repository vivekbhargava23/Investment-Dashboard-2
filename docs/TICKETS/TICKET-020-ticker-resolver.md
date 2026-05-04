# TICKET-020 — TickerResolver port + yfinance adapter (autocomplete + metadata)

**Status:** DRAFT
**Priority:** P1 (blocks TICKET-009-revised)
**Estimated session length:** 1.5 – 2 hr
**Drafted by:** Vivek + Claude (chat 2026-05-04)
**Implemented by:** _pending_
**Depends on:** TICKETs 001 (domain — Currency), 004-005 (yfinance adapter — extending it), 008c (Currency enum extended; `infer_currency_from_ticker` exists)

---

## Problem

TICKET-009-revised's form needs a way to:

1. Take a partial ticker query ("AP") and return ranked matches.
2. For each match, return enough metadata to display a useful row (name, exchange, currency) and to drive the submit pipeline (currency confirms what `infer_currency_from_ticker` says).

Existing `PriceProvider` only fetches prices for a known ticker. There is no "search" surface. This ticket adds it.

This is also the right place to consolidate any other "ticker → metadata" needs: the placeholder `_TICKER_NAMES` dict in `app/ui/pages/overview.py` (introduced as a TICKET-008 placeholder) becomes obsolete. The resolver becomes the single source of truth for `(ticker → name, exchange, currency)`.

---

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-04:

1. **`TickerResolver` is its own port, not a method on `PriceProvider`.** Reason: a future implementation could be a different security-master (e.g., OpenFIGI, broker-supplied master) without changing the price feed. Two ports = two clean interfaces. The yfinance adapter happens to implement both.

2. **`resolve(query)` returns a list, not an Optional single match.** Even an exact symbol match should not collapse to one result, because the same symbol can exist on multiple exchanges (e.g., `HSBC` on LSE vs NYSE). The form picks; the resolver suggests.

3. **The resolver caches aggressively and indefinitely.** Once we know "AP" → `[APD, APP, APRN, ...]`, that mapping is functionally permanent. Symbols are stable; new IPOs are rare. A 1-hour TTL is a sensible default; longer is fine. The cache is in-memory only (consistent with TICKET-004-005's policy: no on-disk caches).

4. **A single `TickerMatch` dataclass holds everything the UI needs.** Frozen, no methods. The `currency` field is a `Currency` enum value — already validated by the time the resolver returns it. If yfinance reports a currency we don't yet support, the resolver *omits that match* rather than raising. (We don't want a search for "AP" to fail because some Hong Kong listing came back as HKD.)

5. **The yfinance search backing is `yfinance.Search` (newer versions) with a fallback to the lookup endpoint.** yfinance's API has been moving; the adapter handles both. If both fail, the resolver returns an empty list, not an exception — empty results are a normal state, errors are exceptional.

6. **`infer_currency_from_ticker` from TICKET-008c is consulted as a sanity check.** When yfinance reports a ticker's currency, the adapter compares against `infer_currency_from_ticker(symbol)`. Mismatch → log a warning and trust the suffix-based inference (the more conservative choice). This catches yfinance metadata bugs.

---

## Acceptance criteria

### `app/ports/ticker_resolver.py` — new port file

- [ ] `TickerMatch` — frozen Pydantic v2 model:
  ```python
  class TickerMatch(BaseModel):
      model_config = ConfigDict(frozen=True)
      symbol: str           # canonical, e.g., "APD" or "5631.T"
      name: str             # e.g., "Air Products and Chemicals"
      exchange: str         # e.g., "NYSE", "FRA", "TYO"
      currency: Currency    # native trading currency (must be in Currency enum)
      recent_price: Money | None  # most recent close, None if unknown
  ```

- [ ] `TickerResolver` — `typing.Protocol`:
  ```python
  class TickerResolver(Protocol):
      def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]: ...
      def lookup(self, symbol: str) -> TickerMatch | None: ...
      def clear_cache(self) -> None: ...
  ```

- [ ] `resolve` — fuzzy/prefix search. Empty result list is a valid return value. No exception on "no matches."
- [ ] `lookup` — exact-symbol lookup. Returns the single match for an exact symbol, or `None` if unknown. Used by the manage form when editing an existing transaction (we already know the symbol; we just want metadata).
- [ ] `clear_cache` — drop all cached matches.

### `app/adapters/yfinance_feed.py` — extend existing adapter

- [ ] Adapter class `YfinanceAdapter` already implements `PriceProvider` and `FxProvider`. Add `TickerResolver` as a third Protocol it satisfies. No new file; extend in place.

- [ ] Add an in-memory cache: `_resolver_cache: dict[str, tuple[float, list[TickerMatch]]]` keyed by query string. TTL: 3600 seconds (1 hour). Same `time.monotonic()` discipline as the existing caches.

- [ ] `resolve(query, limit)` implementation:
  1. Normalise `query`: strip, uppercase. Reject empty queries (return empty list).
  2. Cache check; return cached list if fresh.
  3. Try `yfinance.Search(query).quotes` — newer yfinance versions. This returns a list of dicts with at least `symbol`, `shortname` or `longname`, `exchange`, `currency`.
  4. If `yfinance.Search` is unavailable or returns empty, fall back to `yfinance.utils.get_json("https://query1.finance.yahoo.com/v1/finance/search", params={"q": query, "quotesCount": limit})`. (yfinance's underlying search API.)
  5. For each raw result:
     a. Extract `symbol`, `name`, `exchange`, `currency_str`.
     b. If `currency_str` not in `Currency` enum's value set → skip this match silently. (Empty list is fine; a half-broken match is not.)
     c. Cross-check: `inferred = infer_currency_from_ticker(symbol)`. If `inferred != Currency(currency_str)` → log a warning, use `inferred` (suffix-based wins).
     d. Optionally fetch `recent_price` via `yf.Ticker(symbol).fast_info.lastPrice`. If this fails or is slow, set `recent_price = None`. Use a per-match timeout (e.g., wrap in a try/except — yfinance is not async-friendly).
     e. Wrap in `TickerMatch`.
  6. Truncate to `limit`. Cache. Return.

- [ ] `lookup(symbol)` implementation:
  1. Cache check (cache key: `f"lookup:{symbol}"`).
  2. Call `yf.Ticker(symbol).info`. yfinance's `info` dict contains `shortName`, `exchange`, `currency`, etc.
  3. If `info` is empty/missing → return `None`.
  4. Build a `TickerMatch` exactly as in `resolve`. Cache. Return.

- [ ] `clear_cache` (existing): also clears `_resolver_cache`.

- [ ] **Currency mismatch handling — explicit:** if a match's `currency_str` is, say, `"HKD"` and `Currency` does not yet support HKD, the match is *silently omitted*. This is the right behaviour because the user cannot record a transaction in HKD anyway (TICKET-008c validator would reject it). Surfacing it in the autocomplete and then having submit fail would be cruel. Document this in a docstring.

### Tests

#### `tests/unit/ports/test_ticker_resolver_protocol.py` (small)

- [ ] Trivially verify `TickerMatch` constructs and is frozen.
- [ ] Verify Protocol has the three required methods.

#### `tests/integration/test_yfinance_resolver.py`

- [ ] Marked `@pytest.mark.integration`, skipped by default.
- [ ] **Resolve common ticker:** `resolve("APD")` returns at least one match with `symbol="APD"`, `currency=Currency.USD`.
- [ ] **Resolve EUR ticker:** `resolve("RHM")` returns at least one match including `RHM.DE` with `currency=Currency.EUR`.
- [ ] **Resolve JPY ticker:** `resolve("Japan Steel Works")` returns at least one match including `5631.T` with `currency=Currency.JPY`. (This test fails before TICKET-008c lands.)
- [ ] **Empty query:** `resolve("")` returns `[]`, no exception.
- [ ] **Garbage query:** `resolve("XQYZNOTREAL")` returns `[]`, no exception.
- [ ] **Currency-not-supported is omitted, not raised:** mock yfinance to return a result with `currency="HKD"`. `resolve(...)` does not include that result and does not raise.
- [ ] **Lookup happy path:** `lookup("NVDA")` returns a `TickerMatch` with USD.
- [ ] **Lookup miss:** `lookup("XQYZNOTREAL")` returns `None`.
- [ ] **Cache works:** call `resolve("APD")` twice with a counting mock; second call uses cache (check via internal counter or by mocking `yf.Search` to assert call count = 1).
- [ ] **`clear_cache` invalidates resolver cache:** call resolve, clear, call again; mock shows two calls.

#### `tests/fakes/ticker_resolver.py` — for use by other tickets' tests

- [ ] `FakeTickerResolver` class implementing the Protocol with hardcoded match dictionaries. Used by TICKET-009-revised's tests.

### Lints / quality

- [ ] `pytest` — all tests pass (integration tests skipped by default; run with `--run-integration` to verify).
- [ ] `ruff check .` — passes.
- [ ] `mypy app/` — passes.
- [ ] `lint-imports` — passes:
  - `app/ports/ticker_resolver.py` imports from `app.domain` only.
  - `app/adapters/yfinance_feed.py` imports from `app.ports`, `app.domain`, and `yfinance`. Same rules as existing adapter.

### State updates (per CLAUDE.md session-end ritual)

- [ ] `docs/SESSION_LOG.md` appended.
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-020 → IN_REVIEW).
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-020 added; → IN_REVIEW).
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.

---

## Files created

```
app/ports/ticker_resolver.py
tests/unit/ports/__init__.py             ← if not yet created
tests/unit/ports/test_ticker_resolver_protocol.py
tests/integration/test_yfinance_resolver.py
tests/fakes/__init__.py                  ← if not yet created
tests/fakes/ticker_resolver.py
```

## Files modified

```
app/adapters/yfinance_feed.py            ← add TickerResolver implementation
app/adapters/__init__.py                 ← export updates if needed
docs/TICKETS/BACKLOG.md                  ← add TICKET-020 row
```

---

## Out of scope

- **Non-yfinance resolvers** (OpenFIGI, broker security master). The port is designed to permit them; the implementation is yfinance-only for now.
- **Persistent caches** (file or SQLite). In-memory only, consistent with TICKET-004-005 policy.
- **Multi-language search.** Query and results are English/Roman-alphabet. yfinance's search handles this natively.
- **Ranking heuristics beyond what yfinance returns.** We sort by yfinance's order. If we observe rank quality issues in practice, a future ticket adds custom ranking.
- **HKD, AUD, KRW, and other currency support.** This ticket *omits* matches in unsupported currencies; it does not extend the `Currency` enum. That extension is its own ticket as currencies are needed.
- **Migrating overview.py's `_TICKER_NAMES` dict to use the resolver.** Tempting, but that change belongs to TICKET-009-revised's "obsolete the placeholder" cleanup, not here.

---

## Notes (for future AI sessions)

### Why a separate Protocol from `PriceProvider`

Future-proofing. A `TickerResolver` could legitimately be implemented by a security-master service (OpenFIGI, the user's broker's instrument master) that has nothing to do with prices. Conflating them would force every search-capable adapter to also implement price fetching, which is a real coupling burden.

That said: yfinance handles both. So in v1, `YfinanceAdapter` satisfies both Protocols and `wiring.py` returns the same instance for `get_price_provider()` and `get_ticker_resolver()`. This is fine; the Protocol separation costs nothing and pays off only if we ever swap.

### Why we cross-check yfinance's currency against `infer_currency_from_ticker`

yfinance's metadata is sometimes wrong. We have seen historical examples of `.T` tickers reporting USD currency in yfinance's `info` dict (probably a bug in yfinance's symbol normalisation). The suffix-based inference is *deterministic*; yfinance's metadata is *empirical*. When they disagree, the deterministic answer is the safer choice — and we log a warning so we can investigate if it ever fires in production.

### Why we don't fetch `recent_price` for every match

It's slow. yfinance makes one HTTP call per ticker for `fast_info`. A search returning 10 matches would take 5–10 seconds at worst. We fetch lazily: include `recent_price` if it comes "free" with the search response, otherwise leave it `None`. The form's autocomplete renders fine without a price.

### Why empty result is `[]`, not exception

The user types "AP" — three matches. Then types "APX" — zero matches. Treating "zero matches" as an error would force the form to handle two failure modes (network error vs no matches) when the UX is the same: "no suggestions, keep typing or click 'use as-typed'." Returning `[]` collapses these. Genuine network errors propagate as exceptions; that's a different code path.
